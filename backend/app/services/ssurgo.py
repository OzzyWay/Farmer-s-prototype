"""USDA SSURGO soil survey, through the NRCS Soil Data Access web service (no key needed).

We ask for the map unit under the point, take its dominant component (the soil that
covers the largest share of the map unit) and read its surface layer.

IMPORTANT: SSURGO values are averages for a mapped soil area, not measurements of
one field. Every record is labelled "map-unit average".
"""
import logging

from app.cache import DiskCache
from app.records import make_record
from app.services.base import SourceUnavailable, post_json

log = logging.getLogger("farm_data")

SOURCE = "USDA SSURGO (map-unit average)"
CACHE_KEY = "ssurgo"
# Soil survey polygons are not a grid. 250 m is a nominal size for a small map unit,
# used only so the panel can show how coarse the data is.
RESOLUTION_M = 250
DATE_LABEL = "current survey"
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
NO_DATA_REASON = "no soil survey data for this location"


def build_query(lat: float, lon: float) -> str:
    """SQL for the dominant component's surface layer. lat/lon are floats, so they are safe to embed."""
    lat, lon = float(lat), float(lon)
    return f"""
        SELECT TOP 1 mu.muname, c.drainagecl, c.hydgrp, c.slope_l, c.slope_h,
               h.om_r, h.awc_r, h.kffact,
               (SELECT TOP 1 t.texdesc FROM chtexturegrp t
                 WHERE t.chkey = h.chkey AND t.rvindicator = 'Yes') AS texdesc
        FROM mapunit mu
        JOIN component c ON c.mukey = mu.mukey
        JOIN chorizon h ON h.cokey = c.cokey
        WHERE mu.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon:.6f} {lat:.6f})'))
        ORDER BY c.comppct_r DESC, h.hzdept_r ASC"""


def _num(v):
    """Return a float, or None for missing/blank/non-numeric values."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def _fmt(x: float) -> str:
    return f"{x:g}"


def parse_response(data) -> list:
    """Turn the Soil Data Access JSON into Feature_Records. Raises SourceUnavailable if there is no soil."""
    try:
        table = data.get("Table") if isinstance(data, dict) else None
        if table is None:
            # SDA returns an object without "Table" when the query matches nothing.
            if isinstance(data, dict):
                raise SourceUnavailable(NO_DATA_REASON)
            raise ValueError("unexpected response")
        if not isinstance(table, list) or not all(isinstance(r, list) for r in table):
            raise ValueError("unexpected table shape")
        if len(table) < 2:
            raise SourceUnavailable(NO_DATA_REASON)
        row = dict(zip(table[0], table[1]))
    except SourceUnavailable:
        raise
    except (TypeError, ValueError, AttributeError):
        raise SourceUnavailable("USDA SSURGO sent data we could not read")

    def rec(variable, value, units=""):
        return make_record(variable, SOURCE, RESOLUTION_M, DATE_LABEL, value, units)

    records = []
    name = _text(row.get("muname"))
    if name:
        records.append(rec("soil_map_unit_name", name))
    om = _num(row.get("om_r"))
    if om is not None:
        records.append(rec("soil_organic_matter", om, "%"))
    texture = _text(row.get("texdesc"))
    if texture:
        records.append(rec("soil_texture", texture))
    drainage = _text(row.get("drainagecl"))
    if drainage:
        records.append(rec("soil_drainage_class", drainage))
    group = _text(row.get("hydgrp"))
    if group:
        records.append(rec("soil_hydrologic_group", group))
    awc = _num(row.get("awc_r"))
    if awc is not None:
        records.append(rec("soil_available_water_capacity", awc, "in/in"))
    k = _num(row.get("kffact"))
    if k is not None:
        records.append(rec("soil_erodibility_k", k))
    lo, hi = _num(row.get("slope_l")), _num(row.get("slope_h"))
    if lo is not None and hi is not None:
        records.append(rec("soil_slope_range", f"{_fmt(lo)} to {_fmt(hi)}", "%"))

    if not records:
        raise SourceUnavailable(NO_DATA_REASON)
    return records


async def fetch(client, lat: float, lon: float, cache: DiskCache) -> list:
    """Return Feature_Records for this location, from cache or live. Raises on failure."""
    cached = cache.read(CACHE_KEY, lat, lon)
    if cached is not None:
        return cached
    data = await post_json(client, SDA_URL, {"query": build_query(lat, lon), "format": "JSON+COLUMNNAME"})
    records = parse_response(data)
    cache.write(CACHE_KEY, lat, lon, records)
    return records
