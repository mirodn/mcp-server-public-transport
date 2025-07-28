"""
UK public transport tools for MCP server
Uses transportapi.com API
"""
import os
import logging
from typing import Any, Dict
from core.base import fetch_json, TransportAPIError
from config import UK_BASE_URL

logger = logging.getLogger(__name__)

def register_uk_tools(mcp):
    """Register UK transport tools with the MCP server"""

    @mcp.tool(
        name="uk_live_departures",
        description=(
            "Get live departure information for a UK train station using its CRS code "
            "(e.g. 'PAD' - London Paddington, 'MAN' - Manchester Piccadilly). "
            "Powered by transportapi.com real-time API."
        )
    )
    async def uk_live_departures(station_code: str) -> Dict[str, Any]:
        """
        Retrieve live departure board for a UK station.

        Args:
            station_code: 3-letter CRS code (e.g. "PAD", "MAN", "EDI").

        Returns:
            JSON with departure times, destinations, platform and delay info.
        """
        code = station_code.strip().upper() if station_code else ""
        if len(code) != 3:
            raise ValueError("Station code must be a 3-character CRS code")

        # Credential validation
        app_id = os.getenv("UK_TRANSPORT_APP_ID")
        api_key = os.getenv("UK_TRANSPORT_API_KEY")
        if not app_id or not api_key:
            raise TransportAPIError(
                "UK transport API credentials are not configured. "
                "Set both UK_TRANSPORT_APP_ID and UK_TRANSPORT_API_KEY."
            )

        params = {
            "app_id": app_id,
            "app_key": api_key,
            "live": "true",
            "to_offset": 120
        }
        url = f"{UK_BASE_URL}/train/station_timetables/{code}.json"

        try:
            logger.info(f"🇬🇧 Fetching live departures for station: {code}")
            return await fetch_json(url, params)
        except TransportAPIError as e:
            logger.error(f"UK live departures fetch failed: {e}", exc_info=True)
            raise

    return [uk_live_departures]
