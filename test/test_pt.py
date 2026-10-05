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

# MOTIS answers in UTC; Lisbon is UTC+1 in October
STOPTIMES = {
    "place": {"name": "Trindade", "stopId": "pt-Metro-Porto_5726"},
    "stopTimes": [
        {"place": {"name": "Trindade", "stopId": "pt-Metro-Porto_5726",
                   "scheduledDeparture": "2026-10-05T08:27:00Z", "departure": "2026-10-05T08:29:00Z"},
         "mode": "SUBWAY", "realTime": True, "headsign": "Póvoa de Varzim", "displayName": "Bx",
         "routeShortName": "Bx", "agencyName": "Metro do Porto", "cancelled": False, "tripCancelled": False},
        {"place": {"name": "Trindade", "stopId": "pt-Metro-Porto_5726",
                   "scheduledDeparture": "2026-10-05T08:30:00Z", "departure": "2026-10-05T08:30:00Z"},
         "mode": "SUBWAY", "realTime": False, "headsign": "Vila d'Este", "displayName": "D",
         "agencyName": "Metro do Porto", "cancelled": False, "tripCancelled": True},
    ],
}

PLAN = {
    "itineraries": [{
        "duration": 1080, "transfers": 1,
        "startTime": "2026-10-05T08:30:00Z", "endTime": "2026-10-05T08:48:00Z",
        "legs": [
            {"mode": "WALK", "realTime": False,
             "from": {"name": "START", "departure": "2026-10-05T08:30:00Z", "scheduledDeparture": "2026-10-05T08:30:00Z"},
             "to": {"name": "Arco Cego", "stopId": "pt-Carris_11105",
                    "arrival": "2026-10-05T08:34:00Z", "scheduledArrival": "2026-10-05T08:34:00Z"}},
            {"mode": "BUS", "realTime": True, "headsign": "Sapadores", "displayName": "726",
             "from": {"name": "Arco Cego", "stopId": "pt-Carris_11105",
                      "departure": "2026-10-05T08:37:00Z", "scheduledDeparture": "2026-10-05T08:35:00Z"},
             "to": {"name": "Anjos", "stopId": "pt-Metro-Lisboa_AN1", "parentId": "pt-Metro-Lisboa_AN",
                    "arrival": "2026-10-05T08:48:00Z", "scheduledArrival": "2026-10-05T08:46:00Z"}},
        ],
    }],
}

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params, **kwargs):
        if "geocode" in url:
            return GEOCODE
        if url.endswith("/stoptimes"):
            return STOPTIMES
        if url.endswith("/plan"):
            return PLAN
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
        result = await fn.fn("38.7369,-9.1427", "pt-Metro-Lisboa_AN", limit=3)
        journey = result["journeys"][0]
        assert journey["departure"] == "2026-10-05T09:30:00+01:00"
        assert journey["arrival"] == "2026-10-05T09:46:00+01:00"
        assert journey["transfers"] == 1

        walk, bus = journey["legs"]
        assert walk["walk"] is True
        assert walk["departure"]["stop"] == {"name": "START"}
        assert bus["line"] == "726"
        assert bus["category"] == "Bus"
        assert bus["direction"] == "Sapadores"
        assert bus["departure"]["delay_min"] == 2
        # platform-level stop ids are mapped to the parent stop the tools accept
        assert bus["arrival"]["stop"] == {"id": "pt-Metro-Lisboa_AN", "name": "Anjos"}

    @pytest.mark.unit
    async def test_pt_search_connections_raw(self, mcp):
        fn = await get_tool(mcp, "pt_search_connections")
        assert await fn.fn("pt-Metro-Lisboa_MP", "pt-Metro-Lisboa_BC", raw=True) == PLAN

    @pytest.mark.unit
    async def test_pt_get_departures(self, mcp):
        fn = await get_tool(mcp, "pt_get_departures")
        result = await fn.fn("pt-Metro-Porto_5726", limit=5)
        assert result["station"] == {"id": "pt-Metro-Porto_5726", "name": "Trindade"}
        live, cancelled = result["departures"]
        assert live == {
            "line": "Bx",
            "category": "Subway",
            "destination": "Póvoa de Varzim",
            "planned": "2026-10-05T09:27:00+01:00",
            "expected": "2026-10-05T09:29:00+01:00",
            "delay_min": 2,
            "operator": "Metro do Porto",
        }
        assert "expected" not in cancelled
        assert cancelled["cancelled"] is True

    @pytest.mark.unit
    async def test_pt_get_departures_trims_to_limit(self, mcp):
        # MOTIS treats n as a minimum and may return more
        fn = await get_tool(mcp, "pt_get_departures")
        result = await fn.fn("pt-Metro-Porto_5726", limit=1)
        assert len(result["departures"]) == 1

    @pytest.mark.unit
    async def test_pt_get_departures_raw(self, mcp):
        fn = await get_tool(mcp, "pt_get_departures")
        assert await fn.fn("pt-Metro-Porto_5726", raw=True) == STOPTIMES

    @pytest.mark.unit
    async def test_pt_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "pt_nearby_stations")
        result = await fn.fn(41.15228, -8.609299, results=8)
        assert result == [GEOCODE[0]]
