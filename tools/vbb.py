# tools/vbb.py
"""
Berlin/Brandenburg (VBB) public transport tools for MCP server
Uses v6.vbb.transport.rest API (HAFAS-based)

Provides:
- vbb_search_locations: Search for stops, stations, POIs and addresses
- vbb_get_departures: Get departures at a stop/station
- vbb_get_arrivals: Get arrivals at a stop/station
- vbb_search_journeys: Find journeys from A to B
- vbb_nearby_stations: Find stops near coordinates

No authentication required. Rate limit: 100 requests/minute.
"""

import logging
from typing import Any, Dict, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import fetch_json, TransportAPIError
from config import VBB_BASE_URL

logger = logging.getLogger(__name__)


def register_vbb_tools(mcp):
    """Register Berlin/Brandenburg (VBB) transport tools with the MCP server."""

    @mcp.tool(
        name="vbb_search_locations",
        description=(
            "Search for stops/stations, POIs and addresses in Berlin/Brandenburg. "
            "Uses v6.vbb.transport.rest API to find locations matching a query. "
            "Returns location details including ID, name, coordinates, and available transport products."
        ),
    )
    async def vbb_search_locations(
        query: Annotated[
            str,
            Field(description="Search query. Example: 'Alexanderplatz'", min_length=1),
        ],
        results: Annotated[
            Optional[int],
            Field(description="Max number of results (default 10).", ge=1, le=50),
        ] = 10,
        stops: Annotated[
            Optional[bool],
            Field(description="Show stops/stations (default true)."),
        ] = True,
        addresses: Annotated[
            Optional[bool],
            Field(description="Show addresses (default true)."),
        ] = True,
        poi: Annotated[
            Optional[bool],
            Field(description="Show points of interest (default true)."),
        ] = True,
        fuzzy: Annotated[
            Optional[bool],
            Field(description="Find more than exact matches (default true)."),
        ] = True,
    ) -> Dict[str, Any]:
        query_clean = query.strip()
        if not query_clean:
            raise ValueError("Search query cannot be empty")

        params: Dict[str, Any] = {
            "query": query_clean,
            "results": int(results or 10),
            "stops": "true" if stops else "false",
            "addresses": "true" if addresses else "false",
            "poi": "true" if poi else "false",
            "fuzzy": "true" if fuzzy else "false",
        }

        try:
            logger.info("Searching VBB locations: %s", query_clean)
            return await fetch_json(f"{VBB_BASE_URL}/locations", params)
        except TransportAPIError as e:
            logger.error("VBB location search failed: %s", e)
            raise

    @mcp.tool(
        name="vbb_get_departures",
        description=(
            "Get departures at a stop/station in Berlin/Brandenburg. "
            "Returns real-time departure information including delays, platform, and line details."
        ),
    )
    async def vbb_get_departures(
        stop_id: Annotated[
            str,
            Field(description="Stop/station ID. Example: '900100003' for S+U Alexanderplatz", min_length=1),
        ],
        when: Annotated[
            Optional[str],
            Field(description="Date/time for departures (ISO 8601 or relative like 'tomorrow 2pm'). Default: now."),
        ] = None,
        duration: Annotated[
            Optional[int],
            Field(description="Show departures for how many minutes (default 10).", ge=1, le=1440),
        ] = None,
        results: Annotated[
            Optional[int],
            Field(description="Max number of departures.", ge=1, le=100),
        ] = None,
        direction: Annotated[
            Optional[str],
            Field(description="Filter departures by direction (stop ID)."),
        ] = None,
    ) -> Dict[str, Any]:
        stop_id_clean = stop_id.strip()
        if not stop_id_clean:
            raise ValueError("Stop ID cannot be empty")

        params: Dict[str, Any] = {}

        if when:
            params["when"] = when
        if duration:
            params["duration"] = int(duration)
        if results:
            params["results"] = int(results)
        if direction:
            params["direction"] = direction.strip()

        try:
            logger.info("Getting VBB departures for stop: %s", stop_id_clean)
            return await fetch_json(f"{VBB_BASE_URL}/stops/{stop_id_clean}/departures", params)
        except TransportAPIError as e:
            logger.error("VBB departures fetch failed: %s", e)
            raise

    @mcp.tool(
        name="vbb_get_arrivals",
        description=(
            "Get arrivals at a stop/station in Berlin/Brandenburg. "
            "Returns real-time arrival information including delays, platform, and line details."
        ),
    )
    async def vbb_get_arrivals(
        stop_id: Annotated[
            str,
            Field(description="Stop/station ID. Example: '900100003' for S+U Alexanderplatz", min_length=1),
        ],
        when: Annotated[
            Optional[str],
            Field(description="Date/time for arrivals (ISO 8601 or relative). Default: now."),
        ] = None,
        duration: Annotated[
            Optional[int],
            Field(description="Show arrivals for how many minutes (default 10).", ge=1, le=1440),
        ] = None,
        results: Annotated[
            Optional[int],
            Field(description="Max number of arrivals.", ge=1, le=100),
        ] = None,
    ) -> Dict[str, Any]:
        stop_id_clean = stop_id.strip()
        if not stop_id_clean:
            raise ValueError("Stop ID cannot be empty")

        params: Dict[str, Any] = {}

        if when:
            params["when"] = when
        if duration:
            params["duration"] = int(duration)
        if results:
            params["results"] = int(results)

        try:
            logger.info("Getting VBB arrivals for stop: %s", stop_id_clean)
            return await fetch_json(f"{VBB_BASE_URL}/stops/{stop_id_clean}/arrivals", params)
        except TransportAPIError as e:
            logger.error("VBB arrivals fetch failed: %s", e)
            raise

    @mcp.tool(
        name="vbb_search_journeys",
        description=(
            "Search for journeys between two locations in Berlin/Brandenburg. "
            "Returns connections with real-time data, transfers, duration, and line information. "
            "Supports departure or arrival time based planning."
        ),
    )
    async def vbb_search_journeys(
        origin: Annotated[
            str,
            Field(description="Origin stop ID or station name. Example: '900100003' or 'Alexanderplatz'", min_length=1),
        ],
        destination: Annotated[
            str,
            Field(description="Destination stop ID or station name. Example: '900017101' or 'Mehringdamm'", min_length=1),
        ],
        departure: Annotated[
            Optional[str],
            Field(description="Departure date/time (ISO 8601 or relative). Mutually exclusive with arrival."),
        ] = None,
        arrival: Annotated[
            Optional[str],
            Field(description="Arrival date/time (ISO 8601 or relative). Mutually exclusive with departure."),
        ] = None,
        results: Annotated[
            Optional[int],
            Field(description="Max number of journeys (default 3).", ge=1, le=10),
        ] = None,
        transfers: Annotated[
            Optional[int],
            Field(description="Maximum number of transfers.", ge=0, le=10),
        ] = None,
    ) -> Dict[str, Any]:
        origin_clean = origin.strip()
        destination_clean = destination.strip()

        if not origin_clean or not destination_clean:
            raise ValueError("Origin and destination cannot be empty")

        params: Dict[str, Any] = {
            "from": origin_clean,
            "to": destination_clean,
        }

        if departure:
            params["departure"] = departure
        if arrival:
            params["arrival"] = arrival
        if results:
            params["results"] = int(results)
        if transfers is not None:
            params["transfers"] = int(transfers)

        try:
            logger.info("Searching VBB journeys: %s -> %s", origin_clean, destination_clean)
            return await fetch_json(f"{VBB_BASE_URL}/journeys", params)
        except TransportAPIError as e:
            logger.error("VBB journey search failed: %s", e)
            raise

    @mcp.tool(
        name="vbb_nearby_stations",
        description=(
            "Find stops/stations near a location in Berlin/Brandenburg by coordinates. "
            "Returns nearby stops with distance information."
        ),
    )
    async def vbb_nearby_stations(
        latitude: Annotated[
            float,
            Field(description="Latitude in decimal degrees. Example: 52.521508", ge=-90, le=90),
        ],
        longitude: Annotated[
            float,
            Field(description="Longitude in decimal degrees. Example: 13.411267", ge=-180, le=180),
        ],
        results: Annotated[
            Optional[int],
            Field(description="Max number of results (default 8).", ge=1, le=50),
        ] = 8,
        distance: Annotated[
            Optional[int],
            Field(description="Maximum distance in meters.", ge=50, le=10000),
        ] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "results": int(results or 8),
        }

        if distance:
            params["distance"] = int(distance)

        try:
            logger.info("Finding VBB stations near: lat=%s, lon=%s", latitude, longitude)
            return await fetch_json(f"{VBB_BASE_URL}/locations/nearby", params)
        except TransportAPIError as e:
            logger.error("VBB nearby stations search failed: %s", e)
            raise

    return [
        vbb_search_locations,
        vbb_get_departures,
        vbb_get_arrivals,
        vbb_search_journeys,
        vbb_nearby_stations,
    ]
