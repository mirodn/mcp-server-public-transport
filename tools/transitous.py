# tools/transitous.py
"""
Shared Transitous (api.transitous.org) tool factory for MCP server
Transitous is a MOTIS instance routing over ingested GTFS feeds with global coverage.
Each country module (pt.py, it.py, ...) describes its region with a TransitousRegion
and calls register_transitous_tools to get the four standard tools:

- <prefix>_search_stations: find stops by name (scoped to the region)
- <prefix>_search_connections: plan a trip A -> B
- <prefix>_get_departures: departure board for a stop
- <prefix>_nearby_stations: find stops near coordinates

No authentication required.

Attribution: data is provided by Transitous (https://transitous.org), a best-effort,
volunteer-run service built on openly ingested GTFS feeds. Keep the attribution visible
to users and follow the usage policy at https://transitous.org/api/ (see also
https://transitous.org/sources/ for underlying feed/OpenStreetMap attribution).
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from typing_extensions import Annotated
from pydantic import Field

from core.base import (
    fetch_json,
    validate_station_name,
    TransportAPIError,
    format_time_for_api,
    READ_ONLY_TOOL,
    CACHE_TTL_LIVE,
    CACHE_TTL_PLAN,
    CACHE_TTL_STATIC,
)
from core.models import (
    RAW_FIELD,
    Departure,
    DepartureBoard,
    JourneyList,
    Leg,
    Stop,
    StopTime,
    compact,
    journey_from_legs,
    minutes_between,
    to_zone,
)
from config import TRANSITOUS_BASE_URL

logger = logging.getLogger(__name__)

# surfaced to users in each tool description; transitous wants attribution kept visible
ATTRIBUTION = (
    "Data via Transitous (https://transitous.org), a best-effort, volunteer-run service; "
    "usage policy: https://transitous.org/api/."
)


@dataclass(frozen=True)
class TransitousRegion:
    """Everything that differs between Transitous-backed countries."""

    prefix: str                       # tool name prefix, e.g. "pt"
    countries: FrozenSet[str]         # ISO codes kept from geocode hits
    tz: ZoneInfo                      # local zone for input and output times
    # geocode bounding box as (lat, lon) pairs; keeps hits inside the region upstream
    # so the country filter doesn't eat into the result count
    bbox_min: Tuple[float, float]
    bbox_max: Tuple[float, float]
    country_name: str                 # "Portugal"
    area: str                         # "the Lisbon or Porto metro area"
    coverage: str                     # "Covers ... " sentence for station search
    example_query: str
    example_origin: str
    example_destination: str
    example_stop_id: str
    example_stop_name: str
    example_lat: float
    example_lon: float

    @property
    def label(self) -> str:
        return self.prefix.upper()


def to_iso(date: Optional[str], time: Optional[str], tz: ZoneInfo) -> Optional[str]:
    """Combine date (YYYY-MM-DD) and time (HH:MM) into an rfc3339 string.

    motis rejects naive timestamps so we attach the local offset. missing parts
    fall back to today / midnight. returns None when nothing was given (motis
    then defaults to now).
    """
    if not date and not time:
        return None

    now = datetime.now(tz)
    if date:
        y, m, d = (int(p) for p in date.split("-"))
    else:
        y, m, d = now.year, now.month, now.day

    hh, mm = (0, 0)
    if time:
        hh, mm = (int(p) for p in format_time_for_api(time).split(":"))

    local = datetime(y, m, d, hh, mm, tzinfo=tz)
    return local.isoformat()


def _in_region(hits: List[Dict[str, Any]], countries: FrozenSet[str], limit: int) -> List[Dict[str, Any]]:
    """Keep hits from the region's countries only and trim. geocode is global so we filter here."""
    return [h for h in hits if h.get("country") in countries][:limit]


def _stop(place: Dict[str, Any]) -> Stop:
    # legs reference platform-level stops (e.g. "it-trenitalia_08409"); the parent id
    # (e.g. "it-trenitalia_08409:station") is what the tools accept
    return Stop(id=place.get("parentId") or place.get("stopId"), name=place.get("name"))


def _stop_time(place: Dict[str, Any], kind: str, realtime: bool, tz: ZoneInfo) -> StopTime:
    """Map a MOTIS place; kind is 'departure' or 'arrival'. Times come in UTC."""
    planned = to_zone(place.get("scheduled" + kind.capitalize()) or place.get(kind), tz)
    expected = to_zone(place.get(kind), tz) if realtime else None
    return StopTime(
        stop=_stop(place),
        planned=planned,
        expected=expected,
        delay_min=minutes_between(planned, expected) if expected else None,
        platform=place.get("track") or place.get("scheduledTrack"),
    )


def _line(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    mode = item.get("mode")
    return {
        "line": item.get("displayName") or item.get("routeShortName") or None,
        "category": mode.title() if mode else None,
    }


def _departure(stop_time: Dict[str, Any], tz: ZoneInfo) -> Departure:
    at_stop = _stop_time(stop_time.get("place") or {}, "departure", bool(stop_time.get("realTime")), tz)
    return Departure(
        **_line(stop_time),
        destination=stop_time.get("headsign"),
        planned=at_stop.planned,
        expected=at_stop.expected,
        delay_min=at_stop.delay_min,
        platform=at_stop.platform,
        cancelled=bool(stop_time.get("cancelled") or stop_time.get("tripCancelled")) or None,
        operator=stop_time.get("agencyName") or None,
    )


def _leg(leg: Dict[str, Any], tz: ZoneInfo) -> Leg:
    realtime = bool(leg.get("realTime"))
    walk = leg.get("mode") == "WALK"
    line = {"line": None, "category": None} if walk else _line(leg)
    return Leg(
        walk=walk,
        **line,
        direction=None if walk else leg.get("headsign"),
        departure=_stop_time(leg.get("from") or {}, "departure", realtime, tz),
        arrival=_stop_time(leg.get("to") or {}, "arrival", realtime, tz),
        cancelled=bool(leg.get("cancelled")) or None,
    )


def register_transitous_tools(mcp, region: TransitousRegion):
    """Register the four Transitous tools for one region with the MCP server."""
    p, label, tz = region.prefix, region.label, region.tz

    @mcp.tool(
        name=f"{p}_search_stations",
        annotations=READ_ONLY_TOOL,
        description=(
            f"Search for stops/stations in {region.country_name} by name. "
            f"{region.coverage} "
            "via Transitous. Returns stop id, name and coordinates - use the id with "
            f"{p}_search_connections and {p}_get_departures. "
            + ATTRIBUTION
        ),
    )
    async def search_stations(
        query: Annotated[
            str,
            Field(description=f"Station/stop search query. Example: '{region.example_query}'", min_length=1),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max number of results (default 10).", ge=1, le=50),
        ] = 10,
    ) -> List[Dict[str, Any]]:
        query_clean = validate_station_name(query)
        n = int(limit or 10)

        params = {
            "text": query_clean,
            "type": "STOP",
            # upstream defaults to 10 hits; over-fetch so the country filter
            # (border stops inside the bbox) can't leave us short
            "numResults": n * 2,
            "min": f"{region.bbox_min[0]},{region.bbox_min[1]}",
            "max": f"{region.bbox_max[0]},{region.bbox_max[1]}",
        }

        try:
            logger.info("Searching %s stations: %s", label, query_clean)
            hits = await fetch_json(f"{TRANSITOUS_BASE_URL}/geocode", params, cache_ttl=CACHE_TTL_STATIC)
            return _in_region(hits, region.countries, n)
        except TransportAPIError as e:
            logger.error("%s station search failed: %s", label, e)
            raise

    @mcp.tool(
        name=f"{p}_search_connections",
        annotations=READ_ONLY_TOOL,
        description=(
            f"Plan a public transport connection between two points in {region.area}. "
            f"Origin and destination are either stop ids (from {p}_search_stations) "
            "or 'lat,lon' coordinates. Returns a compact list of journeys with legs, lines, local "
            "times and transfers; set raw=true for the full upstream response. "
            + ATTRIBUTION
        ),
    )
    async def search_connections(
        origin: Annotated[
            str,
            Field(description=f"Origin stop id or 'lat,lon'. Example: '{region.example_origin}'", min_length=1),
        ],
        destination: Annotated[
            str,
            Field(
                description=f"Destination stop id or 'lat,lon'. Example: '{region.example_destination}'",
                min_length=1,
            ),
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
        raw: Annotated[bool, RAW_FIELD] = False,
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

        when = to_iso(date, time, tz)
        if when:
            params["time"] = when
        if is_arrival_time:
            params["arriveBy"] = "true"

        try:
            logger.info("Planning %s connection: %s -> %s", label, origin_clean, destination_clean)
            data = await fetch_json(f"{TRANSITOUS_BASE_URL}/plan", params, cache_ttl=CACHE_TTL_PLAN)
        except TransportAPIError as e:
            logger.error("%s connection search failed: %s", label, e)
            raise

        if raw:
            return data
        # numItineraries is a minimum for MOTIS, so trim to what was asked for
        itineraries = (data.get("itineraries") or [])[: int(limit or 4)]
        journeys = [
            journey_from_legs([_leg(leg, tz) for leg in it.get("legs") or []], transfers=it.get("transfers"))
            for it in itineraries
        ]
        return compact(JourneyList(journeys=journeys))

    @mcp.tool(
        name=f"{p}_get_departures",
        annotations=READ_ONLY_TOOL,
        description=(
            f"Get the departure board for a stop in {region.area}. "
            f"Needs a stop id from {p}_search_stations. Returns upcoming departures with "
            "line, headsign and real-time times in local time; set raw=true for the full "
            "upstream response. "
            + ATTRIBUTION
        ),
    )
    async def get_departures(
        stop_id: Annotated[
            str,
            Field(
                description=f"Stop id. Example: '{region.example_stop_id}' for {region.example_stop_name}",
                min_length=1,
            ),
        ],
        limit: Annotated[
            Optional[int],
            Field(description="Max departures to return (default 10).", ge=1, le=50),
        ] = 10,
        time: Annotated[
            Optional[str],
            Field(description="Date/time as rfc3339 (optional). Default: now."),
        ] = None,
        raw: Annotated[bool, RAW_FIELD] = False,
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
            logger.info("Getting %s departures for stop: %s", label, stop_id_clean)
            data = await fetch_json(f"{TRANSITOUS_BASE_URL}/stoptimes", params, cache_ttl=CACHE_TTL_LIVE)
        except TransportAPIError as e:
            logger.error("%s departures fetch failed: %s", label, e)
            raise

        if raw:
            return data
        board = DepartureBoard(
            station=_stop(data.get("place") or {"stopId": stop_id_clean}),
            # n is a minimum for MOTIS, so trim to what was asked for
            departures=[_departure(st, tz) for st in (data.get("stopTimes") or [])[: int(limit or 10)]],
        )
        return compact(board)

    @mcp.tool(
        name=f"{p}_nearby_stations",
        annotations=READ_ONLY_TOOL,
        description=(
            f"Find stops/stations near coordinates in {region.area}. "
            "Returns the closest stops with id, name and coordinates. "
            + ATTRIBUTION
        ),
    )
    async def nearby_stations(
        latitude: Annotated[
            float,
            Field(description=f"Latitude in decimal degrees. Example: {region.example_lat}", ge=-90, le=90),
        ],
        longitude: Annotated[
            float,
            Field(description=f"Longitude in decimal degrees. Example: {region.example_lon}", ge=-180, le=180),
        ],
        results: Annotated[
            Optional[int],
            Field(description="Max number of results (default 8).", ge=1, le=50),
        ] = 8,
    ) -> List[Dict[str, Any]]:
        n = int(results or 8)
        # reverse-geocode wants "lat,lon"; it defaults to 5 hits, so ask for more
        # than we need to leave room for the country filter near borders
        params = {
            "place": f"{float(latitude)},{float(longitude)}",
            "type": "STOP",
            "numResults": n * 2,
        }

        try:
            logger.info("Finding %s stations near provided coordinates", label)
            hits = await fetch_json(f"{TRANSITOUS_BASE_URL}/reverse-geocode", params, cache_ttl=CACHE_TTL_STATIC)
            return _in_region(hits, region.countries, n)
        except TransportAPIError as e:
            logger.error("%s nearby stations search failed: %s", label, e)
            raise

    return [
        search_stations,
        search_connections,
        get_departures,
        nearby_stations,
    ]
