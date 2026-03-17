"""
Italian public transport tools for MCP server using GTFS Realtime protobuf feeds
"""

import asyncio
import logging
import aiohttp
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import TransportAPIError
from config import IT_BASE_URL

# Import generated GTFS protobuf classes
from gtfs_realtime_pb2 import FeedMessage, FeedEntity, VehiclePosition, TripDescriptor, Position, VehicleDescriptor

logger = logging.getLogger(__name__)


async def fetch_protobuf(url: str, timeout: int = 60) -> bytes:
    """
    Fetch binary protobuf data from a URL.
    
    Args:
        url: The URL to fetch from
        timeout: Request timeout in seconds
        
    Returns:
        Raw bytes of the protobuf feed
    """
    default_headers = {
        "User-Agent": "MCP-Public-Transport-Server/1.0",
        "Accept": "application/x-protobuf",
    }
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(
            timeout=timeout_obj, headers=default_headers
        ) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text}")
                    raise TransportAPIError(f"HTTP {response.status}: {error_text}")
                
                return await response.read()
                
    except asyncio.TimeoutError:
        logger.error("Request timeout for GTFS feed")
        raise TransportAPIError(f"Request timeout after {timeout} seconds")
    except aiohttp.ClientError as e:
        logger.error(f"Client error during GTFS feed request: {e}")
        raise TransportAPIError(f"Network error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during fetch: {e}")
        raise TransportAPIError(f"Unexpected error: {e}")


def parse_gtfs_realtime_feed(data: bytes) -> Dict[str, Any]:
    """
    Parse GTFS Realtime protobuf feed data using the official GTFS protobuf definitions.
    
    Args:
        data: Raw bytes of the protobuf feed
        
    Returns:
        Dictionary containing parsed feed data
    """
    result = {
        "header": {},
        "entities": []
    }
    
    try:
        # Parse the feed message
        feed = FeedMessage()
        feed.ParseFromString(data)
        
        # Parse header
        if feed.HasField('header'):
            result["header"] = {
                "gtfs_realtime_version": feed.header.gtfs_realtime_version,
                "timestamp": feed.header.timestamp,
                "feed_version": feed.header.feed_version,
            }
        
        # Parse entities
        for entity in feed.entity:
            feed_entity = _parse_feed_entity(entity)
            result["entities"].append(feed_entity)
            
    except Exception as e:
        logger.error(f"Error parsing GTFS realtime feed: {e}")
        raise TransportAPIError(f"Failed to parse GTFS realtime feed: {e}")
    
    return result


def _parse_feed_entity(entity: FeedEntity) -> Dict[str, Any]:
    """Parse a FeedEntity from the protobuf message."""
    feed_entity = {
        "id": entity.id,
        "is_deleted": entity.is_deleted,
        "vehicle": None,
        "trip_update": None,
        "alert": None
    }
    
    if entity.HasField('vehicle'):
        feed_entity["vehicle"] = _parse_vehicle_position(entity.vehicle)
    elif entity.HasField('trip_update'):
        feed_entity["trip_update"] = _parse_trip_update(entity.trip_update)
    elif entity.HasField('alert'):
        feed_entity["alert"] = _parse_alert(entity.alert)
    
    return feed_entity


def _safe_get_field(message, field_name: str) -> Any:
    """Safely get a field value from a protobuf message."""
    try:
        return getattr(message, field_name)
    except ValueError:
        return None


def _parse_vehicle_position(vehicle: VehiclePosition) -> Dict[str, Any]:
    """Parse a VehiclePosition from the protobuf message."""
    result = {
        "trip": None,
        "vehicle": None,
        "position": None,
        "current_stop_sequence": None,
        "stop_id": None,
        "current_status": None,
        "timestamp": None,
        "congestion_level": None,
        "occupancy_status": None,
        "occupancy_percentage": None
    }
    
    if vehicle.HasField('trip'):
        result["trip"] = _parse_trip_descriptor(vehicle.trip)
    
    if vehicle.HasField('vehicle'):
        result["vehicle"] = _parse_vehicle_descriptor(vehicle.vehicle)
    
    if vehicle.HasField('position'):
        position = vehicle.position
        result["position"] = {
            "latitude": position.latitude,
            "longitude": position.longitude,
            "bearing": _safe_get_field(position, 'bearing'),
            "odometer": _safe_get_field(position, 'odometer'),
            "speed": _safe_get_field(position, 'speed')
        }
    
    if vehicle.HasField('current_stop_sequence'):
        result["current_stop_sequence"] = vehicle.current_stop_sequence
    
    if vehicle.stop_id:
        result["stop_id"] = vehicle.stop_id
    
    if vehicle.HasField('current_status'):
        result["current_status"] = vehicle.current_status
    
    if vehicle.HasField('timestamp'):
        result["timestamp"] = vehicle.timestamp
    
    if vehicle.HasField('congestion_level'):
        result["congestion_level"] = vehicle.congestion_level
    
    if vehicle.HasField('occupancy_status'):
        result["occupancy_status"] = vehicle.occupancy_status
    
    if vehicle.HasField('occupancy_percentage'):
        result["occupancy_percentage"] = vehicle.occupancy_percentage
    
    return result


def _parse_trip_descriptor(trip: TripDescriptor) -> Dict[str, Any]:
    """Parse a TripDescriptor from the protobuf message."""
    result = {
        "trip_id": trip.trip_id,
        "route_id": trip.route_id,
        "direction_id": _safe_get_field(trip, 'direction_id'),
        "start_time": trip.start_time,
        "start_date": trip.start_date,
        "schedule_relationship": trip.schedule_relationship
    }
    return result


def _parse_vehicle_descriptor(vehicle: VehicleDescriptor) -> Dict[str, Any]:
    """Parse a VehicleDescriptor from the protobuf message."""
    result = {
        "id": vehicle.id,
        "label": vehicle.label,
        "license_plate": vehicle.license_plate,
        "wheelchair_accessible": vehicle.wheelchair_accessible
    }
    return result


def _parse_trip_update(trip_update: Any) -> Dict[str, Any]:
    """Parse a TripUpdate from the protobuf message."""
    return {
        "trip": _parse_trip_descriptor(trip_update.trip) if trip_update.HasField('trip') else None,
        "vehicle": _parse_vehicle_descriptor(trip_update.vehicle) if trip_update.HasField('vehicle') else None,
        "stop_time_update": [
            {
                "stop_sequence": stu.stop_sequence,
                "stop_id": stu.stop_id,
                "arrival": {"delay": stu.arrival.delay, "time": stu.arrival.time} if stu.HasField('arrival') else None,
                "departure": {"delay": stu.departure.delay, "time": stu.departure.time} if stu.HasField('departure') else None,
                "schedule_relationship": stu.schedule_relationship
            }
            for stu in trip_update.stop_time_update
        ],
        "timestamp": trip_update.timestamp if trip_update.HasField('timestamp') else None,
        "delay": trip_update.delay if trip_update.HasField('delay') else None
    }


def _parse_alert(alert: Any) -> Dict[str, Any]:
    """Parse an Alert from the protobuf message."""
    return {
        "active_period": [
            {"start": ap.start, "end": ap.end} for ap in alert.active_period
        ],
        "informed_entity": [
            {
                "agency_id": ie.agency_id,
                "route_id": ie.route_id,
                "route_type": ie.route_type,
                "stop_id": ie.stop_id
            }
            for ie in alert.informed_entity
        ],
        "cause": alert.cause,
        "effect": alert.effect,
        "header_text": alert.header_text.text if alert.HasField('header_text') else None,
        "description_text": alert.description_text.text if alert.HasField('description_text') else None
    }


def _detect_vehicle_type(route_id: str) -> str:
    """
    Detect vehicle type from route ID.
    
    Roma Mobilità uses specific patterns:
    - Bus routes: numeric or alphanumeric (e.g., '160', 'H', 'C1')
    - Tram routes: numeric with specific ranges (e.g., '2', '3', '5', '8', '19')
    - Metro routes: letter-based (e.g., 'A', 'B', 'C')
    """
    if not route_id:
        return "unknown"
    
    route_id = str(route_id).strip()
    
    # Metro lines are typically single letters A, B, C
    if len(route_id) == 1 and route_id.upper() in ['A', 'B', 'C']:
        return "metro"
    
    # Tram routes in Rome are typically: 2, 3, 5, 8, 19
    tram_routes = ['2', '3', '5', '8', '19']
    if route_id in tram_routes:
        return "tram"
    
    # If it starts with 'M' followed by a number, it's likely a metro
    if route_id.upper().startswith('M') and len(route_id) > 1:
        return "metro"
    
    # Default to bus for other routes
    return "bus"


def register_it_tools(mcp):
    """Register Italian public transport tools with the MCP server"""

    @mcp.tool(
        name="it_get_vehicle_positions",
        description=(
            "Get real-time vehicle positions from Rome public transport (Roma Mobilità). "
            "Returns GPS coordinates and trip information for buses, trams, and other vehicles. "
            "Uses GTFS Realtime protobuf feed from romamobilita.it."
        ),
    )
    async def it_get_vehicle_positions(
        vehicle_type: Annotated[
            Optional[str],
            Field(
                description=(
                    "Filter by vehicle type: 'bus', 'tram', 'metro', or 'all' (default: 'all'). "
                    "Note: Vehicle type is determined by route ID patterns in the feed."
                ),
            ),
        ] = None,
        limit: Annotated[
            Optional[int],
            Field(
                description="Maximum number of vehicles to return (default 50, max 200).",
                ge=1,
                le=200,
            ),
        ] = 50,
    ) -> Dict[str, Any]:
        """
        Get real-time vehicle positions from Rome public transport.
        
        Args:
            vehicle_type: Filter by vehicle type ('bus', 'tram', 'metro', or 'all')
            limit: Maximum number of vehicles to return
            
        Returns:
            Dictionary containing vehicle positions with GPS coordinates
        """
        try:
            logger.info("Fetching vehicle positions from Roma Mobilità (type=%s, limit=%d)", 
                       vehicle_type or "all", limit)
            
            # Fetch the protobuf feed as raw binary data
            feed_bytes = await fetch_protobuf(IT_BASE_URL, timeout=60)
            
            # Parse the GTFS realtime feed
            parsed = parse_gtfs_realtime_feed(feed_bytes)
            
            # Filter and format results
            vehicles = []
            for entity in parsed.get("entities", []):
                if entity.get("is_deleted"):
                    continue
                    
                vehicle_info = entity.get("vehicle")
                if not vehicle_info:
                    continue
                
                # Determine vehicle type from route info
                trip = vehicle_info.get("trip", {})
                vehicle_desc = vehicle_info.get("vehicle", {})
                position = vehicle_info.get("position", {})
                
                # Try to determine vehicle type from route ID
                trip_id = trip.get("trip_id", "") if trip else ""
                vehicle_type_detected = _detect_vehicle_type(trip_id)
                
                # Apply filter
                if vehicle_type and vehicle_type != "all":
                    if vehicle_type_detected != vehicle_type:
                        continue
                
                vehicles.append({
                    "id": entity.get("id", ""),
                    "vehicle_id": vehicle_desc.get("id", "") if vehicle_desc else "",
                    "vehicle_label": vehicle_desc.get("label", "") if vehicle_desc else "",
                    "vehicle_type": vehicle_type_detected,
                    "trip_id": trip_id,
                    "latitude": position.get("latitude") if position else None,
                    "longitude": position.get("longitude") if position else None,
                    "current_stop_sequence": vehicle_info.get("current_stop_sequence"),
                    "stop_id": vehicle_info.get("stop_id"),
                    "timestamp": parsed.get("header", {}).get("timestamp")
                })
            
            # Limit results
            vehicles = vehicles[:int(limit)]
            
            return {
                "success": True,
                "count": len(vehicles),
                "limit": limit,
                "vehicle_type_filter": vehicle_type or "all",
                "vehicles": vehicles,
                "source": "Roma Mobilità GTFS Realtime"
            }
            
        except TransportAPIError as e:
            logger.error("Italy vehicle positions fetch failed: %s", e, exc_info=True)
            raise
        except Exception as e:
            logger.error("Unexpected error fetching Italy vehicle positions: %s", e, exc_info=True)
            raise TransportAPIError(f"Failed to fetch vehicle positions: {e}")

    @mcp.tool(
        name="it_get_bus_positions",
        description=(
            "Get real-time bus positions from Rome public transport (Roma Mobilità). "
            "Returns GPS coordinates for buses currently operating in Rome."
        ),
    )
    async def it_get_bus_positions(
        limit: Annotated[
            Optional[int],
            Field(
                description="Maximum number of buses to return (default 50, max 200).",
                ge=1,
                le=200,
            ),
        ] = 50,
    ) -> Dict[str, Any]:
        """
        Get real-time bus positions from Rome public transport.
        
        Args:
            limit: Maximum number of buses to return
            
        Returns:
            Dictionary containing bus positions with GPS coordinates
        """
        return await it_get_vehicle_positions(vehicle_type="bus", limit=limit)

    @mcp.tool(
        name="it_get_tram_positions",
        description=(
            "Get real-time tram positions from Rome public transport (Roma Mobilità). "
            "Returns GPS coordinates for trams currently operating in Rome."
        ),
    )
    async def it_get_tram_positions(
        limit: Annotated[
            Optional[int],
            Field(
                description="Maximum number of trams to return (default 50, max 200).",
                ge=1,
                le=200,
            ),
        ] = 50,
    ) -> Dict[str, Any]:
        """
        Get real-time tram positions from Rome public transport.
        
        Args:
            limit: Maximum number of trams to return
            
        Returns:
            Dictionary containing tram positions with GPS coordinates
        """
        return await it_get_vehicle_positions(vehicle_type="tram", limit=limit)

    @mcp.tool(
        name="it_get_metro_positions",
        description=(
            "Get real-time metro positions from Rome public transport (Roma Mobilità). "
            "Returns GPS coordinates for metro trains currently operating in Rome."
        ),
    )
    async def it_get_metro_positions(
        limit: Annotated[
            Optional[int],
            Field(
                description="Maximum number of metro trains to return (default 50, max 200).",
                ge=1,
                le=200,
            ),
        ] = 50,
    ) -> Dict[str, Any]:
        """
        Get real-time metro positions from Rome public transport.
        
        Args:
            limit: Maximum number of metro trains to return
            
        Returns:
            Dictionary containing metro positions with GPS coordinates
        """
        return await it_get_vehicle_positions(vehicle_type="metro", limit=limit)

    return [
        it_get_vehicle_positions,
        it_get_bus_positions,
        it_get_tram_positions,
        it_get_metro_positions,
    ]