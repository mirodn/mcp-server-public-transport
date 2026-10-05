"""
Base utilities for MCP public transport server
"""

import aiohttp
import asyncio
import copy
import json
import logging
import atexit
import time
from collections import OrderedDict
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode

from mcp.types import ToolAnnotations

logger = logging.getLogger(__name__)


class TransportAPIError(Exception):
    """Custom exception for transport API errors"""

    pass


# All tools only read public transport data from external APIs
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

# Cache lifetimes in seconds, picked per endpoint by the tools
CACHE_TTL_STATIC = 24 * 60 * 60  # station/location lookups
CACHE_TTL_PLAN = 60  # connection/journey searches
CACHE_TTL_LIVE = 30  # departure boards, live vehicle data

# Small in-memory TTL cache shared by all providers; spares upstream rate limits
_CACHE_MAX_ENTRIES = 256
_cache: "OrderedDict[Tuple[str, str, str], Tuple[float, Any]]" = OrderedDict()


def _cache_get(key: Tuple[str, str, str]) -> Optional[Any]:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, data = entry
    if expires_at < time.monotonic():
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return copy.deepcopy(data)


def _cache_set(key: Tuple[str, str, str], data: Any, ttl: float) -> None:
    _cache[key] = (time.monotonic() + ttl, copy.deepcopy(data))
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def clear_cache() -> None:
    """Drop all cached responses."""
    _cache.clear()


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
                    # Identify the client with contact info. Some upstreams (e.g.
                    # Transitous) require an identifying User-Agent in their usage policy.
                    "User-Agent": (
                        "MCP-Public-Transport-Server/1.0 "
                        "(+https://github.com/mirodn/mcp-server-public-transport)"
                    ),
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


def _is_retryable(status: int) -> bool:
    """Rate limits and server errors are worth another attempt."""
    return status == 429 or status >= 500


async def _backoff(attempt: int) -> None:
    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))


async def _request_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    tries: int = 3,
    cache_ttl: float = 0,
) -> Dict[str, Any]:
    """
    Send a request and return the parsed JSON body.

    Retries with exponential backoff on HTTP 429/5xx, timeouts and network errors.
    Every failure is raised as TransportAPIError. With cache_ttl > 0, successful
    responses are cached for that many seconds.
    """
    if params:
        url = f"{url}?{urlencode(params)}"

    cache_key = (method, url, json.dumps(json_body, sort_keys=True))
    if cache_ttl > 0:
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for API endpoint")
            return cached

    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    client_timeout = aiohttp.ClientTimeout(total=timeout)

    for attempt in range(1, tries + 1):
        try:
            session = await get_session()
            logger.debug("%s API endpoint (attempt %s/%s)", method, attempt, tries)

            async with session.request(
                method, url, json=json_body, headers=request_headers, timeout=client_timeout
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    if _is_retryable(response.status) and attempt < tries:
                        logger.warning("HTTP %s, retrying", response.status)
                        await _backoff(attempt)
                        continue
                    logger.error(f"HTTP {response.status}: {error_text}")
                    raise TransportAPIError(f"HTTP {response.status}: {error_text}")

                try:
                    data = await response.json(content_type=None)
                    logger.debug("Successfully fetched data from API endpoint")
                except Exception as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    raise TransportAPIError(f"Invalid JSON response: {e}")

                if cache_ttl > 0:
                    _cache_set(cache_key, data, cache_ttl)
                return data

        except TransportAPIError:
            raise
        except asyncio.TimeoutError:
            if attempt < tries:
                await _backoff(attempt)
                continue
            logger.error("Request timeout while fetching data from API")
            raise TransportAPIError(f"Request timeout after {timeout} seconds")
        except aiohttp.ClientError as e:
            if attempt < tries:
                await _backoff(attempt)
                continue
            logger.error(f"Client error during API request: {e}")
            raise TransportAPIError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {e}")
            raise TransportAPIError(f"Unexpected error: {e}")

    raise TransportAPIError("Exhausted retries without response")


async def fetch_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    tries: int = 3,
    cache_ttl: float = 0,
) -> Dict[str, Any]:
    """
    GET JSON data from a URL with optional parameters.

    Args:
        url: The URL to fetch from
        params: Optional query parameters
        headers: Optional HTTP headers
        timeout: Request timeout in seconds (default: 30)
        tries: Attempts on 429/5xx, timeouts and network errors (default: 3)
        cache_ttl: Seconds to cache a successful response; 0 disables (default)

    Returns:
        Dict containing the JSON response

    Raises:
        TransportAPIError: If the request fails or returns invalid JSON
    """
    return await _request_json(
        "GET", url, params=params, headers=headers, timeout=timeout, tries=tries,
        cache_ttl=cache_ttl,
    )


async def post_json(
    url: str,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    tries: int = 3,
    cache_ttl: float = 0,
) -> Dict[str, Any]:
    """POST a JSON body and return the JSON response. Same retry/error semantics as fetch_json."""
    return await _request_json(
        "POST", url, json_body=body, headers=headers, timeout=timeout, tries=tries,
        cache_ttl=cache_ttl,
    )


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
