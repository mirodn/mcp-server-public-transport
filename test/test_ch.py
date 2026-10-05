import pytest
from fastmcp import FastMCP
from tools.ch import register_ch_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-ch")
    register_ch_tools(server)
    return server

def checkpoint(station_id, name, kind, planned, expected=None, platform=None, new_platform=None):
    return {
        "station": {"id": station_id, "name": name, "coordinate": {"x": 1, "y": 2}},
        kind: planned,
        "delay": None,
        "platform": platform,
        "prognosis": {kind: expected, "platform": new_platform},
    }

# trimmed transport.opendata.ch payloads; real ones are ~10x larger
STATIONBOARD = {
    "station": {"id": "8503000", "name": "Zürich HB"},
    "stationboard": [
        {
            "stop": checkpoint("8503000", "Zürich HB", "departure",
                               "2026-10-05T10:12:00+0200", "2026-10-05T10:36:00+0200", "33"),
            "category": "S", "number": "14", "operator": "SBB", "to": "Hinwil",
            "passList": [{"huge": True}],
        },
        {
            "stop": checkpoint("8503000", "Zürich HB", "departure", "2026-10-05T10:33:00+0200"),
            "category": "EC", "number": "000019", "operator": "SBB", "to": "Milano Centrale",
        },
    ],
}

CONNECTIONS = {
    "connections": [
        {
            # journey-level times include delays; output must use the schedule
            "from": {"departure": "2026-10-05T10:27:00+0200"},
            "to": {"arrival": "2026-10-05T10:52:00+0200"},
            "duration": "00d00:25:00",
            "transfers": 0,
            "sections": [
                {
                    "journey": {"category": "S", "number": "14", "to": "Hinwil"},
                    "walk": None,
                    "departure": checkpoint("8503001", "Zürich Altstetten", "departure",
                                            "2026-10-05T10:05:00+0200", "2026-10-05T10:27:00+0200", "4"),
                    "arrival": checkpoint("8503125", "Uster", "arrival",
                                          "2026-10-05T10:35:00+0200", None, "2", new_platform="3"),
                },
                {
                    "journey": None,
                    "walk": {"duration": 300},
                    "departure": checkpoint("8503125", "Uster", "departure", "2026-10-05T10:35:00+0200"),
                    "arrival": checkpoint("8590001", "Uster, Bahnhof", "arrival", "2026-10-05T10:40:00+0200"),
                },
            ],
        }
    ]
}

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params, **kwargs):
        if url.endswith("/stationboard"):
            return STATIONBOARD
        if url.endswith("/connections"):
            return CONNECTIONS
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
        result = await fn.fn("Zürich Altstetten", "Uster")
        journey = result["journeys"][0]
        assert journey["departure"] == "2026-10-05T10:05:00+02:00"
        assert journey["arrival"] == "2026-10-05T10:40:00+02:00"
        assert journey["duration_min"] == 35
        assert journey["transfers"] == 0

        ride, walk = journey["legs"]
        assert ride["line"] == "S 14"
        assert ride["direction"] == "Hinwil"
        assert ride["departure"]["stop"] == {"id": "8503001", "name": "Zürich Altstetten"}
        assert ride["departure"]["delay_min"] == 22
        # changed platform from the prognosis wins
        assert ride["arrival"]["platform"] == "3"
        assert walk["walk"] is True
        assert "line" not in walk

    @pytest.mark.unit
    async def test_ch_search_connections_raw(self, mcp):
        fn = await get_tool(mcp, "ch_search_connections")
        assert await fn.fn("Bern", "Zurich", raw=True) == CONNECTIONS

    @pytest.mark.unit
    async def test_ch_search_stations(self, mcp):
        fn = await get_tool(mcp, "ch_search_stations")
        result = await fn.fn("Bern")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_ch_get_departures(self, mcp):
        fn = await get_tool(mcp, "ch_get_departures")
        result = await fn.fn("Zurich HB", limit=5)
        assert result == {
            "station": {"id": "8503000", "name": "Zürich HB"},
            "departures": [
                {
                    "line": "S 14",
                    "category": "S",
                    "destination": "Hinwil",
                    "planned": "2026-10-05T10:12:00+02:00",
                    "expected": "2026-10-05T10:36:00+02:00",
                    "delay_min": 24,
                    "platform": "33",
                    "operator": "SBB",
                },
                {
                    "line": "EC 19",
                    "category": "EC",
                    "destination": "Milano Centrale",
                    "planned": "2026-10-05T10:33:00+02:00",
                    "operator": "SBB",
                },
            ],
        }

    @pytest.mark.unit
    async def test_ch_get_departures_raw(self, mcp):
        fn = await get_tool(mcp, "ch_get_departures")
        assert await fn.fn("Zurich HB", raw=True) == STATIONBOARD

    @pytest.mark.unit
    async def test_ch_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "ch_nearby_stations")
        result = await fn.fn(47.37, 8.54, distance=500)
        assert result == {"dummy": True}
