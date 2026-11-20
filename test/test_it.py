import pytest
from fastmcp import FastMCP
from tools.it import register_it_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-it")
    register_it_tools(server)
    return server

# geocode/reverse-geocode return a list, plan/stoptimes return a dict.
# the tools filter geocode hits down to IT, so feed a mixed list to check scoping.
GEOCODE = [
    {"type": "STOP", "id": "it-trenitalia_08409:station", "name": "ROMA TERMINI", "country": "IT"},
    {"type": "STOP", "id": "pt-Metro-Lisboa_MP", "name": "Marquês de Pombal", "country": "PT"},
]

# MOTIS answers in UTC; Rome is UTC+1 in November (CET)
STOPTIMES = {
    "place": {"name": "ROMA TERMINI", "stopId": "it-trenitalia_08409:station"},
    "stopTimes": [
        {"place": {"name": "ROMA TERMINI", "stopId": "it-trenitalia_08409",
                   "parentId": "it-trenitalia_08409:station",
                   "scheduledDeparture": "2026-11-20T10:50:00Z", "departure": "2026-11-20T10:52:00Z",
                   "track": "9"},
         "mode": "HIGHSPEED_RAIL", "realTime": True, "headsign": "MILANO CENTRALE", "displayName": "FR 9630",
         "routeShortName": "FR 9630", "agencyName": "TRENITALIA", "cancelled": False, "tripCancelled": False},
        {"place": {"name": "ROMA TERMINI", "stopId": "it-trenitalia_08409",
                   "parentId": "it-trenitalia_08409:station",
                   "scheduledDeparture": "2026-11-20T10:54:00Z", "departure": "2026-11-20T10:54:00Z",
                   "track": "21"},
         "mode": "REGIONAL_RAIL", "realTime": False, "headsign": "FRASCATI", "displayName": "REG 20073",
         "agencyName": "TRENITALIA", "cancelled": False, "tripCancelled": True},
    ],
}

PLAN = {
    "itineraries": [{
        "duration": 11280, "transfers": 1,
        "startTime": "2026-11-20T10:50:00Z", "endTime": "2026-11-20T14:00:00Z",
        "legs": [
            {"mode": "WALK", "realTime": False,
             "from": {"name": "START", "departure": "2026-11-20T10:50:00Z", "scheduledDeparture": "2026-11-20T10:50:00Z"},
             "to": {"name": "ROMA TERMINI", "stopId": "it-trenitalia_08409",
                    "arrival": "2026-11-20T10:52:00Z", "scheduledArrival": "2026-11-20T10:52:00Z"}},
            {"mode": "HIGHSPEED_RAIL", "realTime": True, "headsign": "MILANO CENTRALE", "displayName": "FR 9630",
             "from": {"name": "ROMA TERMINI", "stopId": "it-trenitalia_08409",
                      "departure": "2026-11-20T10:54:00Z", "scheduledDeparture": "2026-11-20T10:52:00Z"},
             "to": {"name": "MILANO CENTRALE", "stopId": "it-trenitalia_01700", "parentId": "it-trenitalia_01700:station",
                    "arrival": "2026-11-20T14:00:00Z", "scheduledArrival": "2026-11-20T13:58:00Z"}},
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
    monkeypatch.setattr("tools.it.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestITTools:

    @pytest.mark.unit
    async def test_it_search_stations(self, mcp):
        fn = await get_tool(mcp, "it_search_stations")
        result = await fn.fn("Roma Termini")
        # non-IT hits are dropped
        assert result == [GEOCODE[0]]

    @pytest.mark.unit
    async def test_it_search_connections(self, mcp):
        fn = await get_tool(mcp, "it_search_connections")
        result = await fn.fn("it-trenitalia_08409:station", "it-trenitalia_01700:station", limit=3)
        journey = result["journeys"][0]
        assert journey["departure"] == "2026-11-20T11:50:00+01:00"
        assert journey["arrival"] == "2026-11-20T14:58:00+01:00"
        assert journey["transfers"] == 1

        walk, rail = journey["legs"]
        assert walk["walk"] is True
        assert walk["departure"]["stop"] == {"name": "START"}
        assert rail["line"] == "FR 9630"
        assert rail["category"] == "Highspeed_Rail"
        assert rail["direction"] == "MILANO CENTRALE"
        assert rail["departure"]["delay_min"] == 2
        # platform-level stop ids are mapped to the parent stop the tools accept
        assert rail["arrival"]["stop"] == {"id": "it-trenitalia_01700:station", "name": "MILANO CENTRALE"}

    @pytest.mark.unit
    async def test_it_search_connections_raw(self, mcp):
        fn = await get_tool(mcp, "it_search_connections")
        assert await fn.fn("it-trenitalia_08409:station", "it-trenitalia_01700:station", raw=True) == PLAN

    @pytest.mark.unit
    async def test_it_get_departures(self, mcp):
        fn = await get_tool(mcp, "it_get_departures")
        result = await fn.fn("it-trenitalia_08409:station", limit=5)
        assert result["station"] == {"id": "it-trenitalia_08409:station", "name": "ROMA TERMINI"}
        live, cancelled = result["departures"]
        assert live == {
            "line": "FR 9630",
            "category": "Highspeed_Rail",
            "destination": "MILANO CENTRALE",
            "planned": "2026-11-20T11:50:00+01:00",
            "expected": "2026-11-20T11:52:00+01:00",
            "delay_min": 2,
            "platform": "9",
            "operator": "TRENITALIA",
        }
        assert "expected" not in cancelled
        assert cancelled["cancelled"] is True

    @pytest.mark.unit
    async def test_it_get_departures_trims_to_limit(self, mcp):
        # MOTIS treats n as a minimum and may return more
        fn = await get_tool(mcp, "it_get_departures")
        result = await fn.fn("it-trenitalia_08409:station", limit=1)
        assert len(result["departures"]) == 1

    @pytest.mark.unit
    async def test_it_get_departures_raw(self, mcp):
        fn = await get_tool(mcp, "it_get_departures")
        assert await fn.fn("it-trenitalia_08409:station", raw=True) == STOPTIMES

    @pytest.mark.unit
    async def test_it_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "it_nearby_stations")
        result = await fn.fn(41.90050, 12.50203, results=8)
        assert result == [GEOCODE[0]]
