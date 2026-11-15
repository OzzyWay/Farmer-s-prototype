"""NASA POWER: regional climate normals (no key needed).

Two upstream calls, made at the same time:
1. Climatology: long-term monthly averages of temperature, rain and sunshine.
2. Daily data for the last 10 full years: used to compute average daily lows and
   highs per month, frost days, typical last/first frost dates, and hot days.
   (The climatology call only gives all-time monthly extremes for min/max, which
   would mislead a farmer, so we average the daily values ourselves.)

NASA POWER is about 50 km resolution. It describes the region, not the field.
"""
import asyncio
import logging
import statistics
from datetime import date, timedelta

from app.cache import DiskCache
from app.records import make_record
from app.services.base import SourceUnavailable, get_json

log = logging.getLogger("farm_data")

SOURCE = "NASA POWER"
CACHE_KEY = "nasa_power"
RESOLUTION_M = 50000
BASE = "https://power.larc.nasa.gov/api/temporal"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DAYS_IN_MONTH = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
FILL = -999  # NASA's "no data" marker
HEAT_THRESHOLD_C = 35.0
FROST_THRESHOLD_C = 0.0
MIN_YEAR_COVERAGE = 0.9  # a year needs at least 90% of its days to be used


# ---------- pure helpers (tested directly) ----------

def _valid(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v != FILL


def _by_year(series: dict) -> dict:
    """Group {"YYYYMMDD": value} into {year: {date: value}}, dropping fill values and bad keys."""
    years: dict[int, dict] = {}
    for key, v in series.items():
        if not _valid(v):
            continue
        try:
            d = date(int(key[:4]), int(key[4:6]), int(key[6:8]))
        except (ValueError, TypeError):
            continue
        years.setdefault(d.year, {})[d] = v
    return years


def _usable_years(series: dict) -> dict:
    """Keep only years with at least 90% of their days present."""
    out = {}
    for year, days in _by_year(series).items():
        total = 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365
        if len(days) >= MIN_YEAR_COVERAGE * total:
            out[year] = days
    return out


def _doy(d: date) -> int:
    """Day of year in a non-leap reference year (Feb 29 counts as Feb 28)."""
    if d.month == 2 and d.day == 29:
        d = d.replace(day=28)
    return date(2001, d.month, d.day).timetuple().tm_yday


def _doy_to_month_day(doy: int) -> str:
    return (date(2001, 1, 1) + timedelta(days=doy - 1)).strftime("%m-%d")


def monthly_means(series: dict) -> list | None:
    """Average daily value for each month (12 numbers), or None if any month has no data."""
    sums = [[0.0, 0] for _ in range(12)]
    for days in _usable_years(series).values():
        for d, v in days.items():
            sums[d.month - 1][0] += v
            sums[d.month - 1][1] += 1
    if any(n == 0 for _, n in sums):
        return None
    return [round(s / n, 1) for s, n in sums]


def estimate_frost_heat(daily_min: dict, daily_max: dict) -> dict:
    """Frost and heat estimates from daily series ({"YYYYMMDD": degC}).

    Returns a dict with frost_days, last_spring_frost, first_fall_frost, heat_days and
    period. Any value that cannot be estimated is None.
    """
    out = {"frost_days": None, "last_spring_frost": None, "first_fall_frost": None,
           "heat_days": None, "period": None}

    min_years = _usable_years(daily_min)
    if min_years:
        frost_counts, springs, falls = [], [], []
        for days in min_years.values():
            frosts = [d for d, v in days.items() if v <= FROST_THRESHOLD_C]
            frost_counts.append(len(frosts))
            spring = [d for d in frosts if d.month < 7]
            fall = [d for d in frosts if d.month >= 7]
            if spring:
                springs.append(_doy(max(spring)))   # last frost before 1 July
            if fall:
                falls.append(_doy(min(fall)))       # first frost from 1 July on
        out["frost_days"] = round(sum(frost_counts) / len(frost_counts), 1)
        if springs:
            out["last_spring_frost"] = _doy_to_month_day(int(round(statistics.median(springs))))
        if falls:
            out["first_fall_frost"] = _doy_to_month_day(int(round(statistics.median(falls))))
        out["period"] = f"{min(min_years)}-{max(min_years)}"

    max_years = _usable_years(daily_max)
    if max_years:
        counts = [sum(1 for v in days.values() if v > HEAT_THRESHOLD_C) for days in max_years.values()]
        out["heat_days"] = round(sum(counts) / len(counts), 1)
        out["period"] = out["period"] or f"{min(max_years)}-{max(max_years)}"
    return out


def _twelve(param: dict | None) -> list | None:
    """Pull JAN..DEC from a climatology parameter, or None if any month is missing."""
    if not isinstance(param, dict):
        return None
    vals = [param.get(m) for m in MONTHS]
    return vals if all(_valid(v) for v in vals) else None


# ---------- record building ----------

def _monthly_records(variable, values, units):
    return [make_record(variable, SOURCE, RESOLUTION_M, f"{i + 1:02d}", v, units) for i, v in enumerate(values)]


def build_records(climatology: dict, daily: dict | None) -> list:
    """Turn the two upstream responses into Feature_Records. `daily` may be None."""
    try:
        params = climatology["properties"]["parameter"]
    except (KeyError, TypeError):
        raise SourceUnavailable("NASA POWER sent data we could not read")

    t_mean = _twelve(params.get("T2M"))
    rain_per_day = _twelve(params.get("PRECTOTCORR"))
    if t_mean is None or rain_per_day is None:
        raise SourceUnavailable("NASA POWER has no climate data for this location")

    records = _monthly_records("temperature_mean", [round(v, 1) for v in t_mean], "°C")

    daily_params = {}
    if daily:
        try:
            daily_params = daily["properties"]["parameter"]
        except (KeyError, TypeError):
            daily_params = {}
    daily_min = daily_params.get("T2M_MIN") or {}
    daily_max = daily_params.get("T2M_MAX") or {}

    # Average daily low and high per month (omitted if the daily data is unusable).
    low = monthly_means(daily_min)
    high = monthly_means(daily_max)
    if low:
        records += _monthly_records("temperature_min", low, "°C")
    if high:
        records += _monthly_records("temperature_max", high, "°C")

    # Rain: NASA gives mm per day; convert to mm per month.
    rain = [round(v * DAYS_IN_MONTH[i], 1) for i, v in enumerate(rain_per_day)]
    records += _monthly_records("precipitation", rain, "mm")

    # Sunshine, only when present. NASA reports MJ/m2/day; convert to kWh/m2/day (divide by 3.6).
    sun = _twelve(params.get("ALLSKY_SFC_SW_DWN"))
    if sun:
        unit_text = ((climatology.get("parameters") or {}).get("ALLSKY_SFC_SW_DWN") or {}).get("units", "MJ")
        factor = 1 / 3.6 if "MJ" in unit_text else 1.0
        records += _monthly_records("solar_radiation", [round(v * factor, 2) for v in sun], "kWh/m²/day")

    est = estimate_frost_heat(daily_min, daily_max)
    period = est["period"]
    for variable, key, units in (
        ("frost_days_per_year", "frost_days", "days/year"),
        ("last_spring_frost", "last_spring_frost", "month-day"),
        ("first_fall_frost", "first_fall_frost", "month-day"),
        ("heat_days_per_year", "heat_days", "days/year"),
    ):
        if est[key] is not None:
            records.append(make_record(variable, SOURCE, RESOLUTION_M, period, est[key], units))
    return records


# ---------- the service ----------

async def fetch(client, lat: float, lon: float, cache: DiskCache, today: date | None = None) -> list:
    """Return Feature_Records for this location, from cache or live. Raises on failure."""
    cached = cache.read(CACHE_KEY, lat, lon)
    if cached is not None:
        return cached

    today = today or date.today()
    last_year = today.year - 1
    common = {"community": "AG", "latitude": round(lat, 4), "longitude": round(lon, 4), "format": "JSON"}

    clim_task = get_json(client, f"{BASE}/climatology/point", {
        **common, "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN"})
    daily_task = get_json(client, f"{BASE}/daily/point", {
        **common, "parameters": "T2M_MIN,T2M_MAX",
        "start": f"{last_year - 9}0101", "end": f"{last_year}1231"})
    clim_result, daily_result = await asyncio.gather(clim_task, daily_task, return_exceptions=True)

    if isinstance(clim_result, BaseException):
        raise clim_result  # the monthly data is required
    daily = None
    if isinstance(daily_result, BaseException):
        # Keep going without frost, heat and min/max values.
        log.warning("farm_data source=%s part=daily error=%s", SOURCE, type(daily_result).__name__)
    else:
        daily = daily_result

    records = build_records(clim_result, daily)
    if any(r["variable"] == "temperature_min" for r in records):
        cache.write(CACHE_KEY, lat, lon, records)  # do not cache a reduced (daily-less) result
    return records
