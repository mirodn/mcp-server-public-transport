"""
Compact, provider-independent response models.

Upstream APIs return large, provider-specific payloads (a 3-entry Swiss
stationboard is ~35 KB). Tools map them onto these models so every country
answers in the same shape and with a fraction of the tokens.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Stop(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class StopTime(BaseModel):
    """Planned/expected time and platform at one stop."""

    stop: Stop
    planned: Optional[str] = Field(None, description="Scheduled time, ISO 8601")
    expected: Optional[str] = Field(None, description="Real-time prediction, ISO 8601")
    delay_min: Optional[int] = None
    platform: Optional[str] = None


class Departure(BaseModel):
    line: Optional[str] = None
    category: Optional[str] = None
    destination: Optional[str] = None
    planned: Optional[str] = None
    expected: Optional[str] = None
    delay_min: Optional[int] = None
    platform: Optional[str] = None
    cancelled: Optional[bool] = None
    operator: Optional[str] = None
    remarks: List[str] = []


class DepartureBoard(BaseModel):
    station: Stop
    departures: List[Departure]


class Leg(BaseModel):
    walk: bool = False
    line: Optional[str] = None
    category: Optional[str] = None
    direction: Optional[str] = None
    departure: StopTime
    arrival: StopTime
    cancelled: Optional[bool] = None
    remarks: List[str] = []


class Journey(BaseModel):
    departure: Optional[str] = Field(None, description="Planned departure at origin, ISO 8601")
    arrival: Optional[str] = Field(None, description="Planned arrival at destination, ISO 8601")
    duration_min: Optional[int] = Field(None, description="Scheduled travel time in minutes")
    transfers: int = 0
    legs: List[Leg]


def journey_from_legs(legs: List[Leg], transfers: Optional[int] = None) -> Journey:
    """
    Build a Journey whose times come from the schedule of its first and last leg.

    Upstream journey-level times are inconsistent (some include delays), so
    planned leg times keep departure/arrival/duration comparable across providers.
    Real-time information stays on the legs.
    """
    departure = legs[0].departure.planned if legs else None
    arrival = legs[-1].arrival.planned if legs else None
    if transfers is None:
        transfers = max(0, sum(1 for leg in legs if not leg.walk) - 1)
    return Journey(
        departure=departure,
        arrival=arrival,
        duration_min=minutes_between(departure, arrival),
        transfers=transfers,
        legs=legs,
    )


class JourneyList(BaseModel):
    journeys: List[Journey]


def compact(model: BaseModel) -> Dict[str, Any]:
    """Dump a model without empty fields to keep tool output small."""
    data = model.model_dump(exclude_none=True)
    return _drop_empty_lists(data)


def _drop_empty_lists(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_empty_lists(v) for k, v in value.items() if v != []}
    if isinstance(value, list):
        return [_drop_empty_lists(v) for v in value]
    return value


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 timestamps, including offsets without colon (e.g. '+0200')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None


def iso(value: Optional[str]) -> Optional[str]:
    """Normalize a timestamp to ISO 8601 with a colon offset; pass through if unparseable."""
    parsed = parse_time(value)
    return parsed.isoformat() if parsed else value


def minutes_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    """Whole minutes from start to end; used for delays and durations."""
    start_dt, end_dt = parse_time(start), parse_time(end)
    if not start_dt or not end_dt:
        return None
    return round((end_dt - start_dt).total_seconds() / 60)


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return " ".join(_TAG_RE.sub(" ", text).split())
