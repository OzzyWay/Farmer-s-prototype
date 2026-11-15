"""The shapes used for every fact the farm data endpoint returns.

A "Feature_Record" is one fact (for example "organic matter is 2.1 %") together
with where it came from. Every record has the same seven fields so the frontend
can show any fact and its source without special cases.

An "Unavailable_Entry" is what a source returns instead of records when it
failed or has nothing for the location.
"""
from typing import Literal, TypedDict

# The seven fields every Feature_Record must have.
RECORD_FIELDS = ("variable", "source", "resolution_m", "date", "value", "units", "live_or_cached")


class FeatureRecord(TypedDict):
    variable: str                 # what was measured, e.g. "temperature_mean"
    source: str                   # who published it, e.g. "NASA POWER"
    resolution_m: int             # how coarse the data is, in metres
    date: str                     # month "01".."12", a period "2016-2025", or a year "2024"
    value: float | int | str      # the number or text itself
    units: str                    # "°C", "mm", "%", ... ("" when there are none)
    live_or_cached: Literal["live", "cached"]  # fetched just now, or read from disk


def make_record(variable, source, resolution_m, date, value, units, live_or_cached="live") -> FeatureRecord:
    """Build a Feature_Record. Always use this so no field is ever forgotten."""
    if live_or_cached not in ("live", "cached"):
        raise ValueError("live_or_cached must be 'live' or 'cached'")
    return {
        "variable": variable,
        "source": source,
        "resolution_m": int(resolution_m),
        "date": str(date),
        "value": value,
        "units": units,
        "live_or_cached": live_or_cached,
    }


def is_valid_record(obj) -> bool:
    """True when obj is a dict with all seven fields and a valid live_or_cached."""
    return (
        isinstance(obj, dict)
        and all(f in obj for f in RECORD_FIELDS)
        and obj["live_or_cached"] in ("live", "cached")
    )


def ok_result(records: list) -> dict:
    """A source answered. An empty list means 'answered, but has nothing here'."""
    return {"status": "ok", "records": records}


def unavailable_result(source: str, reason: str) -> dict:
    """Unavailable_Entry: the source failed or has no data, with a short plain reason."""
    return {"status": "unavailable", "source": source, "reason": reason}
