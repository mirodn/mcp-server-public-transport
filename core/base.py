"""
Base utilities for MCP public transport server
"""

import aiohttp
import asyncio
import logging
import atexit
from typing import Dict, Any, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class TransportAPIError(Exception):
    """Custom exception for transport API errors"""

    pass


# Shared session for connection pooling and reuse
_session: Optional[aiohttp.ClientSession] = None
_session_lock = asyncio.Lock()


async def get_session() -> aiohttp.ClientSession:
    """
    Get or create a shared aiohttp ClientSession.
    Uses connection pooling for better performance and resource management.
    Thread-safe via async lock.
    """
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "MCP-Public-Transport-Server/1.0",
                },
            )
        return _session


async def close_session() -> None:
    """Close the shared session. Call during shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
        logger.debug("Closed shared aiohttp session")


def _sync_close_session() -> None:
    """Synchronous wrapper for atexit. Best-effort cleanup."""
    global _session
    if _session and not _session.closed:
        # Create a new event loop for cleanup if needed
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(close_session())
        except RuntimeError:
            # No running loop, create a new one
            asyncio.run(close_session())


atexit.register(_sync_close_session)


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

    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    try:
        session = await get_session()

        # Override timeout for this specific request if different from default
        client_timeout = aiohttp.ClientTimeout(total=timeout)

        logger.debug("Fetching data from API endpoint")

        async with session.get(url, headers=request_headers, timeout=client_timeout) as response:
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
        logger.error(f"Request timeout for {url}")
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
