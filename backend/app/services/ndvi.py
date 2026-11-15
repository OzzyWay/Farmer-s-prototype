"""How green the field looks from space: MODIS NDVI from the ORNL DAAC web service (NASA, no login).

NDVI (normalized difference vegetation index) compares the red and near-infrared light a
surface reflects. Bare soil is about 0.1-0.2; sparse or dormant cover 0.2-0.4; growing
crops and grass 0.5-0.9.

Product: MOD13Q1 (Terra), 250 m pixels, one value every 16 days (the best day of each window).
Service: https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset, at most 10 dates per request.

What the probe on 2026-11-15 found for Webberwood: each request took 20-37 s, so 10 years
(about 230 dates, 2 bands) would take about 20 minutes. The team chose (2026-11-15) to use the
last 3 complete years and to prepare the result in advance for demo farms with
scripts/build_ndvi.py, the same way as the climate outlook. Other places say "not prepared".

Quality: each value has a pixel reliability rank. 0 (good) and 1 (marginal) are kept;
2 (snow or ice), 3 (cloudy) and -1 (no data) are dropped.

Bare-month rule: a month counts as bare in a year when the HIGHEST good NDVI in that month
is below 0.25 (BARE_NDVI), a common cut-off between bare or very sparse cover and plants.
The highest value is used so one hazy composite does not make a green month look bare.

IMPORTANT: a 250 m pixel is about 6 hectares (15 acres), so it can include land outside the
field (roads, trees, a neighbour's crop).
"""
import asyncio
import statistics
from datetime import date, timedelta

import httpx

from app.services.base import SourceUnavailable, get_json

SOURCE = "NASA MODIS MOD13Q1 (ORNL DAAC)"
RESOLUTION_M = 250
BASE = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
NDVI_BAND = "250m_16_days_NDVI"
QA_BAND = "250m_16_days_pixel_reliability"
SCALE = 0.0001
GOOD_RANKS = (0, 1)
BARE_NDVI = 0.25
YEARS = 3
MAX_DATES = 10          # the service's limit per request
CONCURRENT = 3          # polite: a few requests at a time
REQUEST_TIMEOUT = 90.0  # the service is slow (20-37 s per request in the probe)
ATTEMPTS = 3            # it sometimes answers 502 Proxy Error; try again after a pause
RETRY_WAIT_S = 20.0


# ---------- turning responses into a series ----------

def parse_subset(doc: dict) -> dict[str, float | int]:
    """{calendar_date: raw value} from one subset response (a single pixel)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("subset"), list):
        raise SourceUnavailable("NASA MODIS sent data we could not read")
    out = {}
    for row in doc["subset"]:
        try:
            out[str(row["calendar_date"])] = row["data"][0]
        except (KeyError, IndexError, TypeError):
            continue
    return out


def combine(ndvi_raw: dict, qa_raw: dict) -> list[dict]:
    """Good-quality NDVI values, oldest first: [{"date", "ndvi", "quality"}]."""
    series = []
    for day in sorted(ndvi_raw):
        rank, raw = qa_raw.get(day), ndvi_raw[day]
        if rank not in GOOD_RANKS or not isinstance(raw, (int, float)) or raw < -2000:
            continue
        series.append({"date": day, "ndvi": round(raw * SCALE, 3), "quality": "good" if rank == 0 else "marginal"})
    return series


def monthly_summary(series: list[dict]) -> list[dict]:
    """Per calendar month: typical NDVI (median), and the share of years that looked bare."""
    best: dict[tuple[int, int], float] = {}   # (year, month) -> highest good value
    values: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for p in series:
        y, m = int(p["date"][:4]), int(p["date"][5:7])
        values[m].append(p["ndvi"])
        best[(y, m)] = max(best.get((y, m), -1.0), p["ndvi"])
    out = []
    for m in range(1, 13):
        years = [v for (y, mm), v in best.items() if mm == m]
        bare = sum(1 for v in years if v < BARE_NDVI)
        out.append({
            "month": m,
            "typical_ndvi": round(statistics.median(values[m]), 3) if values[m] else None,
            "years_seen": len(years),
            "bare_years": bare,
            "bare_share": round(bare / len(years), 2) if years else None,
        })
    return out


def build_doc(series: list[dict], start: str, end: str, lat: float, lon: float, fetched_on: str) -> dict:
    if not series:
        raise SourceUnavailable("NASA MODIS has no good-quality values for this location and period")
    months = monthly_summary(series)
    return {
        "status": "ok",
        "source": SOURCE,
        "resolution_m": RESOLUTION_M,
        "product": "MOD13Q1 v061, 16-day composite",
        "period": f"{start[:4]}-{end[:4]}",
        "location": {"lat": lat, "lon": lon},
        "fetched_on": fetched_on,
        "bare_threshold": BARE_NDVI,
        "method": ("A month is bare in a year when its highest good-quality NDVI is below "
                   f"{BARE_NDVI}. Quality ranks 0 (good) and 1 (marginal) are kept."),
        "series": series,
        "monthly": months,
        "bare_months": [m["month"] for m in months if (m["bare_share"] or 0) >= 0.5],
        "licence": "NASA LP DAAC / ORNL DAAC data: free to use, please cite the MOD13Q1 product.",
    }


# ---------- fetching (used by scripts/build_ndvi.py) ----------

def modis_dates(first_year: int, last_year: int) -> list[dict]:
    """MOD13Q1 composites start every 16 days from day 1 of each year (23 a year), so the
    dates can be worked out here instead of asking the slow service for its date list."""
    out = []
    for year in range(first_year, last_year + 1):
        for doy in range(1, 366, 16):
            d = date(year, 1, 1) + timedelta(days=doy - 1)
            out.append({"modis_date": f"A{year}{doy:03d}", "calendar_date": d.isoformat()})
    return out


async def _get_with_retry(client, url, params, attempts=ATTEMPTS, wait=RETRY_WAIT_S, sleep=asyncio.sleep):
    """The service sometimes answers 502/503 or stalls; try again after a pause."""
    for attempt in range(attempts):
        try:
            return await get_json(client, url, params, timeout=REQUEST_TIMEOUT)
        except (httpx.TimeoutException, asyncio.TimeoutError, httpx.TransportError):
            if attempt == attempts - 1:
                raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 or attempt == attempts - 1:
                raise
        await sleep(wait * (attempt + 1))


def date_chunks(dates: list[dict], start: str, end: str) -> list[tuple[str, str]]:
    """(first modis_date, last modis_date) chunks of at most 10 dates within [start, end]."""
    inside = [d["modis_date"] for d in dates if start <= d["calendar_date"] <= end]
    return [(inside[i], inside[min(i + MAX_DATES, len(inside)) - 1]) for i in range(0, len(inside), MAX_DATES)]


def period_for(today: date, years: int = YEARS) -> tuple[str, str]:
    """The last `years` complete calendar years, as ISO dates."""
    return f"{today.year - years}-01-01", f"{today.year - 1}-12-31"


async def fetch(client, lat: float, lon: float, today: date | None = None, years: int = YEARS,
                progress=None, sleep=asyncio.sleep) -> dict:
    """Fetch and summarise NDVI for the last complete years. Slow (minutes). Raises on failure."""
    today = today or date.today()
    start, end = period_for(today, years)
    point = {"latitude": round(lat, 6), "longitude": round(lon, 6)}
    chunks = date_chunks(modis_dates(int(start[:4]), int(end[:4])), start, end)
    if not chunks:
        raise SourceUnavailable("NASA MODIS lists no dates for this location and period")

    gate = asyncio.Semaphore(CONCURRENT)

    async def one(band, first, last):
        async with gate:
            doc = await _get_with_retry(client, f"{BASE}/subset", {
                **point, "band": band, "startDate": first, "endDate": last,
                "kmAboveBelow": 0, "kmLeftRight": 0}, sleep=sleep)
            if progress:
                progress(band, first, last)
            return band, parse_subset(doc)

    results = await asyncio.gather(*(one(b, f, l) for b in (NDVI_BAND, QA_BAND) for f, l in chunks))
    ndvi_raw, qa_raw = {}, {}
    for band, values in results:
        (ndvi_raw if band == NDVI_BAND else qa_raw).update(values)
    return build_doc(combine(ndvi_raw, qa_raw), start, end, lat, lon, today.isoformat())
