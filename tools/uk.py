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
            "(e.g., 'PAD' for London Paddington, 'MAN' for Manchester Piccadilly). "
            "Uses the TransportAPI station timetables endpoint with live data."
        ),
    )
    async def uk_live_departures(station_code: str) -> Dict[str, Any]:
        """
        Retrieve live departures for a UK train station.

        Args:
            station_code (str): 3-letter CRS code (e.g., 'PAD', 'MAN', 'EDI').

        Returns:
            Dict[str, Any]: JSON response containing departure details.
        """
        # Validate station code
        code = station_code.strip().upper() if station_code else ""
        if len(code) != 3:
            raise ValueError("Station code must be exactly 3 characters (CRS code).")

        # Load credentials from environment variables
        app_id = os.getenv("UK_TRANSPORT_APP_ID")
        api_key = os.getenv("UK_TRANSPORT_API_KEY")
        if not app_id or not api_key:
            raise TransportAPIError(
                "UK Transport API credentials are not configured. "
                "Set both UK_TRANSPORT_APP_ID and UK_TRANSPORT_API_KEY."
            )

        # Prepare API request
        url = f"{UK_BASE_URL}/train/station_timetables/{code}.json"
        params = {
            "app_id": app_id,
            "app_key": api_key,
            "live": "true"
        }

        # Execute API request
        try:
            logger.info(f"🇬🇧 Fetching live departures for UK station: {code}")
            response = await fetch_json(url, params)
            return response
        except TransportAPIError as e:
            logger.error(f"UK live departures fetch failed: {e}", exc_info=True)
            raise

    return [uk_live_departures]
