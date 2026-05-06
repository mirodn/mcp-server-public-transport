import pytest
from fastmcp import FastMCP
from tools.be import register_be_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-be")
    register_be_tools(server)
    return server

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.be.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestBETools:

    @pytest.mark.unit
    async def test_be_search_connections(self, mcp):
        fn = await get_tool(mcp, "be_search_connections")
        result = await fn.fn("Brussels", "Antwerp")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_search_stations(self, mcp):
        fn = await get_tool(mcp, "be_search_stations")
        result = await fn.fn("Brussels")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_get_departures(self, mcp):
        fn = await get_tool(mcp, "be_get_departures")
        result = await fn.fn("Brussels", limit=7)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_get_vehicle(self, mcp):
        fn = await get_tool(mcp, "be_get_vehicle")
        result = await fn.fn("IC531")
        assert result == {"dummy": True}
