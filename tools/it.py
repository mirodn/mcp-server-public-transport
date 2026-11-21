# tools/it.py
"""
Italy public transport tools for MCP server
Uses Transitous (api.transitous.org); see tools/transitous.py for the shared implementation.

Coverage is national:
- Trenitalia national rail (high-speed, long-distance, regional, night)
- Regional GTFS feeds (metro, tram, bus) across the country

Provides it_search_stations, it_search_connections, it_get_departures, it_nearby_stations.
No authentication required.
"""

from zoneinfo import ZoneInfo

from tools.transitous import TransitousRegion, register_transitous_tools

IT_REGION = TransitousRegion(
    prefix="it",
    # San Marino and Vatican City are enclaves served by the same feeds
    countries=frozenset({"IT", "SM", "VA"}),
    # all of Italy shares a single zone (CET/CEST)
    tz=ZoneInfo("Europe/Rome"),
    # Lampedusa to South Tyrol, Aosta Valley to Salento
    bbox_min=(35.4, 6.6),
    bbox_max=(47.1, 18.6),
    country_name="Italy",
    area="Italy",
    coverage="Covers national rail (Trenitalia) plus regional metro, tram and bus networks",
    example_query="Roma Termini",
    example_origin="it-trenitalia_08409:station",
    example_destination="it-trenitalia_01700:station",
    example_stop_id="it-trenitalia_08409:station",
    example_stop_name="Roma Termini",
    example_lat=41.9005,
    example_lon=12.50203,
)


def register_it_tools(mcp):
    """Register Italy transport tools with the MCP server."""
    return register_transitous_tools(mcp, IT_REGION)
