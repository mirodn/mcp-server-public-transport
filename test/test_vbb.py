import pytest
from fastmcp import FastMCP
from tools.vbb import register_vbb_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-vbb")
    register_vbb_tools(server)
    return server

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.vbb.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestVBBTools:

    @pytest.mark.unit
    async def test_vbb_search_locations(self, mcp):
        fn = await get_tool(mcp, "vbb_search_locations")
        result = await fn.fn("Alexanderplatz")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_get_departures(self, mcp):
        fn = await get_tool(mcp, "vbb_get_departures")
        result = await fn.fn("900100003", results=5)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_get_arrivals(self, mcp):
        fn = await get_tool(mcp, "vbb_get_arrivals")
        result = await fn.fn("900100003", duration=10)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_search_journeys(self, mcp):
        fn = await get_tool(mcp, "vbb_search_journeys")
        result = await fn.fn("900100003", "900017101", results=3)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "vbb_nearby_stations")
        result = await fn.fn(52.521508, 13.411267, results=8)
        assert result == {"dummy": True}
