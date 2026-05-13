from collections.abc import Callable
import inspect
import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AnalysisPrompt, AnalysisRun, ScanJob, Website
from app.schemas.dto import SearchRequest
from app.services.analysis import AnalysisService, seed_default_analysis_prompts, serialize_analysis_run
from app.services.search import semantic_search

router = APIRouter(prefix="/mcp", tags=["MCP"])
MCP_PROTOCOL_VERSION = "2025-06-18"


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_websites",
            "title": "List websites",
            "description": "List known company websites and their marketing profile metadata.",
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
                                "logo_url": {"type": "string"},
                            },
                            "required": ["id", "url", "company_name", "logo_url"],
                        },
                    }
                },
                "required": ["websites"],
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "start_scan",
            "title": "Start website scan",
            "description": "Queue a public same-domain crawl for an existing website id.",
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
            "name": "get_scan_status",
            "title": "Get scan status",
            "description": "Return scan progress, status and latest worker message.",
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
            "name": "search_company_data",
            "title": "Search company data",
            "description": "Semantic search over crawled public company website content.",
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
            "description": "Return website metadata and known document summaries for a company.",
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
            "description": "List manageable default prompts for the company analysis agent jobs.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "outputSchema": {"type": "object", "properties": {"prompts": {"type": "array", "items": {"type": "object"}}}, "required": ["prompts"]},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "run_company_analysis",
            "title": "Run company analysis",
            "description": "Run the 9-step agentic company analysis chain for a website.",
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
            "description": "Return a stored company analysis run with all job results.",
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
            "description": "Return scenario-ready opportunities from the latest stored company analysis.",
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
            "description": "Return a PoC briefing based on the latest stored company analysis.",
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
        },
        "required": ["id", "status", "progress", "message"],
    }


@router.get("")
def manifest() -> dict:
    tools = _tool_descriptors()
    return {
        "name": "companycrawler",
        "description": "MCP tools for scanning public company websites and retrieving marketing profile data.",
        "protocol": "MCP",
        "protocol_version": MCP_PROTOCOL_VERSION,
        "transport": "streamable-http-json-rpc",
        "jsonrpc_endpoint": "/mcp",
        "capabilities": {"tools": {"listChanged": False}},
        "tools": tools,
    }


@router.post("")
async def json_rpc(request: Request, db: Session = Depends(get_db)) -> dict | None:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON"},
        }
    if isinstance(payload, list):
        responses = [await _json_rpc_response(item, db) for item in payload]
        return [response for response in responses if response is not None]
    return await _json_rpc_response(payload, db)


async def _handle_json_rpc(payload: dict[str, Any], db: Session) -> dict[str, Any] | None:
    method = payload.get("method")
    params = payload.get("params") or {}
    if method == "initialize":
        requested_version = params.get("protocolVersion")
        return {
            "protocolVersion": requested_version or MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "companycrawler", "title": "Companycrawler", "version": "1.0.0"},
            "instructions": "Use these tools to inspect public website crawl data, start scans, and search marketing profiles.",
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
        return await _call_tool(tool_name, arguments, db)
    raise ValueError(f"Unsupported MCP method: {method}")


async def _json_rpc_response(payload: dict[str, Any], db: Session) -> dict[str, Any] | None:
    request_id = payload.get("id")
    if request_id is None:
        return None
    try:
        result = await _handle_json_rpc(payload, db)
        if result is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except ValueError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": str(exc)}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}


async def _call_tool(tool_name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    handlers: dict[str, Callable[..., Any]] = {
        "list_websites": list_websites,
        "start_scan": start_scan,
        "get_scan_status": get_scan_status,
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
    result = await _invoke_tool(handler, arguments, db)
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


async def _invoke_tool(handler: Callable[..., Any], arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    if handler is list_websites:
        result = handler(db=db)
    elif handler is start_scan:
        result = handler(website_id=arguments.get("website_id"), db=db)
    elif handler is get_scan_status:
        result = handler(scan_id=arguments.get("scan_id"), db=db)
    elif handler is search_company_data:
        result = handler(payload=SearchRequest(**arguments), db=db)
    elif handler is get_company_profile:
        result = handler(website_id=arguments.get("website_id"), db=db)
    elif handler is list_analysis_prompts:
        result = handler(db=db)
    elif handler is run_company_analysis:
        result = handler(website_id=arguments.get("website_id"), db=db)
    elif handler is get_company_analysis:
        result = handler(analysis_id=arguments.get("analysis_id"), db=db)
    elif handler is generate_company_scenarios:
        result = handler(website_id=arguments.get("website_id"), db=db)
    elif handler is generate_poc_brief:
        result = handler(website_id=arguments.get("website_id"), db=db)
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


@router.post("/tools/list_websites")
def list_websites(db: Session = Depends(get_db)) -> dict:
    return {"websites": [{"id": item.id, "url": item.url, "company_name": item.company_name, "logo_url": item.logo_url} for item in db.query(Website).all()]}


@router.post("/tools/start_scan")
def start_scan(website_id: int, db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, website_id)
    if not website:
        return {"error": "Website not found"}
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return {"id": scan.id, "status": scan.status, "progress": scan.progress, "message": scan.message}


@router.post("/tools/get_scan_status")
def get_scan_status(scan_id: int, db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        return {"error": "Scan not found"}
    return {"id": scan.id, "status": scan.status, "progress": scan.progress, "message": scan.message}


@router.post("/tools/search_company_data")
async def search_company_data(payload: SearchRequest, db: Session = Depends(get_db)) -> dict:
    return {"results": await semantic_search(db, payload.query, payload.website_id, payload.limit)}


@router.post("/tools/get_company_profile")
def get_company_profile(website_id: int, db: Session = Depends(get_db)) -> dict:
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
def list_analysis_prompts(db: Session = Depends(get_db)) -> dict:
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
async def run_company_analysis(website_id: int, db: Session = Depends(get_db)) -> dict:
    if not db.get(Website, website_id):
        return {"error": "Website not found"}
    return serialize_analysis_run(await AnalysisService(db).run_company_analysis(website_id))


@router.post("/tools/get_company_analysis")
def get_company_analysis(analysis_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(AnalysisRun, analysis_id)
    if not run:
        return {"error": "Analysis not found"}
    return serialize_analysis_run(run)


@router.post("/tools/generate_company_scenarios")
def generate_company_scenarios(website_id: int, db: Session = Depends(get_db)) -> dict:
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
def generate_poc_brief(website_id: int, db: Session = Depends(get_db)) -> dict:
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
