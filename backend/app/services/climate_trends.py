"""How the climate at a field has changed since 1981, from NASA POWER daily data (no key).

One request fetches every day from 1 January 1981 to the end of the last complete year for
five variables (the probe on 2026-11-14 took about 1 second and returned 1.3 MB):

  T2M_MIN, T2M_MAX   daily low and high temperature, °C
  PRECTOTCORR        rain, mm/day
  EVLAND             evaporation from the land surface, mm/day
  GWETROOT           root-zone soil wetness, 0 (dry) to 1 (saturated)

From that it computes the yearly indicators, a trend for each, the averages of the last
10 years (the "today" site facts), monthly highs and rain for the calendar strip, and the
1991-2020 averages that the climate outlook adds its projected changes to.

Only the computed summary (a few KB) is cached, under a key that includes the last
complete year, so a new year's data is picked up automatically, at most once a year.

NASA POWER is about 50 km resolution: it describes the regional climate, not the field.
"""
from datetime import date

from app.cache import DiskCache
from app.rotation import indicators as ind
from app.rotation.trends import trend
from app.services.base import SourceUnavailable, get_json

SOURCE = "NASA POWER"
RESOLUTION_M = 50000
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = "T2M_MIN,T2M_MAX,PRECTOTCORR,GWETROOT,EVLAND"
FIRST_YEAR = 1981
RECENT_YEARS = 10           # "today" = the average of the last 10 complete years
BASELINE = (1991, 2020)     # the outlook's reference period


def last_complete_year(today: date | None = None) -> int:
    return (today or date.today()).year - 1


def cache_key(last_year: int) -> str:
    return f"climate_trends_{last_year}"


def summarize(power_json: dict, last_year: int) -> dict:
    """Turn a NASA POWER daily response into the trends summary. Raises SourceUnavailable."""
    try:
        p = power_json["properties"]["parameter"]
    except (KeyError, TypeError):
        raise SourceUnavailable("NASA POWER sent data we could not read")

    tmin, tmax = ind.from_power(p.get("T2M_MIN")), ind.from_power(p.get("T2M_MAX"))
    rain = ind.from_power(p.get("PRECTOTCORR"))
    evap, soil = ind.from_power(p.get("EVLAND")), ind.from_power(p.get("GWETROOT"))
    if not (ind.by_year(tmin) and ind.by_year(tmax) and ind.by_year(rain)):
        raise SourceUnavailable("NASA POWER has no daily climate data for this location")

    threshold = ind.heavy_rain_threshold(rain)
    yearly = ind.yearly_indicators(tmin, tmax, rain, evap or None, soil or None, threshold)
    all_years = sorted({y for series in yearly.values() for y in series})
    recent = [y for y in all_years if y > last_year - RECENT_YEARS]
    baseline = range(BASELINE[0], BASELINE[1] + 1)

    items = []
    for key, (label, units) in ind.INDICATORS.items():
        series = yearly.get(key)
        if not series:
            continue
        if key == "heavy_rain_days" and threshold is not None:
            label = f"{label} (over {threshold:g} mm)"
        items.append({
            "id": key,
            "label": label,
            "units": units,
            "yearly": [[y, series[y]] for y in sorted(series)],
            **trend(series),
            "recent_avg": ind.average(series, recent),
            "baseline_avg": ind.average(series, baseline),
        })

    monthly = ind.monthly_climate(tmax, rain, recent)
    return {
        "status": "ok",
        "source": SOURCE,
        "resolution_m": RESOLUTION_M,
        "period": f"{all_years[0]}-{all_years[-1]}",
        "recent_period": f"{recent[0]}-{recent[-1]}" if recent else None,
        "baseline_period": f"{BASELINE[0]}-{BASELINE[1]}",
        "heavy_rain_threshold_mm": threshold,
        "rain_cv_pct": ind.coefficient_of_variation(yearly.get("rain_total", {})),
        "monthly": {"period": f"{recent[0]}-{recent[-1]}" if recent else None, **monthly},
        "indicators": items,
    }


def is_valid_summary(doc: dict) -> bool:
    items = doc.get("indicators")
    return doc.get("status") == "ok" and isinstance(items, list) and bool(items) and all(
        isinstance(i, dict) and "id" in i and "yearly" in i for i in items)


async def fetch(client, lat: float, lon: float, cache: DiskCache, today: date | None = None) -> dict:
    """Return the trends summary for a location, from cache or live. Raises on failure."""
    last_year = last_complete_year(today)
    key = cache_key(last_year)
    cached = cache.read_doc(key, lat, lon, is_valid_summary)
    if cached is not None:
        return cached
    data = await get_json(client, URL, {
        "parameters": PARAMETERS, "community": "AG", "format": "JSON",
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "start": f"{FIRST_YEAR}0101", "end": f"{last_year}1231",
    })
    summary = summarize(data, last_year)
    cache.write_doc(key, lat, lon, summary)
    return dict(summary, live_or_cached="live")
