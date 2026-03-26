import pytest
from fastmcp import FastMCP
from tools.vbb import register_vbb_tools

@pytest.fixture
def mcp():
    return FastMCP("test-vbb")

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.vbb.fetch_json", dummy)
    return dummy

class TestVBBTools:

    @pytest.mark.unit
    async def test_vbb_search_locations(self, mcp):
        tools = register_vbb_tools(mcp)
        fn = next(t for t in tools if t.name == "vbb_search_locations")
        result = await fn.fn("Alexanderplatz")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_get_departures(self, mcp):
        fn = next(t for t in register_vbb_tools(mcp) if t.name == "vbb_get_departures")
        result = await fn.fn("900100003", results=5)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_get_arrivals(self, mcp):
        fn = next(t for t in register_vbb_tools(mcp) if t.name == "vbb_get_arrivals")
        result = await fn.fn("900100003", duration=10)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_search_journeys(self, mcp):
        fn = next(t for t in register_vbb_tools(mcp) if t.name == "vbb_search_journeys")
        result = await fn.fn("900100003", "900017101", results=3)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_nearby_stations(self, mcp):
        fn = next(t for t in register_vbb_tools(mcp) if t.name == "vbb_nearby_stations")
        result = await fn.fn(52.521508, 13.411267, results=8)
        assert result == {"dummy": True}
