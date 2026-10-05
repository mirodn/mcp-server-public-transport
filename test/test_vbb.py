import pytest
from fastmcp import FastMCP
from tools.vbb import register_vbb_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-vbb")
    register_vbb_tools(server)
    return server

ALEX = {"type": "stop", "id": "900100003", "name": "S+U Alexanderplatz Bhf (Berlin)"}
HBF = {"type": "stop", "id": "900003201", "name": "S+U Berlin Hauptbahnhof"}
HBF_DEEP = {"type": "stop", "id": "900003200", "name": "S+U Berlin Hauptbahnhof [Gleis 1-8]"}
SUEDKREUZ = {"type": "stop", "id": "900058101", "name": "S Südkreuz Bhf (Berlin)"}

S3 = {"name": "S3", "productName": "S", "operator": {"name": "S-Bahn Berlin GmbH"}, "color": {"bg": "#0079f2"}}
WARNING = {"type": "warning", "summary": "Störung.", "text": "Bauarbeiten <a href=\"x\">Info</a>"}
HINT = {"type": "hint", "code": "FK", "text": "Bicycle conveyance"}

# trimmed v6.vbb.transport.rest payloads
DEPARTURES = {
    "departures": [
        {"stop": ALEX, "when": None, "plannedWhen": "2026-10-05T10:12:00+02:00", "platform": None,
         "plannedPlatform": "3", "direction": "S Erkner Bhf", "line": S3, "cancelled": True,
         "remarks": [HINT, WARNING, WARNING]},
        {"stop": ALEX, "when": "2026-10-05T10:14:00+02:00", "plannedWhen": "2026-10-05T10:11:00+02:00",
         "platform": "Pos. 15", "plannedPlatform": "Pos. 15", "direction": "S Hackescher Markt",
         "line": {"name": "M4", "productName": "Tram", "operator": {"name": "BVG"}}, "remarks": []},
    ],
    "realtimeDataUpdatedAt": 1791187860,
}

JOURNEYS = {
    "journeys": [
        {"legs": [
            {"origin": ALEX, "destination": HBF, "plannedDeparture": "2026-10-05T10:13:00+02:00",
             "departure": "2026-10-05T10:13:00+02:00", "plannedArrival": "2026-10-05T10:19:00+02:00",
             "arrival": "2026-10-05T10:20:00+02:00", "plannedDeparturePlatform": "3",
             "departurePlatform": "4", "line": S3, "direction": "S Westkreuz", "remarks": [WARNING]},
            {"origin": HBF, "destination": HBF_DEEP, "plannedDeparture": "2026-10-05T10:19:00+02:00",
             "plannedArrival": "2026-10-05T10:24:00+02:00", "walking": True, "distance": 120},
            {"origin": HBF_DEEP, "destination": SUEDKREUZ, "plannedDeparture": "2026-10-05T10:29:00+02:00",
             "departure": "2026-10-05T10:39:00+02:00", "plannedArrival": "2026-10-05T10:33:00+02:00",
             "line": {"name": "ICE 507", "productName": "ICE"}, "direction": "München Hbf"},
        ]},
    ],
}

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params, **kwargs):
        if url.endswith("/departures"):
            return DEPARTURES
        if url.endswith("/journeys"):
            return JOURNEYS
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
        assert result["station"] == {"id": "900100003", "name": "S+U Alexanderplatz Bhf (Berlin)"}

        cancelled, tram = result["departures"]
        assert cancelled == {
            "line": "S3",
            "category": "S",
            "destination": "S Erkner Bhf",
            "planned": "2026-10-05T10:12:00+02:00",
            "platform": "3",
            "cancelled": True,
            "operator": "S-Bahn Berlin GmbH",
            # only warnings, deduplicated, without HTML
            "remarks": ["Bauarbeiten Info"],
        }
        assert tram["delay_min"] == 3
        assert "cancelled" not in tram

    @pytest.mark.unit
    async def test_vbb_get_departures_raw(self, mcp):
        fn = await get_tool(mcp, "vbb_get_departures")
        assert await fn.fn("900100003", raw=True) == DEPARTURES

    @pytest.mark.unit
    async def test_vbb_get_arrivals(self, mcp):
        fn = await get_tool(mcp, "vbb_get_arrivals")
        result = await fn.fn("900100003", duration=10)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_vbb_search_journeys(self, mcp):
        fn = await get_tool(mcp, "vbb_search_journeys")
        result = await fn.fn("900100003", "900058101", results=3)
        journey = result["journeys"][0]
        assert journey["departure"] == "2026-10-05T10:13:00+02:00"
        assert journey["arrival"] == "2026-10-05T10:33:00+02:00"
        assert journey["duration_min"] == 20
        # two rides, the walk in between does not count
        assert journey["transfers"] == 1

        s3, walk, ice = journey["legs"]
        assert s3["line"] == "S3"
        assert s3["departure"]["platform"] == "4"
        assert s3["arrival"]["delay_min"] == 1
        assert s3["remarks"] == ["Bauarbeiten Info"]
        assert walk["walk"] is True
        assert walk["arrival"]["stop"]["name"] == "S+U Berlin Hauptbahnhof [Gleis 1-8]"
        assert ice["departure"]["delay_min"] == 10

    @pytest.mark.unit
    async def test_vbb_search_journeys_raw(self, mcp):
        fn = await get_tool(mcp, "vbb_search_journeys")
        assert await fn.fn("900100003", "900058101", raw=True) == JOURNEYS

    @pytest.mark.unit
    async def test_vbb_nearby_stations(self, mcp):
        fn = await get_tool(mcp, "vbb_nearby_stations")
        result = await fn.fn(52.521508, 13.411267, results=8)
        assert result == {"dummy": True}
