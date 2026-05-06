import pytest
from fastmcp import FastMCP
from tools.ch import register_ch_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-ch")
    register_ch_tools(server)
    return server

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.ch.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestCHTools:

    @pytest.mark.unit
    async def test_ch_search_connections(self, mcp):
        fn = await get_tool(mcp, "ch_search_connections")
        result = await fn.fn("Bern", "Zurich")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_search_stations(self, mcp):
        fn = await get_tool(mcp, "ch_search_stations")
        result = await fn.fn("Bern")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_get_departures(self, mcp):
        fn = await get_tool(mcp, "ch_get_departures")
        result = await fn.fn("Zurich HB", limit=5)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "ch_nearby_stations")
        result = await fn.fn(47.37, 8.54, distance=500)
        assert result == {"dummy": True}
