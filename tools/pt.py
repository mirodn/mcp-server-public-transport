# tools/pt.py
"""
Portugal public transport tools for MCP server
Uses Transitous (api.transitous.org); see tools/transitous.py for the shared implementation.

Coverage is scoped to the Lisbon and Porto metro areas:
- Lisbon: Metro Lisboa, Carris, Carris Metropolitana, CP suburban
- Porto: Metro do Porto, STCP

Provides pt_search_stations, pt_search_connections, pt_get_departures, pt_nearby_stations.
No authentication required.
"""

from zoneinfo import ZoneInfo

from tools.transitous import TransitousRegion, register_transitous_tools

PT_REGION = TransitousRegion(
    prefix="pt",
    countries=frozenset({"PT"}),
    # both metro areas share the same zone
    tz=ZoneInfo("Europe/Lisbon"),
    # mainland Portugal
    bbox_min=(36.9, -9.6),
    bbox_max=(42.2, -6.1),
    country_name="Portugal",
    area="the Lisbon or Porto metro area",
    coverage="Covers the Lisbon and Porto metro areas (metro, buses, trams, suburban rail)",
    example_query="Trindade",
    example_origin="pt-Metro-Lisboa_MP",
    example_destination="pt-Metro-Lisboa_BC",
    example_stop_id="pt-Metro-Porto_5726",
    example_stop_name="Trindade",
    example_lat=41.15228,
    example_lon=-8.609299,
)


def register_pt_tools(mcp):
    """Register Portugal (Lisbon + Porto) transport tools with the MCP server."""
    return register_transitous_tools(mcp, PT_REGION)
