"""Yearly climate measures ("indicators") computed from daily weather.

Each indicator turns one year of daily values into one number that a farmer recognises,
such as "days above 35 °C" or "longest run of days without rain". They cover the pressures
named in the challenge: shifting temperatures, changing rainfall, water shortage, extreme
weather. All functions here are pure (no network, no files), so they are easy to test.

Daily data comes in as {datetime.date: value}. Two helpers convert from the two sources:
- from_power({"YYYYMMDD": value})        NASA POWER daily API
- from_lists(["YYYY-MM-DD", ...], [...])  Open-Meteo Climate API

A year is used for an indicator only when at least 90% of its days have data (Req 17.3).
"""
from datetime import date, timedelta
import math
import statistics

FILL = -999  # NASA POWER "no data" marker
MIN_COVERAGE = 0.9

HOT_DAY_C = 35.0       # day counts as hot when the high is above this
WARM_NIGHT_C = 24.0    # night counts as warm when the low is above this
FROST_C = 0.0          # frost when the low is at or below this
DRY_DAY_MM = 1.0       # a day with less rain than this is a dry day
WET_DAY_MM = 1.0       # wet days (for the heavy-rain threshold) have at least this much rain
GROWING_MONTHS = (4, 5, 6, 7, 8, 9)  # April to September

# id -> (label, units). The order is the order shown to the farmer.
INDICATORS = {
    "hot_days": ("Days above 35 °C", "days/year"),
    "warm_nights": ("Nights above 24 °C", "nights/year"),
    "frost_days": ("Frost days (0 °C or below)", "days/year"),
    "last_spring_frost": ("Last spring frost", "day of year"),
    "first_fall_frost": ("First fall frost", "day of year"),
    "rain_total": ("Yearly rain", "mm/year"),
    "rain_growing": ("April–September rain", "mm"),
    "dry_spell": ("Longest dry spell", "days"),
    "heavy_rain_days": ("Heavy-rain days", "days/year"),
    "water_balance": ("Rain minus evaporation", "mm/year"),
    "soil_wetness": ("Growing-season root-zone wetness", "0–1"),
}


# ---------- converting source data ----------

def _valid(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v != FILL and not math.isnan(v)


def from_power(series: dict) -> dict[date, float]:
    """{"YYYYMMDD": value} -> {date: value}, dropping fill values and bad keys."""
    out = {}
    for key, v in (series or {}).items():
        if not _valid(v):
            continue
        try:
            out[date(int(key[:4]), int(key[4:6]), int(key[6:8]))] = float(v)
        except (ValueError, TypeError):
            continue
    return out


def from_lists(times: list, values: list) -> dict[date, float]:
    """Parallel lists of "YYYY-MM-DD" and values -> {date: value}, dropping missing values."""
    out = {}
    for t, v in zip(times or [], values or []):
        if not _valid(v):
            continue
        try:
            out[date.fromisoformat(str(t)[:10])] = float(v)
        except ValueError:
            continue
    return out


# ---------- grouping by year ----------

def days_in_year(year: int) -> int:
    return 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365


def by_year(daily: dict[date, float]) -> dict[int, dict[date, float]]:
    """Group daily values by year, keeping only years with at least 90% of their days."""
    years: dict[int, dict[date, float]] = {}
    for d, v in daily.items():
        years.setdefault(d.year, {})[d] = v
    return {y: days for y, days in years.items() if len(days) >= MIN_COVERAGE * days_in_year(y)}


def day_of_year(d: date) -> int:
    """Day of the year in a non-leap calendar, so dates compare across years (Feb 29 -> Feb 28)."""
    if d.month == 2 and d.day == 29:
        d = d.replace(day=28)
    return date(2001, d.month, d.day).timetuple().tm_yday


def doy_to_month_day(doy: int) -> str:
    """Day of year (non-leap) -> "MM-DD"."""
    return (date(2001, 1, 1) + timedelta(days=int(doy) - 1)).strftime("%m-%d")


# ---------- one-year measures ----------

def _longest_run(days: dict[date, float], is_dry) -> int:
    """Longest run of consecutive calendar days that are dry. A missing day breaks the run."""
    best = run = 0
    previous = None
    for d in sorted(days):
        if is_dry(days[d]) and previous is not None and d - previous == timedelta(days=1) and run:
            run += 1
        elif is_dry(days[d]):
            run = 1
        else:
            run = 0
        best = max(best, run)
        previous = d
    return best


def heavy_rain_threshold(rain: dict[date, float], start_year: int = 1981, end_year: int = 2010) -> float | None:
    """95th percentile of wet-day rain (>= 1 mm) in the base period, rounded to whole mm.

    Uses the years 1981-2010 when available; falls back to all years if fewer than 10 base
    years have data. Returns None if there are not enough wet days to say.
    """
    years = by_year(rain)
    base = [y for y in years if start_year <= y <= end_year]
    if len(base) < 10:
        base = list(years)
    wet = sorted(v for y in base for v in years[y].values() if v >= WET_DAY_MM)
    if len(wet) < 20:
        return None
    k = 0.95 * (len(wet) - 1)
    lo, hi = math.floor(k), math.ceil(k)
    value = wet[lo] + (wet[hi] - wet[lo]) * (k - lo)
    return float(round(value))


def yearly_indicators(tmin: dict, tmax: dict, rain: dict, evap: dict | None = None,
                      soil: dict | None = None, heavy_threshold: float | None = None) -> dict[str, dict[int, float]]:
    """Compute every indicator for every usable year. Returns {indicator_id: {year: value}}.

    Inputs are {date: value} maps. evap (mm/day) and soil (0-1 wetness) are optional because
    the climate models do not provide them. An indicator is left out entirely if its inputs
    are missing, and a year is left out of an indicator when its data is incomplete or the
    value is undefined (for example no frost at all that year means no frost date).
    """
    out: dict[str, dict[int, float]] = {k: {} for k in INDICATORS}
    lows, highs, rains = by_year(tmin), by_year(tmax), by_year(rain)

    for y, days in highs.items():
        out["hot_days"][y] = sum(1 for v in days.values() if v > HOT_DAY_C)

    for y, days in lows.items():
        out["warm_nights"][y] = sum(1 for v in days.values() if v > WARM_NIGHT_C)
        frosts = [d for d, v in days.items() if v <= FROST_C]
        out["frost_days"][y] = len(frosts)
        spring = [d for d in frosts if d.month < 7]
        fall = [d for d in frosts if d.month >= 7]
        if spring:
            out["last_spring_frost"][y] = day_of_year(max(spring))
        if fall:
            out["first_fall_frost"][y] = day_of_year(min(fall))

    if heavy_threshold is None:
        heavy_threshold = heavy_rain_threshold(rain)
    for y, days in rains.items():
        out["rain_total"][y] = round(sum(days.values()), 1)
        out["rain_growing"][y] = round(sum(v for d, v in days.items() if d.month in GROWING_MONTHS), 1)
        out["dry_spell"][y] = _longest_run(days, lambda v: v < DRY_DAY_MM)
        if heavy_threshold is not None:
            out["heavy_rain_days"][y] = sum(1 for v in days.values() if v > heavy_threshold)

    if evap:
        evaps = by_year(evap)
        for y in sorted(set(rains) & set(evaps)):
            shared = set(rains[y]) & set(evaps[y])
            if len(shared) >= MIN_COVERAGE * days_in_year(y):
                out["water_balance"][y] = round(sum(rains[y][d] - evaps[y][d] for d in shared), 1)

    if soil:
        for y, days in by_year(soil).items():
            season = [v for d, v in days.items() if d.month in GROWING_MONTHS]
            if season:
                out["soil_wetness"][y] = round(statistics.fmean(season), 3)

    return {k: v for k, v in out.items() if v}


# ---------- averages used as "today's" site facts ----------

def average(series: dict[int, float], years) -> float | None:
    """Mean of the given years that exist in the series, or None."""
    values = [series[y] for y in years if y in series]
    return round(statistics.fmean(values), 1) if values else None


def coefficient_of_variation(series: dict[int, float]) -> float | None:
    """Year-to-year variation as a percentage of the mean (needs at least 5 years)."""
    values = list(series.values())
    if len(values) < 5:
        return None
    mean = statistics.fmean(values)
    return round(statistics.stdev(values) / mean * 100, 1) if mean else None


def monthly_climate(tmax: dict[date, float], rain: dict[date, float], years) -> dict:
    """Average daily high (°C) and average rain (mm) for each month over the given years.

    Used for heat-stress months (average high above 35 °C) and the wettest month.
    Returns lists of 12 values (None for a month with no data).
    """
    years = set(years)
    highs = [[] for _ in range(12)]
    totals: dict[tuple[int, int], float] = {}
    for d, v in tmax.items():
        if d.year in years:
            highs[d.month - 1].append(v)
    for d, v in rain.items():
        if d.year in years:
            totals[(d.year, d.month)] = totals.get((d.year, d.month), 0.0) + v
    rain_by_month = [[t for (y, m), t in totals.items() if m == month] for month in range(1, 13)]
    return {
        "avg_high_c": [round(statistics.fmean(h), 1) if h else None for h in highs],
        "rain_mm": [round(statistics.fmean(r), 1) if r else None for r in rain_by_month],
    }
