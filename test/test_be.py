import pytest
from fastmcp import FastMCP
from tools.be import register_be_tools

@pytest.fixture
def mcp():
    server = FastMCP("test-be")
    register_be_tools(server)
    return server

def point(station_id, name, time, delay="0", platform="1", vehicle="IC 1810", direction=None, canceled="0"):
    return {
        "station": name,
        "stationinfo": {"id": station_id, "name": name, "locationX": "3.2"},
        "time": time,
        "delay": delay,
        "platform": platform,
        "vehicleinfo": {"shortname": vehicle, "type": vehicle.split()[0]},
        "direction": {"name": direction},
        "canceled": canceled,
        "walking": "0",
    }

# trimmed iRail payloads; times are unix seconds, delays in seconds
LIVEBOARD = {
    "station": "Ghent-Sint-Pieters",
    "stationinfo": {"id": "BE.NMBS.008892007", "name": "Ghent-Sint-Pieters"},
    "departures": {
        "number": "3",
        "departure": [
            {"station": "Oostende", "time": "1791189540", "delay": "1140", "canceled": "0",
             "platform": "?", "vehicleinfo": {"shortname": "IC 531", "type": "IC"}},
            {"station": "Antwerp-Central", "time": "1791190000", "delay": "0", "canceled": "1",
             "platform": "5", "vehicleinfo": {"shortname": "IC 731", "type": "IC"}},
            {"station": "Poperinge", "time": "1791190500", "delay": "0", "canceled": "0",
             "platform": "6", "vehicleinfo": {"shortname": "IC 709", "type": "IC"}},
        ],
    },
}

CONNECTIONS = {
    "connection": [
        {
            "departure": point("BE.NMBS.008891009", "Brugge", "1791188700", delay="120",
                               platform="9", direction="Antwerp-Central"),
            "vias": {"number": "1", "via": [{
                "arrival": point("BE.NMBS.008892007", "Ghent-Sint-Pieters", "1791190140", delay="60", platform="4"),
                "departure": point("BE.NMBS.008892007", "Ghent-Sint-Pieters", "1791190500",
                                   platform="9", vehicle="IC 410", direction="Leuven"),
            }]},
            "arrival": point("BE.NMBS.008833001", "Leuven", "1791194100", platform="4", vehicle="IC 410"),
            "duration": "5280",
            "remarks": {"number": "0", "remark": []},
            "alerts": {"number": "1", "alert": [
                {"header": "Works", "description": "Fewer trains <a href='x'>info</a>"},
            ]},
        }
    ]
}

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params, **kwargs):
        if "/liveboard/" in url:
            return LIVEBOARD
        if "/connections/" in url:
            return CONNECTIONS
        return {"dummy": True}
    monkeypatch.setattr("tools.be.fetch_json", dummy)
    return dummy

async def get_tool(mcp, name):
    tools = await mcp._list_tools()
    return next(t for t in tools if t.name == name)

class TestBETools:

    @pytest.mark.unit
    async def test_be_search_connections(self, mcp, monkeypatch):
        captured = {}

        async def capture_request(url, params, **kwargs):
            captured.update({"url": url, "params": params})
            return CONNECTIONS

        monkeypatch.setattr("tools.be.fetch_json", capture_request)
        fn = await get_tool(mcp, "be_search_connections")
        result = await fn.fn(
            "Brussels-Luxembourg", "Arlon", date="2026-08-25", time="18:00"
        )
        assert captured["params"]["date"] == "250826"
        assert captured["params"]["time"] == "1800"

        journey = result["journeys"][0]
        assert journey["departure"] == "2026-10-05T10:25:00+02:00"
        assert journey["arrival"] == "2026-10-05T11:55:00+02:00"
        assert journey["duration_min"] == 90
        assert journey["transfers"] == 1
        assert journey["remarks"] == ["Works: Fewer trains info"]

        first, second = journey["legs"]
        assert first["line"] == "IC 1810"
        assert first["direction"] == "Antwerp-Central"
        assert first["departure"]["delay_min"] == 2
        assert first["departure"]["expected"] == "2026-10-05T10:27:00+02:00"
        assert first["arrival"]["stop"] == {"id": "BE.NMBS.008892007", "name": "Ghent-Sint-Pieters"}
        assert second["line"] == "IC 410"
        assert second["departure"]["planned"] == "2026-10-05T10:55:00+02:00"
        assert second["arrival"]["stop"]["name"] == "Leuven"

    @pytest.mark.unit
    async def test_be_search_connections_raw(self, mcp):
        fn = await get_tool(mcp, "be_search_connections")
        assert await fn.fn("Brugge", "Leuven", raw=True) == CONNECTIONS

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"date": "25-08-2026"}, "Invalid date format. Use YYYY-MM-DD"),
            ({"time": "6pm"}, "Invalid time format. Use HH:MM"),
        ],
    )
    async def test_be_search_connections_rejects_invalid_datetime(
        self, mcp, kwargs, message
    ):
        fn = await get_tool(mcp, "be_search_connections")
        with pytest.raises(ValueError, match=message):
            await fn.fn("Brussels-Luxembourg", "Arlon", **kwargs)

    @pytest.mark.unit
    async def test_be_search_stations(self, mcp):
        fn = await get_tool(mcp, "be_search_stations")
        result = await fn.fn("Brussels")
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_be_get_departures(self, mcp):
        fn = await get_tool(mcp, "be_get_departures")
        # iRail ignores the limit, so the tool trims
        result = await fn.fn("Gent-Sint-Pieters", limit=2)
        assert result["station"] == {"id": "BE.NMBS.008892007", "name": "Ghent-Sint-Pieters"}
        delayed, cancelled = result["departures"]
        assert delayed == {
            "line": "IC 531",
            "category": "IC",
            "destination": "Oostende",
            "planned": "2026-10-05T10:39:00+02:00",
            "expected": "2026-10-05T10:58:00+02:00",
            "delay_min": 19,
        }
        assert cancelled["cancelled"] is True
        assert cancelled["platform"] == "5"

    @pytest.mark.unit
    async def test_be_get_departures_raw(self, mcp):
        fn = await get_tool(mcp, "be_get_departures")
        assert await fn.fn("Gent-Sint-Pieters", raw=True) == LIVEBOARD

    @pytest.mark.unit
    async def test_be_get_vehicle(self, mcp):
        fn = await get_tool(mcp, "be_get_vehicle")
        result = await fn.fn("IC531")
        assert result == {"dummy": True}
