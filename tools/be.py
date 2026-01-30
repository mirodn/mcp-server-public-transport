# tools/be.py
"""
Belgium public transport tools for MCP server using the iRail API
"""

import logging
from typing import Any, Dict, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import fetch_json, TransportAPIError
from config import BE_BASE_URL

logger = logging.getLogger(__name__)


def register_be_tools(mcp):
    """Register Belgian public transport tools with the MCP server"""

    @mcp.tool(
        name="be_search_connections",
        description=(
            "Search train connections in Belgium between two stations. "
            "Powered by iRail API for real-time routes and schedules."
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
    ) -> Dict[str, Any]:
        origin_clean = origin.strip() if origin else ""
        destination_clean = destination.strip() if destination else ""

        if not origin_clean or not destination_clean:
            raise ValueError("Origin and destination must be provided and non-empty")
        if origin_clean == destination_clean:
            raise ValueError("Origin and destination must be different")

        params: Dict[str, Any] = {
            "from": origin_clean,
            "to": destination_clean,
            "format": "json",
            "results": int(results or 4),
        }
        if date:
            params["date"] = date
        if time:
            params["time"] = time

        try:
            logger.info("Searching connections: %s → %s", origin_clean, destination_clean)
            return await fetch_json(f"{BE_BASE_URL}/connections/", params)
        except TransportAPIError as e:
            logger.error("Belgium connection search failed: %s", e, exc_info=True)
            raise

    @mcp.tool(
        name="be_search_stations",
        description="Search for Belgian train stations by name.",
    )
    async def be_search_stations(
        query: Annotated[
            str,
            Field(description="Station name query. Example: 'Brux'", min_length=1),
        ]
    ) -> Dict[str, Any]:
        query_clean = query.strip() if query else ""
        if not query_clean:
            raise ValueError("Station search query cannot be empty")

        params = {"input": query_clean, "format": "json"}

        try:
            logger.info("Searching stations for: %s", query_clean)
            return await fetch_json(f"{BE_BASE_URL}/stations/", params)
        except TransportAPIError as e:
            logger.error("Belgium station search failed: %s", e, exc_info=True)
            raise

    @mcp.tool(
        name="be_get_departures",
        description="Get live departure board for a Belgian train station.",
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
    ) -> Dict[str, Any]:
        station_clean = station.strip() if station else ""
        if not station_clean:
            raise ValueError("Station name must be provided for departures lookup")

        params = {
            "station": station_clean,
            "limit": int(limit or 10),
            "format": "json",
        }

        try:
            logger.info("Fetching departures for station: %s", station_clean)
            return await fetch_json(f"{BE_BASE_URL}/liveboard/", params)
        except TransportAPIError as e:
            logger.error("Belgium liveboard fetch failed: %s", e, exc_info=True)
            raise

    @mcp.tool(
        name="be_get_vehicle",
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
            return await fetch_json(f"{BE_BASE_URL}/vehicle/", params)
        except TransportAPIError as e:
            logger.error("Belgium vehicle fetch failed: %s", e, exc_info=True)
            raise

    return [
        be_search_connections,
        be_search_stations,
        be_get_departures,
        be_get_vehicle,
    ]
