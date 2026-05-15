from collections.abc import Callable
import inspect
import json
from typing import Any
from urllib.parse import urlparse, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AnalysisPrompt, AnalysisRun, ScanJob, Website
from app.models.entities import ApiTokenScope
from app.schemas.dto import SearchRequest
from app.services.crawler import CompanyCrawler
from app.services.analysis import AnalysisService, seed_default_analysis_prompts, serialize_analysis_run
from app.services.auth import ApiPrincipal, require_mcp_principal, require_principal_scope
from app.services.search import semantic_search

router = APIRouter(prefix="/mcp", tags=["MCP"])
MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_CONTEXT = (
    "Companycrawler verzamelt publieke websitecontent om bedrijfsprofielen, pagina-/bestandsstructuur, "
    "samenvattingen, embeddings en agentische analyses beschikbaar te maken voor salesvoorbereiding, "
    "marktverkenning en PoC-briefings. Tools lezen of starten dezelfde workflows als de REST API: scans "
    "blijven same-domain, dode links worden als scanmelding teruggegeven, semantische zoekresultaten zijn "
    "bedoeld als compacte LLM-context, en analyses bouwen voort op de gecrawlde documenten en beheerbare prompts."
)


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_websites",
            "title": "List websites",
            "description": "List known company websites with the profile metadata that anchors later scans, search and analyses. Use this first to pick a website_id.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "outputSchema": {
                "type": "object",
                "properties": {
                    "websites": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "url": {"type": "string"},
                                "company_name": {"type": "string"},
                                "company_place": {"type": "string"},
                                "region": {"type": "string"},
                                "logo_url": {"type": "string"},
                            },
                            "required": ["id", "url", "company_name", "company_place", "region", "logo_url"],
                        },
                    }
                },
                "required": ["websites"],
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "upsert_website",
            "title": "Create or update website",
            "description": "Create a new company website record or update an existing one by URL. Optionally detects company metadata from the homepage when fields are missing.",
            "inputSchema": _website_input_schema(),
            "outputSchema": {
                "type": "object",
                "properties": {
                    "created": {"type": "boolean"},
                    "website": {"type": "object"},
                    "profile_detection_error": {"type": "string"},
                },
                "required": ["created", "website"],
            },
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": True,
                "idempotentHint": True,
            },
        },
        {
            "name": "start_scan",
            "title": "Start website scan",
            "description": "Queue a public same-domain crawl for an existing website id. The worker extracts pages/files, summaries and embeddings; broken URLs are reported as scan errors but do not always fail the whole scan.",
            "inputSchema": {
                "type": "object",
                "properties": {"website_id": {"type": "integer", "minimum": 1}},
                "required": ["website_id"],
                "additionalProperties": False,
            },
            "outputSchema": _scan_output_schema(),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": True,
                "idempotentHint": False,
            },
        },
        {
            "name": "scan_and_analyze_website",
            "title": "Scan and analyze website",
            "description": "Create or update a website record, queue a same-domain scan, and mark it for automatic company analysis after the scan completes. Poll get_scan_analysis_status for progress.",
            "inputSchema": _website_input_schema(),
            "outputSchema": {
                "type": "object",
                "properties": {
                    "website": {"type": "object"},
                    "scan": {"type": "object"},
                    "analysis": {"type": ["object", "null"]},
                    "profile_detection_error": {"type": "string"},
                },
                "required": ["website", "scan", "analysis"],
            },
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": True,
                "idempotentHint": False,
            },
        },
        {
            "name": "get_scan_status",
            "title": "Get scan status",
            "description": "Return scan progress, status, latest worker message and any current error text such as dead links or fatal crawl failures. Poll this after start_scan.",
            "inputSchema": {
                "type": "object",
                "properties": {"scan_id": {"type": "integer", "minimum": 1}},
                "required": ["scan_id"],
                "additionalProperties": False,
            },
            "outputSchema": _scan_output_schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_scan_analysis_status",
            "title": "Get scan and analysis status",
            "description": "Return combined progress for a scan started by scan_and_analyze_website, including the linked or latest company analysis when available.",
            "inputSchema": {
                "type": "object",
                "properties": {"scan_id": {"type": "integer", "minimum": 1}},
                "required": ["scan_id"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "website": {"type": "object"},
                    "scan": {"type": "object"},
                    "analysis": {"type": ["object", "null"]},
                    "ready": {"type": "boolean"},
                },
                "required": ["website", "scan", "analysis", "ready"],
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "search_company_data",
            "title": "Search company data",
            "description": "Semantic search over crawled public company website content. Use this to retrieve compact, source-linked context for a question before drafting analysis, scenarios or PoC material.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "website_id": {"type": ["integer", "null"], "minimum": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {"results": {"type": "array", "items": {"type": "object"}}},
                "required": ["results"],
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_company_profile",
            "title": "Get company profile",
            "description": "Return website metadata and known document summaries for a company. This is the broad context snapshot for an LLM client before deeper search or analysis retrieval.",
            "inputSchema": {
                "type": "object",
                "properties": {"website_id": {"type": "integer", "minimum": 1}},
                "required": ["website_id"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "url": {"type": "string"},
                    "company_name": {"type": "string"},
                    "logo_url": {"type": "string"},
                    "documents": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["id", "url", "company_name", "logo_url", "documents"],
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "list_analysis_prompts",
            "title": "List analysis prompts",
            "description": "List manageable prompts for the company analysis jobs, including the purpose of each step in the chain. Admins can adjust these prompts through the application settings.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "outputSchema": {"type": "object", "properties": {"prompts": {"type": "array", "items": {"type": "object"}}}, "required": ["prompts"]},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "run_company_analysis",
            "title": "Run company analysis",
            "description": "Run the agentic company analysis chain for a website. The chain uses website metadata, crawl summaries and semantic chunks to extract profile variables, challenges, value opportunities, market context and technology hooks.",
            "inputSchema": {
                "type": "object",
                "properties": {"website_id": {"type": "integer", "minimum": 1}},
                "required": ["website_id"],
                "additionalProperties": False,
            },
            "outputSchema": {"type": "object", "properties": {"id": {"type": "integer"}, "status": {"type": "string"}, "jobs": {"type": "array", "items": {"type": "object"}}}},
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "get_company_analysis",
            "title": "Get company analysis",
            "description": "Return a stored company analysis run with all job results, extracted variables, summaries, sources and provider errors. Use this instead of rerunning analysis when a recent run exists.",
            "inputSchema": {
                "type": "object",
                "properties": {"analysis_id": {"type": "integer", "minimum": 1}},
                "required": ["analysis_id"],
                "additionalProperties": False,
            },
            "outputSchema": {"type": "object", "properties": {"id": {"type": "integer"}, "status": {"type": "string"}, "jobs": {"type": "array", "items": {"type": "object"}}}},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "generate_company_scenarios",
            "title": "Generate company scenarios",
            "description": "Return scenario-ready opportunities from the latest stored company analysis. This tool reshapes analysis jobs into practical directions for solution discovery or customer conversations.",
            "inputSchema": {
                "type": "object",
                "properties": {"website_id": {"type": "integer", "minimum": 1}},
                "required": ["website_id"],
                "additionalProperties": False,
            },
            "outputSchema": {"type": "object", "properties": {"scenarios": {"type": "array", "items": {"type": "object"}}}, "required": ["scenarios"]},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "generate_poc_brief",
            "title": "Generate PoC brief",
            "description": "Return a PoC briefing based on the latest stored company analysis, including company profile, challenges, value opportunities and technical hooks for a first proposal.",
            "inputSchema": {
                "type": "object",
                "properties": {"website_id": {"type": "integer", "minimum": 1}},
                "required": ["website_id"],
                "additionalProperties": False,
            },
            "outputSchema": {"type": "object", "properties": {"brief": {"type": "object"}}, "required": ["brief"]},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
    ]


def _scan_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "status": {"type": "string"},
            "progress": {"type": "integer"},
            "message": {"type": "string"},
            "error": {"type": "string"},
            "auto_analyze": {"type": "boolean"},
            "analysis_run_id": {"type": ["integer", "null"]},
        },
        "required": ["id", "status", "progress", "message"],
    }


def _website_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string", "minLength": 1},
            "company_name": {"type": "string"},
            "company_place": {"type": "string"},
            "region": {"type": "string"},
            "logo_url": {"type": "string"},
            "detect_profile": {"type": "boolean", "default": True},
        },
        "required": ["url"],
        "additionalProperties": False,
    }


@router.get("")
def manifest(_: ApiPrincipal = Depends(require_mcp_principal)) -> dict:
    tools = _tool_descriptors()
    return {
        "name": "companycrawler",
        "description": SERVER_CONTEXT,
        "protocol": "MCP",
        "protocol_version": MCP_PROTOCOL_VERSION,
        "transport": "streamable-http-json-rpc",
        "jsonrpc_endpoint": "/mcp",
        "data_context": {
            "purpose": "Publieke websitecontent omzetten naar betrouwbare bedrijfscontext voor analyse, salesvoorbereiding en PoC-briefings.",
            "sources": ["Gecrawlde same-domain pagina's", "Publieke bestanden", "AI-samenvattingen", "Embeddings", "Opgeslagen analysejobs"],
            "analysis_context": "De analyse combineert gedetecteerde bedrijfsmetadata, documentensamenvattingen en relevante semantische chunks. Resultaten zijn ondersteunende analysecontext en moeten bij klantcommunicatie tegen de bronpagina's worden gecontroleerd.",
            "privacy": "De crawler is bedoeld voor publieke website-informatie. Secrets en providerconfiguratie worden niet via MCP teruggegeven.",
        },
        "capabilities": {"tools": {"listChanged": False}},
        "tools": tools,
    }


@router.post("")
async def json_rpc(request: Request, principal: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict | None:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON"},
        }
    if isinstance(payload, list):
        responses = [await _json_rpc_response(item, db, principal) for item in payload]
        return [response for response in responses if response is not None]
    return await _json_rpc_response(payload, db, principal)


async def _handle_json_rpc(payload: dict[str, Any], db: Session, principal: ApiPrincipal | None = None) -> dict[str, Any] | None:
    method = payload.get("method")
    params = payload.get("params") or {}
    if method == "initialize":
        requested_version = params.get("protocolVersion")
        return {
            "protocolVersion": requested_version or MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "companycrawler", "title": "Companycrawler", "version": "1.0.0"},
            "instructions": SERVER_CONTEXT,
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": _tool_descriptors()}
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        return await _call_tool(tool_name, arguments, db, principal)
    raise ValueError(f"Unsupported MCP method: {method}")


async def _json_rpc_response(payload: dict[str, Any], db: Session, principal: ApiPrincipal | None = None) -> dict[str, Any] | None:
    request_id = payload.get("id")
    if request_id is None:
        return None
    try:
        result = await _handle_json_rpc(payload, db, principal)
        if result is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except ValueError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": str(exc)}}
    except HTTPException as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": str(exc.detail)}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}


async def _call_tool(tool_name: str, arguments: dict[str, Any], db: Session, principal: ApiPrincipal | None = None) -> dict[str, Any]:
    handlers: dict[str, Callable[..., Any]] = {
        "list_websites": list_websites,
        "upsert_website": upsert_website,
        "start_scan": start_scan,
        "scan_and_analyze_website": scan_and_analyze_website,
        "get_scan_status": get_scan_status,
        "get_scan_analysis_status": get_scan_analysis_status,
        "search_company_data": search_company_data,
        "get_company_profile": get_company_profile,
        "list_analysis_prompts": list_analysis_prompts,
        "run_company_analysis": run_company_analysis,
        "get_company_analysis": get_company_analysis,
        "generate_company_scenarios": generate_company_scenarios,
        "generate_poc_brief": generate_poc_brief,
    }
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"Unknown MCP tool: {tool_name}")
    if principal is not None:
        require_principal_scope(principal, _tool_scope(tool_name))
    result = await _invoke_tool(handler, arguments, db, principal)
    if "error" in result:
        return {
            "isError": True,
            "structuredContent": result,
            "content": [{"type": "text", "text": result["error"]}],
        }
    result = _jsonable(result)
    return {
        "structuredContent": result,
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
    }


def _tool_scope(tool_name: str) -> ApiTokenScope:
    if tool_name in {"upsert_website", "start_scan", "scan_and_analyze_website", "run_company_analysis"}:
        return ApiTokenScope.execute
    return ApiTokenScope.read


async def _invoke_tool(handler: Callable[..., Any], arguments: dict[str, Any], db: Session, principal: ApiPrincipal | None = None) -> dict[str, Any]:
    if handler is list_websites:
        result = handler(_=principal, db=db) if principal else handler(db=db)
    elif handler is upsert_website:
        result = await handler(payload=arguments, principal=principal, db=db) if principal else await handler(payload=arguments, db=db)
    elif handler is start_scan:
        result = handler(website_id=arguments.get("website_id"), principal=principal, db=db) if principal else handler(website_id=arguments.get("website_id"), db=db)
    elif handler is scan_and_analyze_website:
        result = await handler(payload=arguments, principal=principal, db=db) if principal else await handler(payload=arguments, db=db)
    elif handler is get_scan_status:
        result = handler(scan_id=arguments.get("scan_id"), _=principal, db=db) if principal else handler(scan_id=arguments.get("scan_id"), db=db)
    elif handler is get_scan_analysis_status:
        result = handler(scan_id=arguments.get("scan_id"), _=principal, db=db) if principal else handler(scan_id=arguments.get("scan_id"), db=db)
    elif handler is search_company_data:
        result = handler(payload=SearchRequest(**arguments), _=principal, db=db) if principal else handler(payload=SearchRequest(**arguments), db=db)
    elif handler is get_company_profile:
        result = handler(website_id=arguments.get("website_id"), _=principal, db=db) if principal else handler(website_id=arguments.get("website_id"), db=db)
    elif handler is list_analysis_prompts:
        result = handler(_=principal, db=db) if principal else handler(db=db)
    elif handler is run_company_analysis:
        result = handler(website_id=arguments.get("website_id"), principal=principal, db=db) if principal else handler(website_id=arguments.get("website_id"), db=db)
    elif handler is get_company_analysis:
        result = handler(analysis_id=arguments.get("analysis_id"), _=principal, db=db) if principal else handler(analysis_id=arguments.get("analysis_id"), db=db)
    elif handler is generate_company_scenarios:
        result = handler(website_id=arguments.get("website_id"), _=principal, db=db) if principal else handler(website_id=arguments.get("website_id"), db=db)
    elif handler is generate_poc_brief:
        result = handler(website_id=arguments.get("website_id"), _=principal, db=db) if principal else handler(website_id=arguments.get("website_id"), db=db)
    else:
        raise ValueError("Unsupported MCP tool handler")
    if inspect.isawaitable(result):
        result = await result
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _normalize_website_url(raw_url: str | None) -> str:
    value = (raw_url or "").strip()
    if not value:
        raise ValueError("url is required")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be a valid http(s) URL or domain")
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _website_url_key(url: str) -> str:
    return _normalize_website_url(url).rstrip("/").lower()


def _find_website_by_url(db: Session, url: str) -> Website | None:
    key = _website_url_key(url)
    for website in db.query(Website).all():
        if _website_url_key(website.url) == key:
            return website
    return None


def _serialize_website(website: Website) -> dict[str, Any]:
    return {
        "id": website.id,
        "url": website.url,
        "company_name": website.company_name,
        "company_place": website.company_place,
        "region": website.region,
        "logo_url": website.logo_url,
        "created_at": website.created_at,
        "updated_at": website.updated_at,
    }


def _serialize_scan(scan: ScanJob) -> dict[str, Any]:
    return {
        "id": scan.id,
        "website_id": scan.website_id,
        "status": _status_value(scan.status),
        "progress": scan.progress,
        "message": scan.message,
        "items_found": scan.items_found,
        "items_processed": scan.items_processed,
        "error": scan.error,
        "auto_analyze": scan.auto_analyze,
        "analysis_run_id": scan.analysis_run_id,
        "created_at": scan.created_at,
        "started_at": scan.started_at,
        "completed_at": scan.completed_at,
    }


async def _upsert_website_from_payload(payload: dict[str, Any], db: Session) -> tuple[Website, bool, str]:
    normalized_url = _normalize_website_url(payload.get("url"))
    detect_profile = payload.get("detect_profile", True)
    detected: dict[str, str] = {}
    detection_error = ""
    provided_company_name = (payload.get("company_name") or "").strip()
    if detect_profile and not all((payload.get(key) or "").strip() for key in ["company_name", "company_place", "region", "logo_url"]):
        try:
            detected = await CompanyCrawler(db).detect_company_profile(normalized_url)
        except Exception as exc:
            detection_error = str(exc)
    parsed = urlparse(normalized_url)
    website = _find_website_by_url(db, normalized_url)
    created = website is None
    company_name = provided_company_name or detected.get("company_name") or (website.company_name if website else "") or parsed.netloc.removeprefix("www.")
    if website is None:
        website = Website(url=normalized_url, company_name=company_name)
        db.add(website)
    else:
        website.url = normalized_url
        website.company_name = company_name
    for key in ["company_place", "region", "logo_url"]:
        value = (payload.get(key) or detected.get(key) or "").strip()
        if value:
            setattr(website, key, value)
    db.commit()
    db.refresh(website)
    return website, created, detection_error


@router.post("/tools/list_websites")
def list_websites(_: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    return {
        "websites": [
            {
                "id": item.id,
                "url": item.url,
                "company_name": item.company_name,
                "company_place": item.company_place,
                "region": item.region,
                "logo_url": item.logo_url,
            }
            for item in db.query(Website).all()
        ]
    }


@router.post("/tools/upsert_website")
async def upsert_website(payload: dict[str, Any], principal: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    if isinstance(principal, ApiPrincipal):
        require_principal_scope(principal, ApiTokenScope.execute)
    website, created, detection_error = await _upsert_website_from_payload(payload, db)
    result = {"created": created, "website": _serialize_website(website)}
    if detection_error:
        result["profile_detection_error"] = detection_error
    return result


@router.post("/tools/start_scan")
def start_scan(website_id: int, principal: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    if isinstance(principal, ApiPrincipal):
        require_principal_scope(principal, ApiTokenScope.execute)
    website = db.get(Website, website_id)
    if not website:
        return {"error": "Website not found"}
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return _serialize_scan(scan)


@router.post("/tools/scan_and_analyze_website")
async def scan_and_analyze_website(payload: dict[str, Any], principal: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    if isinstance(principal, ApiPrincipal):
        require_principal_scope(principal, ApiTokenScope.execute)
    website, _, detection_error = await _upsert_website_from_payload(payload, db)
    scan = ScanJob(website_id=website.id, auto_analyze=True, message="Queued for scan and analysis")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    result = {"website": _serialize_website(website), "scan": _serialize_scan(scan), "analysis": None}
    if detection_error:
        result["profile_detection_error"] = detection_error
    return result


@router.post("/tools/get_scan_status")
def get_scan_status(scan_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        return {"error": "Scan not found"}
    return _serialize_scan(scan)


@router.post("/tools/get_scan_analysis_status")
def get_scan_analysis_status(scan_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        return {"error": "Scan not found"}
    website = db.get(Website, scan.website_id)
    analysis = db.get(AnalysisRun, scan.analysis_run_id) if scan.analysis_run_id else _latest_analysis(db, scan.website_id)
    analysis_payload = serialize_analysis_run(analysis) if analysis else None
    scan_status = _status_value(scan.status)
    analysis_status = analysis_payload["status"] if analysis_payload else ""
    return {
        "website": _serialize_website(website) if website else None,
        "scan": _serialize_scan(scan),
        "analysis": analysis_payload,
        "ready": scan_status in {"failed", "stopped"} or (scan_status == "completed" and (not scan.auto_analyze or analysis_status in {"completed", "failed"})),
    }


@router.post("/tools/search_company_data")
async def search_company_data(payload: SearchRequest, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    return {"results": await semantic_search(db, payload.query, payload.website_id, payload.limit)}


@router.post("/tools/get_company_profile")
def get_company_profile(website_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, website_id)
    if not website:
        return {"error": "Website not found"}
    return {
        "id": website.id,
        "url": website.url,
        "company_name": website.company_name,
        "logo_url": website.logo_url,
        "documents": [
            {"id": doc.id, "title": doc.title, "url": doc.source_url, "summary": doc.summary}
            for doc in website.documents
        ],
    }


@router.post("/tools/list_analysis_prompts")
def list_analysis_prompts(_: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    seed_default_analysis_prompts(db)
    prompts = db.query(AnalysisPrompt).order_by(AnalysisPrompt.sort_order, AnalysisPrompt.prompt_id).all()
    return {
        "prompts": [
            {
                "prompt_id": prompt.prompt_id,
                "title": prompt.title,
                "description": prompt.description,
                "sort_order": prompt.sort_order,
                "is_system_prompt": prompt.is_system_prompt,
                "updated_at": prompt.updated_at,
            }
            for prompt in prompts
        ]
    }


@router.post("/tools/run_company_analysis")
async def run_company_analysis(website_id: int, principal: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    if isinstance(principal, ApiPrincipal):
        require_principal_scope(principal, ApiTokenScope.execute)
    if not db.get(Website, website_id):
        return {"error": "Website not found"}
    return serialize_analysis_run(await AnalysisService(db).run_company_analysis(website_id))


@router.post("/tools/get_company_analysis")
def get_company_analysis(analysis_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    run = db.get(AnalysisRun, analysis_id)
    if not run:
        return {"error": "Analysis not found"}
    return serialize_analysis_run(run)


@router.post("/tools/generate_company_scenarios")
def generate_company_scenarios(website_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    run = _latest_analysis(db, website_id)
    if not run:
        return {"error": "Analysis not found"}
    jobs = serialize_analysis_run(run)["jobs"]
    return {
        "website_id": website_id,
        "analysis_id": run.id,
        "scenarios": [
            {
                "title": job["prompt_id"].replace("_", " ").title(),
                "input": job["summary"],
                "source_prompt": job["prompt_id"],
            }
            for job in jobs
            if job["prompt_id"] in {"job_3_uitdagingen", "job_4_waardekansen", "job_8_marktcontext", "job_9_technologie_indicaties"}
        ],
    }


@router.post("/tools/generate_poc_brief")
def generate_poc_brief(website_id: int, _: ApiPrincipal = Depends(require_mcp_principal), db: Session = Depends(get_db)) -> dict:
    run = _latest_analysis(db, website_id)
    if not run:
        return {"error": "Analysis not found"}
    data = serialize_analysis_run(run)
    jobs = {job["prompt_id"]: job for job in data["jobs"]}
    return {
        "website_id": website_id,
        "analysis_id": run.id,
        "brief": {
            "bedrijf": data["extracted_variables"].get("Bedrijfsnaam", ""),
            "plaats": data["extracted_variables"].get("Bedrijfsplaats", ""),
            "regio": data["extracted_variables"].get("Regio", ""),
            "profiel": jobs.get("job_2_bedrijfsprofiel", {}).get("summary", ""),
            "uitdagingen": jobs.get("job_3_uitdagingen", {}).get("summary", ""),
            "waardekansen": jobs.get("job_4_waardekansen", {}).get("summary", ""),
            "technische_haakjes": jobs.get("job_9_technologie_indicaties", {}).get("summary", ""),
        },
    }


def _latest_analysis(db: Session, website_id: int) -> AnalysisRun | None:
    return (
        db.query(AnalysisRun)
        .filter(AnalysisRun.website_id == website_id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
