"""Gather all farm facts for one location from the three sources at the same time.

Each source either gives a list of Feature_Records or an Unavailable_Entry with a short
reason. One source failing never affects the others, and this function never raises,
so the endpoint never turns an upstream problem into a server error.
"""
import asyncio
import logging

from app.cache import DiskCache
from app.records import ok_result, unavailable_result
from app.services import cdl, nasa_power, ssurgo
from app.services.base import describe_failure

log = logging.getLogger("farm_data")

# Safety net on top of the 10 s limit per upstream request. A service makes its own
# requests in parallel, so it should finish well inside this.
SERVICE_TIMEOUT = 15.0

# key in the response -> (service module, display name for messages)
SOURCES = {
    "nasa_power": (nasa_power, "NASA POWER"),
    "ssurgo": (ssurgo, "USDA SSURGO"),
    "cdl": (cdl, "USDA NASS CDL"),
}


async def _run(service, client, lat, lon, cache):
    return await asyncio.wait_for(service.fetch(client, lat, lon, cache), SERVICE_TIMEOUT)


async def gather_farm_data(client, lat: float, lon: float, cache: DiskCache) -> dict:
    """Return {"location": {...}, "sources": {key: ok_result | unavailable_result}}."""
    keys = list(SOURCES)
    results = await asyncio.gather(
        *(_run(SOURCES[k][0], client, lat, lon, cache) for k in keys),
        return_exceptions=True,  # one failure must not cancel the others
    )
    sources = {}
    for key, result in zip(keys, results):
        name = SOURCES[key][1]
        if isinstance(result, BaseException):
            # Log only the source and the kind of error: no URLs, bodies or secrets.
            log.warning("farm_data source=%s error=%s", key, type(result).__name__)
            sources[key] = unavailable_result(name, describe_failure(name, result))
        elif isinstance(result, list):
            sources[key] = ok_result(result)
        else:
            log.warning("farm_data source=%s error=UnexpectedResult", key)
            sources[key] = unavailable_result(name, f"{name} sent data we could not read")
    return {"location": {"lat": lat, "lon": lon}, "sources": sources}
