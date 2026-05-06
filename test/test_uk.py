import pytest
from fastmcp import FastMCP
from tools.uk import register_uk_tools, TransportAPIError

@pytest.fixture
def mcp():
    server = FastMCP("test-uk")
    register_uk_tools(server)
    return server

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.uk.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestUKTools:

    @pytest.mark.unit
    async def test_uk_live_departures_invalid_code(self, mcp):
        fn = await get_tool(mcp, "uk_live_departures")
        with pytest.raises(ValueError):
            await fn.fn("AB")  # too short

    @pytest.mark.unit
    async def test_uk_live_departures_no_credentials(self, mcp, monkeypatch):
        monkeypatch.delenv("UK_TRANSPORT_APP_ID", raising=False)
        monkeypatch.delenv("UK_TRANSPORT_API_KEY", raising=False)
        fn = await get_tool(mcp, "uk_live_departures")
        with pytest.raises(TransportAPIError):
            await fn.fn("PAD")

    @pytest.mark.unit
    async def test_uk_live_departures_success(self, mcp, monkeypatch):
        monkeypatch.setenv("UK_TRANSPORT_APP_ID", "app")
        monkeypatch.setenv("UK_TRANSPORT_API_KEY", "key")
        fn = await get_tool(mcp, "uk_live_departures")
        result = await fn.fn("PAD")
        assert result == {"dummy": True}
