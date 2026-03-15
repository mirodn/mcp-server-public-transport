# tools/it.py
"""
Italian public transport tools for MCP server using GTFS Realtime protobuf feeds
"""

import logging
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated
from pydantic import Field

from core.base import fetch_json, TransportAPIError
from config import IT_BASE_URL

logger = logging.getLogger(__name__)


def register_it_tools(mcp):
    """Register Italian public transport tools with the MCP server"""

    @mcp.tool(
        name="it_get_vehicle_positions",
        description=(
            "Get real-time vehicle positions from Rome's public transport network. "
            "Powered by Rome Mobilità GTFS Realtime vehicle positions feed. "
            "Returns GPS coordinates, speed, heading, and trip information for buses and trams."
        ),
    )
    async def it_get_vehicle_positions(
        vehicle_type: Annotated[
            Optional[str],
            Field(
                description="Filter by vehicle type: 'bus', 'tram', or 'all' (default: 'all').",
                enum=["bus", "tram", "all"],
            ),
        ] = "all",
        limit: Annotated[
            Optional[int],
            Field(
                description="Max number of vehicles to return (default 100).",
                ge=1,
                le=1000,
            ),
        ] = 100,
    ) -> Dict[str, Any]:
        """
        Fetch and parse the GTFS Realtime vehicle positions protobuf feed from Rome Mobilità.
        
        Args:
            vehicle_type: Filter by vehicle type (bus, tram, or all)
            limit: Maximum number of vehicles to return
            
        Returns:
            Dictionary containing parsed vehicle positions data
        """
        try:
            logger.info("Fetching Italian vehicle positions (type=%s, limit=%d)", vehicle_type, limit)
            return await fetch_vehicle_positions(IT_BASE_URL, vehicle_type, limit)
        except TransportAPIError as e:
            logger.error("Italian vehicle positions fetch failed: %s", e, exc_info=True)
            raise

    return [it_get_vehicle_positions]


async def fetch_vehicle_positions(
    url: str,
    vehicle_type: str = "all",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Fetch and parse GTFS Realtime vehicle positions from a protobuf feed.
    
    Args:
        url: URL of the protobuf feed
        vehicle_type: Filter by vehicle type ('bus', 'tram', 'all')
        limit: Maximum number of vehicles to return
        
    Returns:
        Dictionary containing parsed vehicle positions
        
    Raises:
        TransportAPIError: If the request fails or parsing fails
    """
    import io
    import struct
    
    try:
        # Fetch the raw protobuf data
        timeout_obj = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise TransportAPIError(f"HTTP {response.status}: {error_text}")
                
                protobuf_data = await response.read()
    
    except asyncio.TimeoutError:
        raise TransportAPIError(f"Request timeout after 30 seconds")
    except aiohttp.ClientError as e:
        raise TransportAPIError(f"Network error: {e}")
    
    # Parse GTFS Realtime Vehicle Positions protobuf
    vehicles = parse_gtfs_vehicle_positions(protobuf_data, vehicle_type, limit)
    
    return {
        "feed": {
            "publisher": "Rome Mobilità",
            "language": "it",
            "start_time": vehicles.get("timestamp"),
        },
        "vehicles": vehicles.get("vehicles", []),
        "total_count": len(vehicles.get("vehicles", [])),
        "filtered_count": len([v for v in vehicles.get("vehicles", []) if vehicle_type == "all" or v.get("vehicle_type") == vehicle_type]),
    }


def parse_gtfs_vehicle_positions(data: bytes, vehicle_type: str = "all", limit: int = 100) -> Dict[str, Any]:
    """
    Parse GTFS Realtime Vehicle Positions protobuf data.
    
    GTFS Realtime uses Protocol Buffers with the following message structure:
    
    message FeedMessage {
      optional EntityCacheDuration entity_cache_duration = 8;
      repeated Entity entity = 1;
      optional String feed_info = 2;
      optional Timestamp timestamp = 3;
      optional String next_update = 4;
    }
    
    message Entity {
      optional String id = 1;
      optional VehiclePosition vehicle = 2;
      optional bool is_deleted = 3;
      optional MessageExtensions extensions = 4;
    }
    
    message VehiclePosition {
      optional TripDescriptor trip = 1;
      optional VehicleDescriptor vehicle = 2;
      optional Timestamp timestamp = 3;
      optional float position_lat = 4;
      optional float position_lon = 5;
      optional float heading = 6;
      optional float speed = 7;
      optional VehicleDescriptor vehicle_descriptor = 8;
      optional int32 occupancy_status = 9;
      optional MessageExtensions extensions = 10;
      optional int32 stop_sequence = 11;
      optional StopDescriptor current_stop_sequence = 12;
    }
    
    Args:
        data: Raw protobuf bytes
        vehicle_type: Filter by vehicle type
        limit: Maximum number of vehicles to return
        
    Returns:
        Dictionary with parsed vehicle data
    """
    vehicles = []
    timestamp = None
    
    # GTFS Realtime Vehicle Positions uses a simple protobuf encoding
    # We'll parse it manually since we don't have the .proto file
    
    # The feed message structure is:
    # Field 1 (Entity): tag = 0x0A (field 1, wire type 2 = length-delimited)
    # Field 3 (Timestamp): tag = 0x18 (field 3, wire type 0 = varint) followed by varint
    
    # Parse entities from the protobuf data
    entities = parse_protobuf_entities(data)
    
    for entity in entities:
        if "vehicle" in entity:
            vehicle = entity["vehicle"]
            
            # Filter by vehicle type
            v_type = vehicle.get("vehicle_type", "")
            if vehicle_type != "all" and v_type != vehicle_type:
                continue
            
            # Build vehicle position record
            position = vehicle.get("position", {})
            vehicle_record = {
                "id": entity.get("id", ""),
                "trip_id": vehicle.get("trip", {}).get("trip_id", ""),
                "route_id": vehicle.get("trip", {}).get("route_id", ""),
                "direction_id": vehicle.get("trip", {}).get("direction_id"),
                "vehicle_id": vehicle.get("vehicle", {}).get("id", ""),
                "vehicle_type": v_type,
                "latitude": position.get("lat"),
                "longitude": position.get("lon"),
                "heading": vehicle.get("heading"),
                "speed": vehicle.get("speed"),
                "timestamp": vehicle.get("timestamp"),
                "occupancy_status": vehicle.get("occupancy_status"),
                "stop_sequence": vehicle.get("stop_sequence"),
            }
            
            vehicles.append(vehicle_record)
            
            if len(vehicles) >= limit:
                break
    
    return {
        "timestamp": timestamp,
        "vehicles": vehicles,
    }


def parse_protobuf_entities(data: bytes) -> List[Dict[str, Any]]:
    """
    Parse protobuf entities from raw GTFS Realtime data.
    
    This is a simplified parser that handles the common GTFS Realtime structure.
    """
    entities = []
    pos = 0
    
    while pos < len(data):
        # Read field tag and wire type
        if pos >= len(data):
            break
            
        # Varint encoding for tag
        tag = 0
        shift = 0
        while True:
            if pos >= len(data):
                break
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if field_number == 1 and wire_type == 2:  # Entity message (field 1)
            entity = parse_protobuf_entity(data, pos)
            if entity:
                entities.append(entity)
                # Skip to next entity
                if "length" in entity:
                    pos += entity["length"]
                else:
                    break
        elif field_number == 3 and wire_type == 0:  # Timestamp (field 3)
            # Varint timestamp
            timestamp = 0
            shift = 0
            while pos < len(data):
                byte = data[pos]
                pos += 1
                timestamp |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
        else:
            # Skip unknown field
            if wire_type == 0:  # Varint
                while pos < len(data) and (data[pos] & 0x80) != 0:
                    pos += 1
                pos += 1
            elif wire_type == 1:  # 64-bit
                pos += 8
            elif wire_type == 2:  # Length-delimited
                if pos >= len(data):
                    break
                length = 0
                shift = 0
                while True:
                    if pos >= len(data):
                        break
                    byte = data[pos]
                    pos += 1
                    length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                pos += length
            elif wire_type == 5:  # 32-bit
                pos += 4
    
    return entities


def parse_protobuf_entity(data: bytes, pos: int) -> Optional[Dict[str, Any]]:
    """Parse a single protobuf entity message."""
    if pos >= len(data):
        return None
    
    entity = {"length": 0}
    start_pos = pos
    
    # Read length of entity message
    length = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    
    entity["length"] = length + 1  # Include the length byte itself
    
    # Parse entity fields
    end_pos = start_pos + length
    while pos < end_pos and pos < len(data):
        # Read field tag
        tag = 0
        shift = 0
        while pos < end_pos:
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if field_number == 1:  # Entity ID
            if pos < end_pos:
                field_length = 0
                shift = 0
                while pos < end_pos:
                    byte = data[pos]
                    pos += 1
                    field_length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                if pos + field_length <= end_pos:
                    entity["id"] = data[pos:pos + field_length].decode("utf-8", errors="ignore")
                    pos += field_length
                    
        elif field_number == 2 and wire_type == 2:  # VehiclePosition (nested message)
            vehicle = parse_protobuf_vehicle_position(data, pos, end_pos)
            if vehicle:
                entity["vehicle"] = vehicle
                # Update position to after the vehicle message
                if "length" in vehicle:
                    pos += vehicle["length"]
                    
        elif field_number == 3 and wire_type == 0:  # is_deleted
            value = 0
            while pos < end_pos:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            entity["is_deleted"] = value != 0
    
    return entity


def parse_protobuf_vehicle_position(data: bytes, pos: int, end_pos: int) -> Optional[Dict[str, Any]]:
    """Parse a VehiclePosition message."""
    if pos >= end_pos:
        return None
    
    vehicle = {"length": 0}
    start_pos = pos
    
    # Read length
    length = 0
    shift = 0
    while pos < end_pos:
        byte = data[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    
    vehicle["length"] = length
    
    # Parse vehicle position fields
    field_end = start_pos + length
    while pos < field_end and pos < end_pos:
        # Read field tag
        tag = 0
        shift = 0
        while pos < field_end:
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if field_number == 1 and wire_type == 2:  # Trip (nested)
            trip = parse_protobuf_trip(data, pos, field_end)
            if trip:
                vehicle["trip"] = trip
                if "length" in trip:
                    pos += trip["length"]
                    
        elif field_number == 2 and wire_type == 2:  # Vehicle (nested)
            vehicle_desc = parse_protobuf_vehicle_descriptor(data, pos, field_end)
            if vehicle_desc:
                vehicle["vehicle"] = vehicle_desc
                if "length" in vehicle_desc:
                    pos += vehicle_desc["length"]
                    
        elif field_number == 3 and wire_type == 0:  # Timestamp
            value = 0
            while pos < field_end:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            vehicle["timestamp"] = value
            
        elif field_number == 4 and wire_type == 5:  # Position lat (fixed32)
            if pos + 4 <= field_end:
                # Read as float
                import struct
                vehicle["position"] = {}
                vehicle["position"]["lat"] = struct.unpack("<f", data[pos:pos+4])[0]
                pos += 4
                
        elif field_number == 5 and wire_type == 5:  # Position lon (fixed32)
            if pos + 4 <= field_end:
                import struct
                if "position" not in vehicle:
                    vehicle["position"] = {}
                vehicle["position"]["lon"] = struct.unpack("<f", data[pos:pos+4])[0]
                pos += 4
                
        elif field_number == 6 and wire_type == 5:  # Heading (fixed32)
            if pos + 4 <= field_end:
                import struct
                vehicle["heading"] = struct.unpack("<f", data[pos:pos+4])[0]
                pos += 4
                
        elif field_number == 7 and wire_type == 5:  # Speed (fixed32)
            if pos + 4 <= field_end:
                import struct
                vehicle["speed"] = struct.unpack("<f", data[pos:pos+4])[0]
                pos += 4
                
        elif field_number == 9 and wire_type == 0:  # Occupancy status
            value = 0
            while pos < field_end:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            vehicle["occupancy_status"] = value
            
        elif field_number == 11 and wire_type == 0:  # Stop sequence
            value = 0
            while pos < field_end:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            vehicle["stop_sequence"] = value
    
    return vehicle


def parse_protobuf_trip(data: bytes, pos: int, end_pos: int) -> Optional[Dict[str, Any]]:
    """Parse a TripDescriptor message."""
    if pos >= end_pos:
        return None
    
    trip = {"length": 0}
    start_pos = pos
    
    # Read length
    length = 0
    shift = 0
    while pos < end_pos:
        byte = data[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    
    trip["length"] = length
    
    field_end = start_pos + length
    while pos < field_end and pos < end_pos:
        tag = 0
        shift = 0
        while pos < field_end:
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if field_number == 3 and wire_type == 2:  # Trip ID
            if pos < field_end:
                field_length = 0
                shift = 0
                while pos < field_end:
                    byte = data[pos]
                    pos += 1
                    field_length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                if pos + field_length <= field_end:
                    trip["trip_id"] = data[pos:pos + field_length].decode("utf-8", errors="ignore")
                    pos += field_length
                    
        elif field_number == 4 and wire_type == 2:  # Route ID
            if pos < field_end:
                field_length = 0
                shift = 0
                while pos < field_end:
                    byte = data[pos]
                    pos += 1
                    field_length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                if pos + field_length <= field_end:
                    trip["route_id"] = data[pos:pos + field_length].decode("utf-8", errors="ignore")
                    pos += field_length
                    
        elif field_number == 5 and wire_type == 0:  # Direction ID
            value = 0
            while pos < field_end:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            trip["direction_id"] = value
    
    return trip


def parse_protobuf_vehicle_descriptor(data: bytes, pos: int, end_pos: int) -> Optional[Dict[str, Any]]:
    """Parse a VehicleDescriptor message."""
    if pos >= end_pos:
        return None
    
    vehicle_desc = {"length": 0}
    start_pos = pos
    
    # Read length
    length = 0
    shift = 0
    while pos < end_pos:
        byte = data[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    
    vehicle_desc["length"] = length
    
    field_end = start_pos + length
    while pos < field_end and pos < end_pos:
        tag = 0
        shift = 0
        while pos < field_end:
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        field_number = tag >> 3
        wire_type = tag & 0x7
        
        if field_number == 1 and wire_type == 2:  # ID
            if pos < field_end:
                field_length = 0
                shift = 0
                while pos < field_end:
                    byte = data[pos]
                    pos += 1
                    field_length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                if pos + field_length <= field_end:
                    vehicle_desc["id"] = data[pos:pos + field_length].decode("utf-8", errors="ignore")
                    pos += field_length
                    
        elif field_number == 2 and wire_type == 0:  # Vehicle type
            value = 0
            while pos < field_end:
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            # GTFS vehicle type: 0=unknown, 1=train, 2=subway, 3=bus, 4=tram, 5=ship, 6=funicular, 7=trolleybus, 8=airplane
            vehicle_type_map = {
                0: "unknown",
                1: "train",
                2: "subway",
                3: "bus",
                4: "tram",
                5: "ship",
                6: "funicular",
                7: "trolleybus",
                8: "airplane",
            }
            vehicle_desc["vehicle_type"] = vehicle_type_map.get(value, f"unknown_{value}")
    
    return vehicle_desc


# Import required modules at module level
import aiohttp
import asyncio
import struct