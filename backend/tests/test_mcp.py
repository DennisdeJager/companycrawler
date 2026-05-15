import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import mcp
from app.core.database import Base
from app.models import AnalysisRun, ScanJob, Website
from app.models.entities import ApiTokenScope, ScanStatus
from app.services.auth import ApiPrincipal


@pytest.mark.asyncio
async def test_mcp_initialize_returns_tool_capability() -> None:
    response = await mcp._json_rpc_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        },
        db=None,
    )

    assert response["result"]["protocolVersion"] == "2025-06-18"
    assert response["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert response["result"]["serverInfo"]["name"] == "companycrawler"


@pytest.mark.asyncio
async def test_mcp_tools_list_includes_json_schemas_and_annotations() -> None:
    response = await mcp._json_rpc_response({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, db=None)

    tools = response["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert {
        "list_websites",
        "upsert_website",
        "start_scan",
        "scan_and_analyze_website",
        "get_scan_status",
        "get_scan_analysis_status",
        "search_company_data",
        "get_company_profile",
        "list_analysis_prompts",
        "run_company_analysis",
        "get_company_analysis",
        "generate_company_scenarios",
        "generate_poc_brief",
    } <= tool_names
    assert all("inputSchema" in tool for tool in tools)
    assert all("annotations" in tool for tool in tools)


@pytest.mark.asyncio
async def test_mcp_tools_call_returns_structured_content(monkeypatch) -> None:
    def fake_list_websites(db):
        return {"websites": [{"id": 1, "url": "https://example.com", "company_name": "Example", "logo_url": ""}]}

    monkeypatch.setattr(mcp, "list_websites", fake_list_websites)

    response = await mcp._json_rpc_response(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_websites", "arguments": {}},
        },
        db=None,
    )

    result = response["result"]
    assert result["structuredContent"]["websites"][0]["company_name"] == "Example"
    assert result["content"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_mcp_read_token_cannot_execute_tools() -> None:
    response = await mcp._json_rpc_response(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "start_scan", "arguments": {"website_id": 1}},
        },
        db=None,
        principal=ApiPrincipal(kind="api_token", name="readonly", scope=ApiTokenScope.read),
    )

    assert response["error"]["code"] == -32001
    assert "scope" in response["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_json_rpc_returns_parse_error_for_invalid_json() -> None:
    class BadJsonRequest:
        async def json(self):
            raise mcp.json.JSONDecodeError("Invalid escape", "{}", 0)

    response = await mcp.json_rpc(BadJsonRequest(), db=None)

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error: invalid JSON"},
    }


def make_mcp_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.mark.asyncio
async def test_upsert_website_creates_record_without_profile_detection() -> None:
    db = make_mcp_session()

    result = await mcp.upsert_website(
        {"url": "example.com", "company_name": "Example BV", "detect_profile": False},
        principal=ApiPrincipal(kind="api_token", name="execute", scope=ApiTokenScope.execute),
        db=db,
    )

    assert result["created"] is True
    assert result["website"]["url"] == "https://example.com/"
    assert result["website"]["company_name"] == "Example BV"
    assert db.query(Website).count() == 1


@pytest.mark.asyncio
async def test_scan_and_analyze_website_queues_auto_analysis_scan() -> None:
    db = make_mcp_session()

    result = await mcp.scan_and_analyze_website(
        {"url": "https://example.com", "company_name": "Example", "detect_profile": False},
        principal=ApiPrincipal(kind="api_token", name="execute", scope=ApiTokenScope.execute),
        db=db,
    )

    scan = db.get(ScanJob, result["scan"]["id"])
    assert result["website"]["id"] == scan.website_id
    assert scan.auto_analyze is True
    assert result["analysis"] is None


def test_get_scan_analysis_status_returns_linked_analysis() -> None:
    db = make_mcp_session()
    website = Website(url="https://example.com/", company_name="Example")
    db.add(website)
    db.commit()
    db.refresh(website)
    analysis = AnalysisRun(website_id=website.id, status="completed")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    scan = ScanJob(website_id=website.id, status=ScanStatus.completed, auto_analyze=True, analysis_run_id=analysis.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)

    result = mcp.get_scan_analysis_status(scan.id, db=db)

    assert result["analysis"]["id"] == analysis.id
    assert result["ready"] is True
