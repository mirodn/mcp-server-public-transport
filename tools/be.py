# tools/be.py
"""
Belgium public transport tools for MCP server using the iRail API
"""

import logging
import re
from datetime import date as date_type
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from typing_extensions import Annotated
from pydantic import Field

from core.base import (
    fetch_json,
    TransportAPIError,
    validate_station_name,
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
    from_timestamp,
    journey_from_legs,
    strip_html,
)
from config import BE_BASE_URL

logger = logging.getLogger(__name__)

BE_TZ = ZoneInfo("Europe/Brussels")


def _format_date_for_irail(date: str) -> str:
    """Convert an ISO date to the DDMMYY format expected by iRail."""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError
        return date_type.fromisoformat(date).strftime("%d%m%y")
    except ValueError as e:
        raise ValueError("Invalid date format. Use YYYY-MM-DD") from e


def _format_time_for_irail(time: str) -> str:
    """Convert a user-facing time to the HHMM format expected by iRail."""
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("Invalid time format. Use HH:MM")
    return time.replace(":", "")


def _be_list(container: Optional[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """iRail wraps lists as {"number": "2", key: [...]}; a single item may come unwrapped."""
    items = (container or {}).get(key) or []
    return [items] if isinstance(items, dict) else items


def _be_flag(value: Any) -> Optional[bool]:
    """iRail encodes booleans as "0"/"1"; return None for false to keep output small."""
    return True if str(value) == "1" else None


def _be_stop(point: Dict[str, Any]) -> Stop:
    info = point.get("stationinfo") or {}
    return Stop(id=info.get("id"), name=info.get("name") or point.get("station"))


def _be_stop_time(point: Dict[str, Any]) -> StopTime:
    """Map an iRail departure/arrival point: unix 'time' is the schedule, 'delay' is seconds."""
    planned = from_timestamp(point.get("time"), BE_TZ)
    delay_s = int(point.get("delay") or 0)
    expected = from_timestamp(int(point["time"]) + delay_s, BE_TZ) if planned else None
    platform = point.get("platform")
    return StopTime(
        stop=_be_stop(point),
        planned=planned,
        expected=expected,
        delay_min=round(delay_s / 60) if planned else None,
        platform=platform if platform not in (None, "", "?") else None,
    )


def _be_departure(entry: Dict[str, Any]) -> Departure:
    vehicle = entry.get("vehicleinfo") or {}
    stop_time = _be_stop_time(entry)
    return Departure(
        line=vehicle.get("shortname"),
        category=vehicle.get("type"),
        destination=entry.get("station"),
        planned=stop_time.planned,
        expected=stop_time.expected,
        delay_min=stop_time.delay_min,
        platform=stop_time.platform,
        cancelled=_be_flag(entry.get("canceled")),
    )


def _be_leg(start: Dict[str, Any], end: Dict[str, Any]) -> Leg:
    vehicle = start.get("vehicleinfo") or {}
    walk = _be_flag(start.get("walking")) is True
    return Leg(
        walk=walk,
        line=None if walk else vehicle.get("shortname"),
        category=None if walk else vehicle.get("type"),
        direction=None if walk else (start.get("direction") or {}).get("name"),
        departure=_be_stop_time(start),
        arrival=_be_stop_time(end),
        cancelled=_be_flag(start.get("canceled")) or _be_flag(end.get("canceled")),
    )


def _be_alerts(connection: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    for alert in _be_list(connection.get("alerts"), "alert"):
        parts = [alert.get("header"), alert.get("description")]
        text = strip_html(": ".join(p for p in parts if p))
        if text and text not in texts:
            texts.append(text)
    for remark in _be_list(connection.get("remarks"), "remark"):
        text = strip_html(remark.get("description") or "")
        if text and text not in texts:
            texts.append(text)
    return texts


def _be_journey(connection: Dict[str, Any]) -> Journey:
    """A connection is departure -> vias -> arrival; each via ends one leg and starts the next."""
    points = [connection.get("departure") or {}]
    for via in _be_list(connection.get("vias"), "via"):
        points.append(via.get("arrival") or {})
        points.append(via.get("departure") or {})
    points.append(connection.get("arrival") or {})
    legs = [_be_leg(points[i], points[i + 1]) for i in range(0, len(points), 2)]
    return journey_from_legs(legs, remarks=_be_alerts(connection))


def register_be_tools(mcp):
    """Register Belgian public transport tools with the MCP server"""

    @mcp.tool(
        name="be_search_connections",
        annotations=READ_ONLY_TOOL,
        description=(
            "Search train connections in Belgium between two stations. "
            "Powered by iRail API for real-time routes and schedules. Returns a compact list of "
            "journeys with legs and alerts; set raw=true for the full upstream response."
        ),
    )
    async def be_search_connections(
        origin: Annotated[
            str,
            Field(
                description="Origin station name (Belgium). Example: 'Bruxelles-Central'",
                min_length=1,
            ),
        ],
        destination: Annotated[
            str,
            Field(
                description="Destination station name (Belgium). Example: 'Gent-Sint-Pieters'",
                min_length=1,
            ),
        ],
        results: Annotated[
            Optional[int],
            Field(
                description="Max number of connections to return (default 4).",
                ge=1,
                le=10,
            ),
        ] = 4,
        date: Annotated[
            Optional[str],
            Field(description="Travel date in YYYY-MM-DD format (optional)."),
        ] = None,
        time: Annotated[
            Optional[str],
            Field(description="Travel time in HH:MM format (optional)."),
        ] = None,
        raw: Annotated[bool, RAW_FIELD] = False,
    ) -> Dict[str, Any]:
        origin_clean = validate_station_name(origin)
        destination_clean = validate_station_name(destination)

        if origin_clean == destination_clean:
            raise ValueError("Origin and destination must be different")

        params: Dict[str, Any] = {
            "from": origin_clean,
            "to": destination_clean,
            "format": "json",
            "results": int(results or 4),
        }
        if date:
            params["date"] = _format_date_for_irail(date)
        if time:
            params["time"] = _format_time_for_irail(time)

        try:
            logger.info("Searching connections: %s → %s", origin_clean, destination_clean)
            data = await fetch_json(f"{BE_BASE_URL}/connections/", params, cache_ttl=CACHE_TTL_PLAN)
        except TransportAPIError as e:
            logger.error("Belgium connection search failed: %s", e, exc_info=True)
            raise

        if raw:
            return data
        journeys = [_be_journey(c) for c in data.get("connection") or []]
        return compact(JourneyList(journeys=journeys))

    @mcp.tool(
        name="be_search_stations",
        annotations=READ_ONLY_TOOL,
        description="Search for Belgian train stations by name.",
    )
    async def be_search_stations(
        query: Annotated[
            str,
            Field(description="Station name query. Example: 'Brux'", min_length=1),
        ]
    ) -> Dict[str, Any]:
        query_clean = query.strip() if query else ""
        if not query_clean or len(query_clean) < 2:
            raise ValueError("Station search query must be at least 2 characters")

        params = {"input": query_clean, "format": "json"}

        try:
            logger.info("Searching stations for: %s", query_clean)
            return await fetch_json(f"{BE_BASE_URL}/stations/", params, cache_ttl=CACHE_TTL_STATIC)
        except TransportAPIError as e:
            logger.error("Belgium station search failed: %s", e, exc_info=True)
            raise

    @mcp.tool(
        name="be_get_departures",
        annotations=READ_ONLY_TOOL,
        description=(
            "Get live departure board for a Belgian train station (planned/expected time, delay, "
            "platform, cancellations). Set raw=true for the full upstream response."
        ),
    )
    async def be_get_departures(
        station: Annotated[
            str,
            Field(description="Station name. Example: 'Antwerpen-Centraal'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max departures to return (default 10).", ge=1, le=50),
        ] = 10,
        raw: Annotated[bool, RAW_FIELD] = False,
    ) -> Dict[str, Any]:
        station_clean = validate_station_name(station)

        params = {
            "station": station_clean,
            "limit": int(limit or 10),
            "format": "json",
        }

        try:
            logger.info("Fetching departures for station: %s", station_clean)
            data = await fetch_json(f"{BE_BASE_URL}/liveboard/", params, cache_ttl=CACHE_TTL_LIVE)
        except TransportAPIError as e:
            logger.error("Belgium liveboard fetch failed: %s", e, exc_info=True)
            raise

        if raw:
            return data
        # iRail ignores `limit` and always returns the full board, so trim here
        entries = _be_list(data.get("departures"), "departure")[: int(limit or 10)]
        board = DepartureBoard(
            station=_be_stop({"stationinfo": data.get("stationinfo"), "station": data.get("station")}),
            departures=[_be_departure(e) for e in entries],
        )
        return compact(board)

    @mcp.tool(
        name="be_get_vehicle",
        annotations=READ_ONLY_TOOL,
        description="Get details about a specific Belgian train vehicle by its ID.",
    )
    async def be_get_vehicle(
        vehicle_id: Annotated[
            str,
            Field(
                description="Vehicle ID from iRail. Example: 'BE.NMBS.IC1234' (format may vary)",
                min_length=1,
            ),
        ]
    ) -> Dict[str, Any]:
        vid = vehicle_id.strip() if vehicle_id else ""
        if not vid:
            raise ValueError("Vehicle ID must be provided for vehicle lookup")

        params = {"id": vid, "format": "json"}

        try:
            logger.info("Fetching vehicle info: %s", vid)
            return await fetch_json(f"{BE_BASE_URL}/vehicle/", params, cache_ttl=CACHE_TTL_LIVE)
        except TransportAPIError as e:
            logger.error("Belgium vehicle fetch failed: %s", e, exc_info=True)
            raise

    return [
        be_search_connections,
        be_search_stations,
        be_get_departures,
        be_get_vehicle,
    ]
