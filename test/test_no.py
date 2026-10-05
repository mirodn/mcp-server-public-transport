import pytest
from fastmcp import FastMCP

from core.base import TransportAPIError
from tools.no import register_no_tools


@pytest.fixture
def mcp():
    server = FastMCP("test-no")
    register_no_tools(server)
    return server

SITUATION = {
    "summary": [{"value": "Signalfeil", "language": "no"}, {"value": "Signal failure", "language": "en"}],
    "description": [{"value": "Expect delays", "language": "en"}],
}

# GraphQL answers in the shape our queries request
DEPARTURES = {
    "stopPlace": {
        "id": "NSR:StopPlace:59872",
        "name": "Oslo S",
        "estimatedCalls": [
            {"realtime": True, "cancellation": False,
             "aimedDepartureTime": "2026-10-05T10:30:00+02:00",
             "expectedDepartureTime": "2026-10-05T10:34:00+02:00",
             "destinationDisplay": {"frontText": "Oslo Lufthavn"},
             "quay": {"id": "NSR:Quay:569", "publicCode": "14"},
             "situations": [SITUATION],
             "serviceJourney": {"line": {"publicCode": "FLY2", "transportMode": "rail",
                                         "operator": {"name": "Flytoget"}}}},
            {"realtime": False, "cancellation": True,
             "aimedDepartureTime": "2026-10-05T10:31:00+02:00",
             "expectedDepartureTime": "2026-10-05T10:31:00+02:00",
             "destinationDisplay": {"frontText": "Ski"},
             "quay": {"id": "NSR:Quay:556", "publicCode": "19"},
             "situations": [],
             "serviceJourney": {"line": {"publicCode": "L2", "transportMode": "rail"}}},
        ],
    }
}

def place(name, stop_place, code):
    return {"name": name, "quay": {"publicCode": code, "stopPlace": {"id": stop_place}}}

TRIP = {
    "trip": {"tripPatterns": [{
        "duration": 1870,
        "legs": [
            {"mode": "foot", "realtime": False,
             "aimedStartTime": "2026-10-05T10:31:50+02:00", "expectedStartTime": "2026-10-05T10:31:50+02:00",
             "aimedEndTime": "2026-10-05T10:37:00+02:00", "expectedEndTime": "2026-10-05T10:37:00+02:00",
             "fromPlace": place("Oslo S", "NSR:StopPlace:337", "3"),
             "toPlace": place("Jernbanetorget", "NSR:StopPlace:3990", "2"),
             "line": None, "fromEstimatedCall": None, "situations": []},
            {"mode": "metro", "realtime": True,
             "aimedStartTime": "2026-10-05T10:37:00+02:00", "expectedStartTime": "2026-10-05T10:39:00+02:00",
             "aimedEndTime": "2026-10-05T11:03:00+02:00", "expectedEndTime": "2026-10-05T11:05:00+02:00",
             "fromPlace": place("Jernbanetorget", "NSR:StopPlace:3990", "2"),
             "toPlace": place("Holmenkollen", "NSR:StopPlace:6318", "2"),
             "line": {"publicCode": "1", "transportMode": "metro"},
             "fromEstimatedCall": {"destinationDisplay": {"frontText": "Frognerseteren"}, "cancellation": False},
             "situations": [SITUATION]},
        ],
    }]}
}

@pytest.fixture
def calls():
    return []

@pytest.fixture(autouse=True)
def mock_http(monkeypatch, calls):
    async def dummy_fetch(url, params, headers=None, **kwargs):
        calls.append(("GET", url, params, headers))
        return {"features": []}

    async def dummy_post(url, body, headers=None, **kwargs):
        calls.append(("POST", url, body, headers))
        if "StopDepartures" in body["query"]:
            return {"data": DEPARTURES}
        if "PlanTrip" in body["query"]:
            return {"data": TRIP}
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
        result = await fn.fn("NSR:StopPlace:59872", limit=5)
        assert calls[0][2]["variables"] == {"id": "NSR:StopPlace:59872", "limit": 5}

        assert result["station"] == {"id": "NSR:StopPlace:59872", "name": "Oslo S"}
        live, cancelled = result["departures"]
        assert live == {
            "line": "FLY2",
            "category": "rail",
            "destination": "Oslo Lufthavn",
            "planned": "2026-10-05T10:30:00+02:00",
            "expected": "2026-10-05T10:34:00+02:00",
            "delay_min": 4,
            "platform": "14",
            "operator": "Flytoget",
            # English preferred over Norwegian
            "remarks": ["Signal failure: Expect delays"],
        }
        # without real-time data Entur repeats the aimed time; that is not a prediction
        assert "expected" not in cancelled
        assert cancelled["cancelled"] is True

    @pytest.mark.unit
    async def test_no_stop_departures_raw(self, mcp):
        fn = await get_tool(mcp, "no_stop_departures")
        assert await fn.fn("NSR:StopPlace:59872", raw=True) == DEPARTURES

    @pytest.mark.unit
    async def test_no_stop_departures_unknown_id(self, mcp, monkeypatch):
        async def empty_post(url, body, headers=None, **kwargs):
            return {"data": {"stopPlace": None}}
        monkeypatch.setattr("tools.no.post_json", empty_post)

        fn = await get_tool(mcp, "no_stop_departures")
        with pytest.raises(ValueError, match="no_search_places"):
            await fn.fn("NSR:StopPlace:0")

    @pytest.mark.unit
    async def test_no_trip(self, mcp, calls):
        fn = await get_tool(mcp, "no_trip")
        result = await fn.fn("NSR:StopPlace:59872", "NSR:StopPlace:59766", results=3)
        assert calls[0][2]["variables"]["results"] == 3

        journey = result["journeys"][0]
        assert journey["departure"] == "2026-10-05T10:31:50+02:00"
        assert journey["arrival"] == "2026-10-05T11:03:00+02:00"
        assert journey["duration_min"] == 31
        assert journey["transfers"] == 0

        walk, metro = journey["legs"]
        assert walk["walk"] is True
        assert walk["departure"]["stop"] == {"id": "NSR:StopPlace:337", "name": "Oslo S"}
        assert metro["line"] == "1"
        assert metro["direction"] == "Frognerseteren"
        assert metro["departure"]["delay_min"] == 2
        assert metro["remarks"] == ["Signal failure: Expect delays"]

    @pytest.mark.unit
    async def test_no_trip_raw(self, mcp):
        fn = await get_tool(mcp, "no_trip")
        assert await fn.fn("NSR:StopPlace:59872", "NSR:StopPlace:59766", raw=True) == TRIP

    @pytest.mark.unit
    async def test_no_nearest_stops(self, mcp):
        fn = await get_tool(mcp, "no_nearest_stops")
        result = await fn.fn(59.91, 10.75, radius=300)
        assert result == {"dummy": True}

    @pytest.mark.unit
    async def test_graphql_errors_raise(self, mcp, monkeypatch):
        async def failing_post(url, body, headers=None, **kwargs):
            return {"errors": [{"message": "boom"}]}
        monkeypatch.setattr("tools.no.post_json", failing_post)

        fn = await get_tool(mcp, "no_stop_departures")
        with pytest.raises(TransportAPIError, match="boom"):
            await fn.fn("NSR:StopPlace:58368")
