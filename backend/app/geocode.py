"""Turn user input (street address or "lat, lon") into a US location.

Order of attempts:
1. "lat, lon" typed directly -> no network call.
2. US Census Geocoder (free, no key, US addresses only).
3. Nominatim / OpenStreetMap fallback (restricted to the US).
"""
import re

import httpx

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
TIMEOUT = 8.0

# Rough boxes covering the lower 48, Alaska and Hawaii. Good enough to reject
# obviously non-US points for a demo.
US_BOXES = [
    (24.0, 49.6, -125.0, -66.5),   # contiguous US
    (51.0, 71.6, -180.0, -129.0),  # Alaska
    (18.8, 22.4, -160.5, -154.5),  # Hawaii
]

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")


class GeocodeError(Exception):
    """Raised with a farmer-friendly message when a location can't be used."""


def is_in_us(lat: float, lon: float) -> bool:
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in US_BOXES)


def parse_coordinates(text: str):
    """Return (lat, lon) if the text looks like coordinates, else None."""
    m = COORD_RE.match(text)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise GeocodeError("Coordinates out of range. Use 'latitude, longitude', e.g. 30.2752, -98.872.")
    return lat, lon


OUTSIDE_US_MESSAGE = "That location is outside the US. This tool only covers US farms."


def check_location(lat_text, lon_text) -> tuple[float, float]:
    """Validate a location given as raw text (for example query parameters).

    Returns (lat, lon). Raises GeocodeError with a plain message when a value is
    missing, not a number, out of range, or outside the US. Reuses the same
    rules as the geocoder so they are not written twice.
    """
    if lat_text is None or lon_text is None:
        raise GeocodeError("Latitude and longitude are both required, e.g. lat=30.2752&lon=-98.872.")
    coords = parse_coordinates(f"{str(lat_text).strip()}, {str(lon_text).strip()}")
    if coords is None:
        raise GeocodeError("Latitude and longitude must be numbers, e.g. lat=30.2752&lon=-98.872.")
    if not is_in_us(*coords):
        raise GeocodeError(OUTSIDE_US_MESSAGE)
    return coords


def _result(lat, lon, label, source):
    if not is_in_us(lat, lon):
        raise GeocodeError(OUTSIDE_US_MESSAGE)
    return {"lat": round(lat, 6), "lon": round(lon, 6), "label": label, "source": source}


def _census(query: str, client: httpx.Client):
    r = client.get(CENSUS_URL, params={
        "address": query, "benchmark": "Public_AR_Current", "format": "json",
    })
    r.raise_for_status()
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    return _result(m["coordinates"]["y"], m["coordinates"]["x"], m["matchedAddress"], "US Census Geocoder")


def _nominatim(query: str, client: httpx.Client):
    r = client.get(NOMINATIM_URL, params={
        "q": query, "format": "json", "countrycodes": "us", "limit": 1,
    }, headers={"User-Agent": "FieldShift-hackathon-demo/0.1"})
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    h = hits[0]
    return _result(float(h["lat"]), float(h["lon"]), h.get("display_name", query), "OpenStreetMap Nominatim")


def geocode(query: str, client: httpx.Client | None = None) -> dict:
    query = (query or "").strip()
    if len(query) < 3:
        raise GeocodeError("Type a street address or coordinates like 30.2752, -98.872.")

    coords = parse_coordinates(query)
    if coords:
        return _result(*coords, f"{coords[0]}, {coords[1]}", "Entered coordinates")

    own_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        for service in (_census, _nominatim):
            try:
                hit = service(query, client)
                if hit:
                    return hit
            except GeocodeError:
                raise
            except (httpx.HTTPError, KeyError, ValueError):
                continue  # try the next service
    finally:
        if own_client:
            client.close()
    raise GeocodeError("Address not found. Check the spelling, add city and state, or enter coordinates.")
