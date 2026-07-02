# tools/pt.py
"""
Portugal public transport tools for MCP server
Uses Transitous (api.transitous.org), a MOTIS instance routing over ingested GTFS feeds.

Coverage is scoped to the Lisbon and Porto metro areas:
- Lisbon: Metro Lisboa, Carris, Carris Metropolitana, CP suburban
- Porto: Metro do Porto, STCP

Provides:
- pt_search_stations: find stops by name (Portugal only)
- pt_search_connections: plan a trip A -> B
- pt_get_departures: departure board for a stop
- pt_nearby_stations: find stops near coordinates

No authentication required.

Attribution: data is provided by Transitous (https://transitous.org), a best-effort,
volunteer-run service built on openly ingested GTFS feeds. Keep the attribution visible
to users and follow the usage policy at https://transitous.org/api/ (see also
https://transitous.org/sources/ for underlying feed/OpenStreetMap attribution).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import fetch_json, validate_station_name, TransportAPIError, format_time_for_api
from config import PT_BASE_URL

logger = logging.getLogger(__name__)

# both metro areas share the same zone
PT_TZ = ZoneInfo("Europe/Lisbon")

# surfaced to users in each tool description; transitous wants attribution kept visible
_ATTRIBUTION = (
    "Data via Transitous (https://transitous.org), a best-effort, volunteer-run service; "
    "usage policy: https://transitous.org/api/."
)


def _to_iso(date: Optional[str], time: Optional[str]) -> Optional[str]:
    """Combine date (YYYY-MM-DD) and time (HH:MM) into an rfc3339 string.

    motis rejects naive timestamps so we attach the Lisbon offset. missing parts
    fall back to today / midnight. returns None when nothing was given (motis
    then defaults to now).
    """
    if not date and not time:
        return None

    now = datetime.now(PT_TZ)
    if date:
        y, m, d = (int(p) for p in date.split("-"))
    else:
        y, m, d = now.year, now.month, now.day

    hh, mm = (0, 0)
    if time:
        hh, mm = (int(p) for p in format_time_for_api(time).split(":"))

    local = datetime(y, m, d, hh, mm, tzinfo=PT_TZ)
    return local.isoformat()


def _pt_only(hits: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Keep Portuguese hits only and trim. geocode is global so we filter here."""
    return [h for h in hits if h.get("country") == "PT"][:limit]


def register_pt_tools(mcp):
    """Register Portugal (Lisbon + Porto) transport tools with the MCP server."""

    @mcp.tool(
        name="pt_search_stations",
        description=(
            "Search for stops/stations in Portugal by name. "
            "Covers the Lisbon and Porto metro areas (metro, buses, trams, suburban rail) "
            "via Transitous. Returns stop id, name and coordinates - use the id with "
            "pt_search_connections and pt_get_departures. "
            + _ATTRIBUTION
        ),
    )
    async def pt_search_stations(
        query: Annotated[
            str,
            Field(description="Station/stop search query. Example: 'Trindade'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max number of results (default 10).", ge=1, le=50),
        ] = 10,
    ) -> List[Dict[str, Any]]:
        query_clean = validate_station_name(query)

        params = {
            "text": query_clean,
            "type": "STOP",
        }

        try:
            logger.info("Searching PT stations: %s", query_clean)
            hits = await fetch_json(f"{PT_BASE_URL}/geocode", params)
            return _pt_only(hits, int(limit or 10))
        except TransportAPIError as e:
            logger.error("PT station search failed: %s", e)
            raise

    @mcp.tool(
        name="pt_search_connections",
        description=(
            "Plan a public transport connection between two points in the Lisbon or Porto "
            "metro area. Origin and destination are either stop ids (from pt_search_stations) "
            "or 'lat,lon' coordinates. Returns itineraries with legs, lines, times and transfers. "
            + _ATTRIBUTION
        ),
    )
    async def pt_search_connections(
        origin: Annotated[
            str,
            Field(description="Origin stop id or 'lat,lon'. Example: 'pt-Metro-Lisboa_MP'", min_length=1),
        ],
        destination: Annotated[
            str,
            Field(description="Destination stop id or 'lat,lon'. Example: 'pt-Metro-Lisboa_BC'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max number of itineraries (default 4).", ge=1, le=10),
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
            Field(description="If true, interpret date/time as arrival time (default false)."),
        ] = False,
    ) -> Dict[str, Any]:
        origin_clean = origin.strip()
        destination_clean = destination.strip()
        if not origin_clean or not destination_clean:
            raise ValueError("Origin and destination cannot be empty")

        params: Dict[str, Any] = {
            "fromPlace": origin_clean,
            "toPlace": destination_clean,
            "numItineraries": int(limit or 4),
        }

        when = _to_iso(date, time)
        if when:
            params["time"] = when
        if is_arrival_time:
            params["arriveBy"] = "true"

        try:
            logger.info("Planning PT connection: %s -> %s", origin_clean, destination_clean)
            return await fetch_json(f"{PT_BASE_URL}/plan", params)
        except TransportAPIError as e:
            logger.error("PT connection search failed: %s", e)
            raise

    @mcp.tool(
        name="pt_get_departures",
        description=(
            "Get the departure board for a stop in the Lisbon or Porto metro area. "
            "Needs a stop id from pt_search_stations. Returns upcoming departures with "
            "line, headsign and real-time times. "
            + _ATTRIBUTION
        ),
    )
    async def pt_get_departures(
        stop_id: Annotated[
            str,
            Field(description="Stop id. Example: 'pt-Metro-Porto_5726' for Trindade", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max departures to return (default 10).", ge=1, le=50),
        ] = 10,
        time: Annotated[
            Optional[str],
            Field(description="Date/time as rfc3339 (optional). Default: now."),
        ] = None,
    ) -> Dict[str, Any]:
        stop_id_clean = stop_id.strip()
        if not stop_id_clean:
            raise ValueError("Stop ID cannot be empty")

        params: Dict[str, Any] = {
            "stopId": stop_id_clean,
            "n": int(limit or 10),
        }

        if time:
            params["time"] = time.strip()

        try:
            logger.info("Getting PT departures for stop: %s", stop_id_clean)
            return await fetch_json(f"{PT_BASE_URL}/stoptimes", params)
        except TransportAPIError as e:
            logger.error("PT departures fetch failed: %s", e)
            raise

    @mcp.tool(
        name="pt_nearby_stations",
        description=(
            "Find stops/stations near coordinates in the Lisbon or Porto metro area. "
            "Returns the closest stops with id, name and coordinates. "
            + _ATTRIBUTION
        ),
    )
    async def pt_nearby_stations(
        latitude: Annotated[
            float,
            Field(description="Latitude in decimal degrees. Example: 41.15228", ge=-90, le=90),
        ],
        longitude: Annotated[
            float,
            Field(description="Longitude in decimal degrees. Example: -8.609299", ge=-180, le=180),
        ],
        results: Annotated[
            Optional[int],
            Field(description="Max number of results (default 8).", ge=1, le=50),
        ] = 8,
    ) -> List[Dict[str, Any]]:
        # reverse-geocode wants "lat,lon"
        params = {
            "place": f"{float(latitude)},{float(longitude)}",
            "type": "STOP",
        }

        try:
            logger.info("Finding PT stations near provided coordinates")
            hits = await fetch_json(f"{PT_BASE_URL}/reverse-geocode", params)
            return _pt_only(hits, int(results or 8))
        except TransportAPIError as e:
            logger.error("PT nearby stations search failed: %s", e)
            raise

    return [
        pt_search_stations,
        pt_search_connections,
        pt_get_departures,
        pt_nearby_stations,
    ]
