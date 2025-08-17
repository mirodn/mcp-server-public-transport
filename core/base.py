"""
Base utilities for MCP public transport server
"""

import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class TransportAPIError(Exception):
    """Custom exception for transport API errors"""

    pass


async def fetch_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Fetch JSON data from a URL with optional parameters.

    Args:
        url: The URL to fetch from
        params: Optional query parameters
        headers: Optional HTTP headers
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dict containing the JSON response

    Raises:
        TransportAPIError: If the request fails or returns invalid JSON
    """
    if params:
        query_string = urlencode(params)
        url = f"{url}?{query_string}"

    default_headers = {
        "User-Agent": "MCP-Public-Transport-Server/1.0",
        "Accept": "application/json",
    }

    if headers:
        default_headers.update(headers)

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(
            timeout=timeout_obj, headers=default_headers
        ) as session:
            logger.debug(f"Fetching: endpoint")

            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text}")
                    raise TransportAPIError(f"HTTP {response.status}: {error_text}")

                try:
                    data = await response.json()
                    logger.debug(f"Successfully fetched data from API endpoint")
                    return data
                except Exception as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    raise TransportAPIError(f"Invalid JSON response: {e}")

    except asyncio.TimeoutError:
        logger.error("Request timeout for API endpoint")
        raise TransportAPIError(f"Request timeout after {timeout} seconds")
    except aiohttp.ClientError as e:
        logger.error(f"Client error during API request: {e}")
        raise TransportAPIError(f"Network error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during fetch: {e}")
        raise TransportAPIError(f"Unexpected error: {e}")


def format_time_for_api(time_str: str) -> str:
    """
    Format a given time string to HH:MM format required by transport.opendata.ch API.

    Args:
        time_str: Time string like '14:30' or '14.30'

    Returns:
        Formatted time string in HH:MM
    """
    # Replace dot with colon if present
    formatted = time_str.replace(".", ":").strip()

    # Validation: should have two parts
    parts = formatted.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid time format. Use HH:MM or HH.MM")

    # Make sure both parts are numeric
    hour, minute = parts
    if not (hour.isdigit() and minute.isdigit()):
        raise ValueError("Time must contain digits only")

    # Pad with leading zero if necessary
    hour = hour.zfill(2)
    minute = minute.zfill(2)

    return f"{hour}:{minute}"


def validate_station_name(station: str) -> str:
    """Validate and clean station name."""
    if not station or not station.strip():
        raise ValueError("Station name cannot be empty")

    cleaned = " ".join(station.strip().split())
    if len(cleaned) < 2:
        raise ValueError("Station name too short")
    return cleaned
