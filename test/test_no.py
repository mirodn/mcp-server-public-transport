import pytest
from fastmcp import FastMCP

from core.base import TransportAPIError
from tools.no import register_no_tools


@pytest.fixture
def mcp():
    server = FastMCP("test-no")
    register_no_tools(server)
    return server

@pytest.fixture
def calls():
    return []

@pytest.fixture(autouse=True)
def mock_http(monkeypatch, calls):
    async def dummy_fetch(url, params, headers=None):
        calls.append(("GET", url, params, headers))
        return {"features": []}

    async def dummy_post(url, body, headers=None):
        calls.append(("POST", url, body, headers))
        return {"data": {"dummy": True}}

    monkeypatch.setattr("tools.no.fetch_json", dummy_fetch)
    monkeypatch.setattr("tools.no.post_json", dummy_post)

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestNOTools:

    @pytest.mark.unit
    async def test_no_search_places(self, mcp, calls):
        fn = await get_tool(mcp, "no_search_places")
        result = await fn.fn("Oslo S", size=5)
        assert result == {"features": []}
        _, _, params, headers = calls[0]
        assert params == {"text": "Oslo S", "lang": "en", "size": 5}
        # Entur rejects requests without a client name
        assert "ET-Client-Name" in headers

    @pytest.mark.unit
    async def test_no_stop_departures(self, mcp, calls):
        fn = await get_tool(mcp, "no_stop_departures")
        result = await fn.fn("NSR:StopPlace:58368", limit=5)
        assert result == {"dummy": True}
        assert calls[0][2]["variables"] == {"id": "NSR:StopPlace:58368", "limit": 5}

    @pytest.mark.unit
    async def test_no_trip(self, mcp, calls):
        fn = await get_tool(mcp, "no_trip")
        result = await fn.fn("NSR:StopPlace:58368", "NSR:StopPlace:337", results=3)
        assert result == {"dummy": True}
        assert calls[0][2]["variables"]["results"] == 3

    @pytest.mark.unit
    async def test_no_nearest_stops(self, mcp):
        fn = await get_tool(mcp, "no_nearest_stops")
        result = await fn.fn(59.91, 10.75, radius=300)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_graphql_errors_raise(self, mcp, monkeypatch):
        async def failing_post(url, body, headers=None):
            return {"errors": [{"message": "boom"}]}
        monkeypatch.setattr("tools.no.post_json", failing_post)

        fn = await get_tool(mcp, "no_stop_departures")
        with pytest.raises(TransportAPIError, match="boom"):
            await fn.fn("NSR:StopPlace:58368")
