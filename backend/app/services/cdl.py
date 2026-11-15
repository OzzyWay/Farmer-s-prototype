"""USDA NASS Cropland Data Layer (CDL), through the CropScape web service (no key needed).

The CDL is a 30 m satellite map of what grew where each year (lower 48 states only).
We ask CropScape for the land-cover category at the point for each recent year.

What CropScape sends back (seen in real responses):
- A value:    <Result>{x: ..., y: ..., value: 5, category: "Soybeans", color: "#267300"}</Result>
- No data:    value 0, category "No Data" (for example open water or outside the map)
- A fault:    <faultstring>Error: ...</faultstring> for a year not published yet, or a point
              outside CDL coverage (Alaska, Hawaii). This is an answer, not an outage.

The category can be a crop ("Corn") or other land cover ("Developed/Open Space",
"Grassland/Pasture"). We report it as-is so the farmer sees exactly what the CDL says.
"""
import asyncio
import re
from datetime import date

import httpx

from app.cache import DiskCache
from app.projection import to_albers
from app.records import make_record
from app.services.base import UPSTREAM_TIMEOUT

SOURCE = "USDA NASS CDL"
ATTEMPTS = 2
ATTEMPT_TIMEOUT = UPSTREAM_TIMEOUT / ATTEMPTS - 1  # 4 s each, 8 s worst case per year
CACHE_KEY = "cdl"
RESOLUTION_M = 30
URL = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLValue"
MAX_YEARS = 8

_RESULT_RE = re.compile(r"<Result>(.*?)</Result>", re.S)
_VALUE_RE = re.compile(r"\bvalue\s*:\s*(-?\d+)")
_CATEGORY_RE = re.compile(r'\bcategory\s*:\s*"([^"]*)"')
_FAULT_RE = re.compile(r"<faultstring>", re.I)

NO_VALUE = object()  # marker: CropScape answered but has no crop for that year


def parse_value(text: str):
    """Return the category name, or NO_VALUE when CropScape answered without a crop.

    Raises ValueError when the text is not a recognisable CropScape answer.
    """
    if _FAULT_RE.search(text or ""):
        return NO_VALUE
    m = _RESULT_RE.search(text or "")
    if not m:
        raise ValueError("no <Result> in CropScape response")
    body = m.group(1)
    value_m, cat_m = _VALUE_RE.search(body), _CATEGORY_RE.search(body)
    if not cat_m:
        raise ValueError("no category in CropScape response")
    category = cat_m.group(1).strip()
    if (value_m and int(value_m.group(1)) == 0) or not category or category.lower() in ("no data", "background"):
        return NO_VALUE
    return category


async def _get_with_retry(client, params: dict):
    """CropScape usually answers in under 2 s, but a random few requests hang and never
    answer. Waiting longer does not help; a fresh request usually does. So each attempt
    gets ATTEMPT_TIMEOUT seconds, with one retry after a timeout. Both attempts together
    stay within the 10 s limit for one upstream request."""
    for attempt in range(ATTEMPTS):
        try:
            return await asyncio.wait_for(client.get(URL, params=params), ATTEMPT_TIMEOUT)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            if attempt == ATTEMPTS - 1:
                raise


async def _one_year(client, year: int, x: float, y: float):
    """Fetch one year. Returns a category or NO_VALUE, raises on timeout/HTTP/parse errors."""
    params = {"year": year, "x": round(x, 3), "y": round(y, 3)}
    r = await _get_with_retry(client, params)
    # CropScape may send its "fault" answers with an error status, so check the body first.
    if _FAULT_RE.search(r.text or ""):
        return NO_VALUE
    r.raise_for_status()
    return parse_value(r.text)


async def fetch(client, lat: float, lon: float, cache: DiskCache, today: date | None = None) -> list:
    """Return one Feature_Record per year (newest first, up to 8). Raises on total failure."""
    cached = cache.read(CACHE_KEY, lat, lon)
    if cached is not None:
        return cached

    today = today or date.today()
    # This year's map is usually not published yet; asking anyway costs one fast fault reply
    # and means we pick it up automatically once it is out.
    years = list(range(today.year, today.year - MAX_YEARS - 1, -1))
    x, y = to_albers(lat, lon)
    results = await asyncio.gather(*(_one_year(client, yr, x, y) for yr in years), return_exceptions=True)

    errors = [r for r in results if isinstance(r, BaseException)]
    if len(errors) == len(results):
        # Every year failed: report the first problem so the reason is specific.
        raise errors[0]

    records = []
    for year, result in zip(years, results):
        if isinstance(result, BaseException) or result is NO_VALUE:
            continue  # skip that year, keep the others
        records.append(make_record("crop_type", SOURCE, RESOLUTION_M, str(year), result, ""))
        if len(records) == MAX_YEARS:
            break

    if not records and errors:
        # Nothing usable and some years failed (the rest were "not published" faults). That is
        # an outage, not "no crop history here", so report it instead of an empty answer.
        raise errors[0]

    if not errors:
        cache.write(CACHE_KEY, lat, lon, records)  # only cache a complete answer
    return records
