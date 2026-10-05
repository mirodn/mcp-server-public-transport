# tools/ch.py
"""
Swiss public transport tools for MCP server
Uses transport.opendata.ch API
"""

import logging
from typing import Any, Dict, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import (
    fetch_json,
    validate_station_name,
    TransportAPIError,
    format_time_for_api,
    READ_ONLY_TOOL,
    CACHE_TTL_LIVE,
    CACHE_TTL_PLAN,
    CACHE_TTL_STATIC,
)
from core.models import (
    RAW_FIELD,
    Departure,
    DepartureBoard,
    Journey,
    JourneyList,
    Leg,
    Stop,
    StopTime,
    compact,
    iso,
    journey_from_legs,
    minutes_between,
)
from config import CH_BASE_URL

logger = logging.getLogger(__name__)

def _ch_line(journey: Dict[str, Any]) -> Optional[str]:
    number = journey.get("number")
    # long-distance trains come zero-padded ("EC 000019")
    if number and number.isdigit():
        number = number.lstrip("0") or number
    parts = [journey.get("category"), number]
    return " ".join(p for p in parts if p) or None


def _ch_stop(station: Optional[Dict[str, Any]]) -> Stop:
    station = station or {}
    return Stop(id=station.get("id"), name=station.get("name"))


def _ch_stop_time(checkpoint: Dict[str, Any], kind: str) -> StopTime:
    """Map a transport.opendata.ch checkpoint; kind is 'departure' or 'arrival'."""
    prognosis = checkpoint.get("prognosis") or {}
    planned = iso(checkpoint.get(kind))
    expected = iso(prognosis.get(kind))
    delay = minutes_between(planned, expected) if expected else checkpoint.get("delay")
    return StopTime(
        stop=_ch_stop(checkpoint.get("station")),
        planned=planned,
        expected=expected,
        delay_min=delay,
        # prognosis carries the platform only when it changed
        platform=prognosis.get("platform") or checkpoint.get("platform"),
    )


def _ch_departure(entry: Dict[str, Any]) -> Departure:
    stop_time = _ch_stop_time(entry.get("stop") or {}, "departure")
    return Departure(
        line=_ch_line(entry),
        category=entry.get("category"),
        destination=entry.get("to"),
        planned=stop_time.planned,
        expected=stop_time.expected,
        delay_min=stop_time.delay_min,
        platform=stop_time.platform,
        operator=entry.get("operator"),
    )


def _ch_journey(connection: Dict[str, Any]) -> Journey:
    legs = []
    for section in connection.get("sections") or []:
        journey = section.get("journey")
        legs.append(
            Leg(
                walk=journey is None,
                line=_ch_line(journey) if journey else None,
                category=journey.get("category") if journey else None,
                direction=journey.get("to") if journey else None,
                departure=_ch_stop_time(section.get("departure") or {}, "departure"),
                arrival=_ch_stop_time(section.get("arrival") or {}, "arrival"),
            )
        )
    return journey_from_legs(legs, transfers=connection.get("transfers") or 0)


def register_ch_tools(mcp):
    """Register Swiss transport tools with the MCP server"""

    @mcp.tool(
        name="ch_search_connections",
        annotations=READ_ONLY_TOOL,
        description=(
            "Search for train connections in Switzerland between two stations. "
            "Uses transport.opendata.ch API to provide real-time connection data including "
            "departure times, duration, platforms, and transfers. Returns a compact list of "
            "journeys with legs; set raw=true for the full upstream response."
        ),
    )
    async def ch_search_connections(
        origin: Annotated[
            str,
            Field(description="Departure station name (CH). Example: 'Zürich HB'", min_length=1),
        ],
        destination: Annotated[
            str,
            Field(description="Arrival station name (CH). Example: 'Basel SBB'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max number of connections (default 4).", ge=1, le=10),
        ] = 4,
        date: Annotated[
            Optional[str],
            Field(description="Date in YYYY-MM-DD format (optional)."),
        ] = None,
        time: Annotated[
            Optional[str],
            Field(description="Time in HH:MM format (optional)."),
        ] = None,
        is_arrival_time: Annotated[
            Optional[bool],
            Field(description="If true, interpret 'time' as arrival time (default false)."),
        ] = False,
        raw: Annotated[bool, RAW_FIELD] = False,
    ) -> Dict[str, Any]:
        origin_clean = validate_station_name(origin)
        destination_clean = validate_station_name(destination)

        params: Dict[str, Any] = {
            "from": origin_clean,
            "to": destination_clean,
            "limit": int(limit or 4),
        }

        if date:
            params["date"] = date
        if time:
            params["time"] = format_time_for_api(time)
        if is_arrival_time:
            params["isArrivalTime"] = "1"

        try:
            logger.info("Searching connections: %s → %s", origin_clean, destination_clean)
            data = await fetch_json(f"{CH_BASE_URL}/connections", params, cache_ttl=CACHE_TTL_PLAN)
        except TransportAPIError as e:
            logger.error("CH connection search failed: %s", e)
            raise

        if raw:
            return data
        journeys = [_ch_journey(c) for c in data.get("connections") or []]
        return compact(JourneyList(journeys=journeys))

    @mcp.tool(
        name="ch_search_stations",
        annotations=READ_ONLY_TOOL,
        description="Search for Swiss train stations by name or location.",
    )
    async def ch_search_stations(
        query: Annotated[
            str,
            Field(description="Station/location search query. Example: 'Bern'", min_length=1),
        ],
        type: Annotated[
            Optional[str],
            Field(description="Location type filter (default 'station'). Example: 'station'"),
        ] = "station",
    ) -> Dict[str, Any]:
        query_clean = query.strip() if query else ""
        if not query_clean:
            raise ValueError("Search query cannot be empty")

        params = {
            "query": query_clean,
            "type": type or "station",
        }

        try:
            logger.info("Searching stations: %s", query_clean)
            return await fetch_json(f"{CH_BASE_URL}/locations", params, cache_ttl=CACHE_TTL_STATIC)
        except TransportAPIError as e:
            logger.error("CH station search failed: %s", e)
            raise

    @mcp.tool(
        name="ch_get_departures",
        annotations=READ_ONLY_TOOL,
        description=(
            "Get departure board for a Swiss train station with real-time information "
            "(planned/expected time, delay, platform). Set raw=true for the full upstream response."
        ),
    )
    async def ch_get_departures(
        station: Annotated[
            str,
            Field(description="Station name (CH). Example: 'Luzern'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max departures to return (default 10).", ge=1, le=50),
        ] = 10,
        datetime: Annotated[
            Optional[str],
            Field(description="Datetime ISO string supported by API (optional)."),
        ] = None,
        raw: Annotated[bool, RAW_FIELD] = False,
    ) -> Dict[str, Any]:
        station_clean = validate_station_name(station)

        params: Dict[str, Any] = {
            "station": station_clean,
            "limit": int(limit or 10),
        }

        if datetime:
            params["datetime"] = datetime

        try:
            logger.info("Getting departures for: %s", station_clean)
            data = await fetch_json(f"{CH_BASE_URL}/stationboard", params, cache_ttl=CACHE_TTL_LIVE)
        except TransportAPIError as e:
            logger.error("CH departures fetch failed: %s", e)
            raise

        if raw:
            return data
        board = DepartureBoard(
            station=_ch_stop(data.get("station")),
            departures=[_ch_departure(e) for e in data.get("stationboard") or []],
        )
        return compact(board)

    @mcp.tool(
        name="ch_nearby_stations",
        annotations=READ_ONLY_TOOL,
        description="Find nearby Swiss train stations based on coordinates (latitude, longitude).",
    )
    async def ch_nearby_stations(
        latitude: Annotated[
            float,
            Field(description="Latitude in decimal degrees. Example: 47.378", ge=-90, le=90),
        ],
        longitude: Annotated[
            float,
            Field(description="Longitude in decimal degrees. Example: 8.540", ge=-180, le=180),
        ],
        distance: Annotated[
            Optional[int],
            Field(description="Search radius in meters (default 1000).", ge=50, le=50000),
        ] = 1000,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "x": float(longitude),
            "y": float(latitude),
            "type": "station",
        }

        if distance is not None:
            params["distance"] = int(distance)

        try:
            logger.info("Finding stations near coordinates")
            return await fetch_json(f"{CH_BASE_URL}/locations", params, cache_ttl=CACHE_TTL_STATIC)
        except TransportAPIError as e:
            logger.error("CH nearby stations search failed: %s", e)
            raise

    return [
        ch_search_connections,
        ch_search_stations,
        ch_get_departures,
        ch_nearby_stations,
    ]
