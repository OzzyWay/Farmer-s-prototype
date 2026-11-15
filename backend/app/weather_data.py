"""The National Weather Service forecast and alerts for one location, for GET /api/weather.

The forecast and the official alerts are fetched at the same time and fail on their own:
if one part fails, the other is still returned. Each successful part is kept in the disk
cache for one hour; failures are never cached. Farm alerts are worked out from the forecast
on every answer, so a change to a threshold takes effect without clearing the cache.
This function never raises for an upstream problem, so the route never returns a 500.
"""
import asyncio
import logging
import time

from app.cache import DiskCache
from app.services import nws
from app.services.base import describe_failure

log = logging.getLogger("farm_data")

CACHE_TTL_S = 3600  # one hour
NAME = "National Weather Service"


def _fresh(clock, key):
    """Shape and age check for a cached part (used by DiskCache.read_doc)."""
    def check(doc):
        age = clock() - float(doc["fetched_at"])
        return 0 <= age < CACHE_TTL_S and isinstance(doc.get(key), list)
    return check


async def _part(source, key, fetch, client, lat, lon, cache, clock):
    hit = cache.read_doc(source, lat, lon, _fresh(clock, key))
    if hit is not None and (key != "periods" or hit[key]):
        return hit[key], "cached"
    value = await fetch(client, lat, lon)
    cache.write_doc(source, lat, lon, {"fetched_at": clock(), key: value})
    return value, "live"


def _failed(exc) -> dict:
    log.warning("farm_data source=nws error=%s", type(exc).__name__)  # no URL, body or coordinates
    return {"status": "unavailable", "reason": describe_failure(NAME, exc)}


def _now() -> float:
    return time.time()  # looked up at call time, so tests can replace time.time


async def gather_weather(client, lat: float, lon: float, cache: DiskCache, clock=_now) -> dict:
    forecast_r, alerts_r = await asyncio.gather(
        _part("nws_forecast", "periods", nws.fetch_periods, client, lat, lon, cache, clock),
        _part("nws_alerts", "alerts", nws.fetch_official_alerts, client, lat, lon, cache, clock),
        return_exceptions=True,
    )

    if isinstance(forecast_r, nws.OutsideCoverage):
        # Outside the US: both parts are unavailable for the same reason (not cached).
        reason = describe_failure(NAME, forecast_r)
        forecast = {"status": "unavailable", "reason": reason}
        alerts = {"status": "unavailable", "reason": reason, "official": [], "farm": []}
    else:
        periods = None
        if isinstance(forecast_r, BaseException):
            forecast = _failed(forecast_r)
        elif isinstance(forecast_r, tuple) and isinstance(forecast_r[0], list):
            periods, how = forecast_r
            forecast = {"status": "ok", "periods": periods, "live_or_cached": how}
        else:
            forecast = {"status": "unavailable", "reason": f"{NAME} sent data we could not read"}

        farm = nws.farm_alerts(periods) if periods else []
        if isinstance(alerts_r, BaseException):
            alerts = dict(_failed(alerts_r), official=[], farm=farm)
        elif isinstance(alerts_r, tuple) and isinstance(alerts_r[0], list):
            alerts = {"status": "ok", "official": alerts_r[0], "farm": farm, "live_or_cached": alerts_r[1]}
        else:
            alerts = {"status": "unavailable", "reason": f"{NAME} sent data we could not read",
                      "official": [], "farm": farm}

    return {
        "location": {"lat": lat, "lon": lon},
        "source": NAME,
        "page_url": nws.forecast_page_url(lat, lon),
        "forecast": forecast,
        "alerts": alerts,
    }
