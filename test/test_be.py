import pytest
from fastmcp import FastMCP
from tools.be import register_be_tools

@pytest.fixture
def mcp():
    return FastMCP("test-be")

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.be.fetch_json", dummy)
    return dummy

class TestBETools:

    @pytest.mark.unit
    async def test_be_search_connections(self, mcp):
        fn = next(t for t in register_be_tools(mcp) if t.name == "be_search_connections")
        result = await fn.fn("Brussels", "Antwerp")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_search_stations(self, mcp):
        fn = next(t for t in register_be_tools(mcp) if t.name == "be_search_stations")
        result = await fn.fn("Brussels")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_get_departures(self, mcp):
        fn = next(t for t in register_be_tools(mcp) if t.name == "be_get_departures")
        result = await fn.fn("Brussels", limit=7)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_get_vehicle(self, mcp):
        fn = next(t for t in register_be_tools(mcp) if t.name == "be_get_vehicle")
        result = await fn.fn("IC531")
        assert result == {"dummy": True}
