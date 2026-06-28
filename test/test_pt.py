import pytest
from fastmcp import FastMCP
from tools.pt import register_pt_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-pt")
    register_pt_tools(server)
    return server

# geocode/reverse-geocode return a list, plan/stoptimes return a dict.
# the tools filter geocode hits down to PT, so feed a mixed list to check scoping.
GEOCODE = [
    {"type": "STOP", "id": "pt-Metro-Lisboa_MP", "name": "Marquês de Pombal", "country": "PT"},
    {"type": "STOP", "id": "it-trenitalia_x", "name": "Elmas Aeroporto", "country": "IT"},
]

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        if "geocode" in url:
            return GEOCODE
        return {"dummy": True}
    monkeypatch.setattr("tools.pt.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestPTTools:

    @pytest.mark.unit
    async def test_pt_search_stations(self, mcp):
        fn = await get_tool(mcp, "pt_search_stations")
        result = await fn.fn("Marques de Pombal")
        # non-PT hits are dropped
        assert result == [GEOCODE[0]]

    @pytest.mark.unit
    async def test_pt_search_connections(self, mcp):
        fn = await get_tool(mcp, "pt_search_connections")
        result = await fn.fn("pt-Metro-Lisboa_MP", "pt-Metro-Lisboa_BC", limit=3)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_pt_get_departures(self, mcp):
        fn = await get_tool(mcp, "pt_get_departures")
        result = await fn.fn("pt-Metro-Porto_5726", limit=5)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_pt_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "pt_nearby_stations")
        result = await fn.fn(41.15228, -8.609299, results=8)
        assert result == [GEOCODE[0]]
