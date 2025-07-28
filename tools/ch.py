"""
Swiss public transport tools for MCP server
Uses transport.opendata.ch API
"""

from typing import Dict, Any, Optional
import logging
from core.base import fetch_json, validate_station_name, TransportAPIError, format_time_for_api
from config import CH_BASE_URL

logger = logging.getLogger(__name__)

def register_ch_tools(mcp):
    """Register Swiss transport tools with the MCP server"""

    @mcp.tool(
        name="ch_search_connections",
        description="Search for train connections in Switzerland between two stations. Uses transport.opendata.ch API to provide real-time connection data including departure times, duration, platforms, and transfers."
    )
    async def ch_search_connections(
        origin: str,
        destination: str,
        limit: Optional[int] = 4,
        date: Optional[str] = None,
        time: Optional[str] = None,
        is_arrival_time: Optional[bool] = False
    ) -> Dict[str, Any]:
        """
        Search for train connections between Swiss stations.

        Args:
            origin: Departure station name (e.g., 'Zürich HB')
            destination: Arrival station name (e.g., 'Basel SBB')
            limit: Max number of connections (default: 4)
            date: Date in format YYYY-MM-DD
            time: Time in HH:MM format
            is_arrival_time: Whether time refers to arrival (True) or departure (False)
        """
        origin_clean = validate_station_name(origin)
        destination_clean = validate_station_name(destination)

        params = {
            "from": origin_clean,
            "to": destination_clean,
            "limit": limit or 4
        }

        if date:
            params["date"] = date
        if time:
            params["time"] = format_time_for_api(time)
        if is_arrival_time:
            params["isArrivalTime"] = "1"

        try:
            logger.info(f"Searching connections: {origin} → {destination}")
            return await fetch_json(f"{CH_BASE_URL}/connections", params)
        except TransportAPIError as e:
            logger.error(f"CH connection search failed: {e}")
            raise

    @mcp.tool(
        name="ch_search_stations",
        description="Search for Swiss train stations by name or location."
    )
    async def ch_search_stations(
        query: str,
        type: Optional[str] = "station"
    ) -> Dict[str, Any]:
        """Search for Swiss stations by name."""
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        params = {
            "query": query.strip(),
            "type": type or "station"
        }

        try:
            logger.info(f"Searching stations: {query}")
            return await fetch_json(f"{CH_BASE_URL}/locations", params)
        except TransportAPIError as e:
            logger.error(f"CH station search failed: {e}")
            raise

    @mcp.tool(
        name="ch_get_departures",
        description="Get departure board for a Swiss train station with real-time information."
    )
    async def ch_get_departures(
        station: str,
        limit: Optional[int] = 10,
        datetime: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get departures from a Swiss train station."""
        station_clean = validate_station_name(station)

        params = {
            "station": station_clean,
            "limit": limit or 10
        }

        if datetime:
            params["datetime"] = datetime

        try:
            logger.info(f"Getting departures for: {station}")
            return await fetch_json(f"{CH_BASE_URL}/stationboard", params)
        except TransportAPIError as e:
            logger.error(f"CH departures fetch failed: {e}")
            raise

    @mcp.tool(
        name="ch_nearby_stations",
        description="Find nearby Swiss train stations based on coordinates (latitude, longitude)."
    )
    async def ch_nearby_stations(
        latitude: float,
        longitude: float,
        distance: Optional[int] = 1000
    ) -> Dict[str, Any]:
        """Find nearby stations by coordinates."""
        params = {
            "x": longitude,
            "y": latitude,
            "type": "station"
        }

        if distance:
            params["distance"] = distance

        try:
            logger.info(f"🇨🇭 Finding stations near: {latitude}, {longitude}")
            return await fetch_json(f"{CH_BASE_URL}/locations", params)
        except TransportAPIError as e:
            logger.error(f"CH nearby stations search failed: {e}")
            raise

    return [
        ch_search_connections,
        ch_search_stations,
        ch_get_departures,
        ch_nearby_stations
    ]
