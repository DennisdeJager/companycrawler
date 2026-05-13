from collections.abc import Callable
import inspect
import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ScanJob, Website
from app.schemas.dto import SearchRequest
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
    payload = await request.json()
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
