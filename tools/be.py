"""
Belgium public transport tools for MCP server using the iRail API
"""

import logging
from typing import Any, Dict, Optional
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
        )
    )
    async def be_search_connections(
        origin: str,
        destination: str,
        results: Optional[int] = 4,
        date: Optional[str] = None,
        time: Optional[str] = None
    ) -> Dict[str, Any]:
        if not origin or not origin.strip() or not destination or not destination.strip():
            raise ValueError("Origin and destination must be provided and non-empty")
        if origin.strip() == destination.strip():
            raise ValueError("Origin and destination must be different")

        params: Dict[str, Any] = {
            "from": origin.strip(),
            "to": destination.strip(),
            "format": "json",
            "results": results or 4
        }
        if date:
            params["date"] = date
        if time:
            params["time"] = time

        try:
            logger.info(f"Searching connections: {origin.strip()} → {destination.strip()}")
            return await fetch_json(f"{BE_BASE_URL}/connections/", params)
        except TransportAPIError as e:
            logger.error(f"Belgium connection search failed: {e}", exc_info=True)
            raise

    @mcp.tool(
        name="be_search_stations",
        description="Search for Belgian train stations by name."
    )
    async def be_search_stations(query: str) -> Dict[str, Any]:
        if not query or not query.strip():
            raise ValueError("Station search query cannot be empty")

        params = {"input": query.strip(), "format": "json"}

        try:
            logger.info(f"Searching stations for: {query.strip()}")
            return await fetch_json(f"{BE_BASE_URL}/stations/", params)
        except TransportAPIError as e:
            logger.error(f"Belgium station search failed: {e}", exc_info=True)
            raise

    @mcp.tool(
        name="be_get_departures",
        description="Get live departure board for a Belgian train station."
    )
    async def be_get_departures(station: str, limit: Optional[int] = 10) -> Dict[str, Any]:
        if not station or not station.strip():
            raise ValueError("Station name must be provided for departures lookup")

        params = {
            "station": station.strip(),
            "limit": limit or 10,
            "format": "json"
        }

        try:
            logger.info(f"Fetching departures for station: {station.strip()}")
            return await fetch_json(f"{BE_BASE_URL}/liveboard/", params)
        except TransportAPIError as e:
            logger.error(f"Belgium liveboard fetch failed: {e}", exc_info=True)
            raise

    @mcp.tool(
        name="be_get_vehicle",
        description="Get details about a specific Belgian train vehicle by its ID."
    )
    async def be_get_vehicle(vehicle_id: str) -> Dict[str, Any]:
        if not vehicle_id or not vehicle_id.strip():
            raise ValueError("Vehicle ID must be provided for vehicle lookup")

        params = {"id": vehicle_id.strip(), "format": "json"}

        try:
            logger.info(f"Fetching vehicle info: {vehicle_id.strip()}")
            return await fetch_json(f"{BE_BASE_URL}/vehicle/", params)
        except TransportAPIError as e:
            logger.error(f"Belgium vehicle fetch failed: {e}", exc_info=True)
            raise

    return [
        be_search_connections,
        be_search_stations,
        be_get_departures,
        be_get_vehicle
    ]
