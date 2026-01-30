# tools/no.py
"""
Norway (Entur) public transport tools for the MCP server.

Provides:
- no_search_places(text, lang="en", size=10)
- no_stop_departures(stop_place_id, limit=10)
- no_trip(from_id, to_id, date_time=None, results=5)
- no_nearest_stops(lat, lon, radius=500, limit=10)

Notes:
- Entur requires the `ET-Client-Name` header. We use the fixed value
  "miro-mcp-public-transport" for a plug-and-play developer experience.
  

"""

from __future__ import annotations

import asyncio
import logging
from typing_extensions import Annotated
from pydantic import Field

import aiohttp

# -----------------------------------------------------------------------------
# Optional reuse of project helpers (if available), otherwise safe fallbacks
# -----------------------------------------------------------------------------
try:
    from core.base import TransportAPIError, fetch_json  # type: ignore
except Exception:  # Fallbacks if your project doesn't expose these
    class TransportAPIError(RuntimeError):
        """Generic transport API error."""

    async def fetch_json(
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> dict[str, object]:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise TransportAPIError(f"HTTP {resp.status} for {url}: {text}")
                return await resp.json()

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Entur constants (no env needed)
# -----------------------------------------------------------------------------
NO_CLIENT_NAME = "miro-mcp-public-transport"
NO_JP_BASE_URL = "https://api.entur.io/journey-planner/v3/graphql"
NO_GEOCODER_AUTOCOMPLETE_URL = "https://api.entur.io/geocoder/v1/autocomplete"

COMMON_HEADERS: dict[str, str] = {
    "ET-Client-Name": NO_CLIENT_NAME,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# -----------------------------------------------------------------------------
# Timeouts & simple retry/backoff
# -----------------------------------------------------------------------------
DEFAULT_TOTAL_TIMEOUT = 30  # seconds
DEFAULT_CONNECT_TIMEOUT = 10


def _make_timeout(total: int = DEFAULT_TOTAL_TIMEOUT) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(
        total=total,
        connect=DEFAULT_CONNECT_TIMEOUT,
        sock_connect=DEFAULT_CONNECT_TIMEOUT,
        sock_read=max(5, total - 5),
    )


# -----------------------------------------------------------------------------
# GraphQL helper
# -----------------------------------------------------------------------------
async def _post_graphql(
    query: str,
    variables: dict[str, object] | None = None,
    timeout: int = DEFAULT_TOTAL_TIMEOUT,
    tries: int = 3,
) -> dict[str, object]:
    """POST a GraphQL query to Entur Journey Planner v3 and return the `data` field."""
    payload = {"query": query, "variables": variables or {}}

    for attempt in range(1, tries + 1):
        try:
            async with aiohttp.ClientSession(headers=COMMON_HEADERS, timeout=_make_timeout(timeout)) as session:
                async with session.post(NO_JP_BASE_URL, json=payload, timeout=_make_timeout(timeout)) as resp:
                    # Retry on rate limit or server errors
                    if resp.status == 429 or resp.status >= 500:
                        text = await resp.text()
                        if attempt < tries:
                            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                            continue
                        raise TransportAPIError(f"Entur GraphQL HTTP {resp.status}: {text}")

                    if resp.status >= 400:
                        text = await resp.text()
                        raise TransportAPIError(f"Entur GraphQL HTTP {resp.status}: {text}")

                    data = await resp.json()
                    if "errors" in data and data["errors"]:
                        raise TransportAPIError(f"Entur GraphQL errors: {data['errors']}")
                    return data.get("data", {})
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
            if attempt < tries:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise TransportAPIError(f"Entur GraphQL timeout after {tries} attempt(s): {e}") from e

    raise TransportAPIError("Entur GraphQL: exhausted retries without response")


# -----------------------------------------------------------------------------
# Tool registration
# -----------------------------------------------------------------------------
def register_no_tools(mcp):
    """Register Norway (Entur) tools with the MCP server."""

    @mcp.tool(
        name="no_search_places",
        description="Autocomplete search across stops/addresses/POIs in Norway via Entur Geocoder.",
    )
    async def no_search_places(
        text: Annotated[str, Field(description="Free-text query. Example: 'Oslo S'", min_length=1)],
        lang: Annotated[str | None, Field(description="Language hint ('en','no','nb','nn',...). Default 'en'.")] = "en",
        size: Annotated[int | None, Field(description="Max results (default 10).", ge=1, le=50)] = 10,
    ) -> dict[str, object]:
        if not text or not text.strip():
            raise ValueError("Parameter 'text' must not be empty.")

        params = {"text": text.strip(), "lang": (lang or "en"), "size": int(size or 10)}
        logger.info("🇳🇴 Entur geocoder autocomplete: %r", params)

        tries = 3
        for attempt in range(1, tries + 1):
            try:
                async with aiohttp.ClientSession(timeout=_make_timeout()) as session:
                    async with session.get(
                        NO_GEOCODER_AUTOCOMPLETE_URL,
                        params=params,
                        headers={"ET-Client-Name": NO_CLIENT_NAME, "Accept": "application/json"},
                        timeout=_make_timeout(),
                    ) as resp:
                        if resp.status == 429 or resp.status >= 500:
                            if attempt < tries:
                                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                                continue
                            text_body = await resp.text()
                            raise TransportAPIError(f"Entur Geocoder HTTP {resp.status}: {text_body}")

                        if resp.status >= 400:
                            text_body = await resp.text()
                            raise TransportAPIError(f"Entur Geocoder HTTP {resp.status}: {text_body}")

                        return await resp.json()
            except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
                if attempt < tries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise TransportAPIError(f"Entur Geocoder timeout after {tries} attempt(s): {e}") from e

        raise TransportAPIError("Entur Geocoder: exhausted retries without response")

    @mcp.tool(
        name="no_stop_departures",
        description="Upcoming departures for a StopPlace ID (e.g., 'NSR:StopPlace:58368').",
    )
    async def no_stop_departures(
        stop_place_id: Annotated[str, Field(description="NSR StopPlace ID. Example: 'NSR:StopPlace:58368'", min_length=1)],
        limit: Annotated[int | None, Field(description="Number of departures to fetch (default 10).", ge=1, le=50)] = 10,
    ) -> dict[str, object]:
        if not stop_place_id or not stop_place_id.strip():
            raise ValueError("Parameter 'stop_place_id' must not be empty.")

        query = """
        query StopDepartures($id: String!, $limit: Int!) {
          stopPlace(id: $id) {
            id
            name
            estimatedCalls(numberOfDepartures: $limit) {
              realtime
              aimedDepartureTime
              expectedDepartureTime
              destinationDisplay { frontText }
              quay { id name }
              serviceJourney {
                id
                line { id name publicCode transportMode }
              }
            }
          }
        }
        """
        variables = {"id": stop_place_id.strip(), "limit": int(limit or 10)}
        logger.info("Entur stop departures: %s (limit=%s)", variables["id"], variables["limit"])
        return await _post_graphql(query, variables)

    @mcp.tool(
        name="no_trip",
        description="Door-to-door trip planning between two StopPlaces (NSR IDs).",
    )
    async def no_trip(
        from_id: Annotated[str, Field(description="Origin StopPlace NSR ID. Example: 'NSR:StopPlace:58368'", min_length=1)],
        to_id: Annotated[str, Field(description="Destination StopPlace NSR ID.", min_length=1)],
        date_time: Annotated[str | None, Field(description="ISO 8601 datetime (optional). Example: '2026-01-30T12:00:00+01:00'")] = None,
        results: Annotated[int | None, Field(description="Number of trip patterns (default 5).", ge=1, le=10)] = 5,
    ) -> dict[str, object]:
        if not from_id or not to_id:
            raise ValueError("'from_id' and 'to_id' are required.")

        query = """
        query PlanTrip($from: String!, $to: String!, $results: Int!, $dateTime: DateTime) {
          trip(
            from: { place: $from }
            to:   { place: $to }
            numTripPatterns: $results
            dateTime: $dateTime
          ) {
            tripPatterns {
              duration
              walkDistance
              legs {
                mode
                distance
                aimedStartTime
                expectedStartTime
                aimedEndTime
                expectedEndTime
                fromPlace { name }
                toPlace { name }
                line { id name publicCode transportMode }
              }
            }
          }
        }
        """
        variables = {
            "from": from_id.strip(),
            "to": to_id.strip(),
            "results": int(results or 5),
            "dateTime": date_time,
        }
        logger.info(
            "🇳🇴 Entur trip: %s -> %s (results=%s, dateTime=%s)",
            variables["from"], variables["to"], variables["results"], variables["dateTime"]
        )
        return await _post_graphql(query, variables)

    @mcp.tool(
        name="no_nearest_stops",
        description="Find nearest StopPlaces for a coordinate (lat, lon) within a radius in meters.",
    )
    async def no_nearest_stops(
        lat: Annotated[float, Field(description="Latitude.", ge=-90, le=90)],
        lon: Annotated[float, Field(description="Longitude.", ge=-180, le=180)],
        radius: Annotated[int | None, Field(description="Max distance in meters (default 500).", ge=50, le=50000)] = 500,
        limit: Annotated[int | None, Field(description="Max number of stops to return (default 10).", ge=1, le=50)] = 10,
    ) -> dict[str, object]:
        query = """
        query Nearest($lat: Float!, $lon: Float!, $radius: Int!, $first: Int!) {
          nearest(
            latitude: $lat,
            longitude: $lon,
            maximumDistance: $radius,
            filterByPlaceTypes: [stopPlace],
            first: $first
          ) {
            edges {
              node {
                distance
                place {
                  ... on StopPlace { id name }
                }
              }
            }
          }
        }
        """
        variables = {
            "lat": float(lat),
            "lon": float(lon),
            "radius": int(radius or 500),
            "first": int(limit or 10),
        }
        logger.info(
            "Entur nearest stops: lat=%s lon=%s radius=%s first=%s",
            variables["lat"], variables["lon"], variables["radius"], variables["first"]
        )
        return await _post_graphql(query, variables)

    # IMPORTANT: return functions (consistent with other modules)
    return [no_search_places, no_stop_departures, no_trip, no_nearest_stops]
