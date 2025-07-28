import pytest
from fastmcp import FastMCP
from tools.ch import register_ch_tools

@pytest.fixture
def mcp():
    return FastMCP("test-ch")

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.ch.fetch_json", dummy)
    return dummy

class TestCHTools:

    @pytest.mark.unit
    async def test_ch_search_connections(self, mcp):
        tools = register_ch_tools(mcp)
        fn = next(t for t in tools if t.name == "ch_search_connections")
        result = await fn.fn("Bern", "Zurich")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_search_stations(self, mcp):
        fn = next(t for t in register_ch_tools(mcp) if t.name == "ch_search_stations")
        result = await fn.fn("Bern")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_get_departures(self, mcp):
        fn = next(t for t in register_ch_tools(mcp) if t.name == "ch_get_departures")
        result = await fn.fn("Zurich HB", limit=5)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_nearby_stations(self, mcp):
        fn = next(t for t in register_ch_tools(mcp) if t.name == "ch_nearby_stations")
        result = await fn.fn(47.37, 8.54, distance=500)
        assert result == {"dummy": True}
