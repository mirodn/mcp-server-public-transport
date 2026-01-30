# tools/ch.py
"""
Swiss public transport tools for MCP server
Uses transport.opendata.ch API
"""

import logging
from typing import Any, Dict, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import fetch_json, validate_station_name, TransportAPIError, format_time_for_api
from config import CH_BASE_URL

logger = logging.getLogger(__name__)


def register_ch_tools(mcp):
    """Register Swiss transport tools with the MCP server"""

    @mcp.tool(
        name="ch_search_connections",
        description=(
            "Search for train connections in Switzerland between two stations. "
            "Uses transport.opendata.ch API to provide real-time connection data including "
            "departure times, duration, platforms, and transfers."
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
            return await fetch_json(f"{CH_BASE_URL}/connections", params)
        except TransportAPIError as e:
            logger.error("CH connection search failed: %s", e)
            raise

    @mcp.tool(
        name="ch_search_stations",
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
            return await fetch_json(f"{CH_BASE_URL}/locations", params)
        except TransportAPIError as e:
            logger.error("CH station search failed: %s", e)
            raise

    @mcp.tool(
        name="ch_get_departures",
        description="Get departure board for a Swiss train station with real-time information.",
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
            return await fetch_json(f"{CH_BASE_URL}/stationboard", params)
        except TransportAPIError as e:
            logger.error("CH departures fetch failed: %s", e)
            raise

    @mcp.tool(
        name="ch_nearby_stations",
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
            return await fetch_json(f"{CH_BASE_URL}/locations", params)
        except TransportAPIError as e:
            logger.error("CH nearby stations search failed: %s", e)
            raise

    return [
        ch_search_connections,
        ch_search_stations,
        ch_get_departures,
        ch_nearby_stations,
    ]
