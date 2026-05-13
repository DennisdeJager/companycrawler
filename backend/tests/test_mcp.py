import pytest

from app.api import mcp


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
        "start_scan",
        "get_scan_status",
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
