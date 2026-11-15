"""All soil layers under a point, from USDA SSURGO through Soil Data Access (no key needed).

The farm-data panel only shows the surface layer. The rotation explorer needs the whole
profile to draw the 3D soil block and to judge drainage and flooding, so this asks for:

- every layer (horizon) of the dominant soil component, top to bottom, with depth,
  texture, organic matter, clay, sand and available water capacity;
- how often the component floods or ponds (the most frequent class across the months).

IMPORTANT: SSURGO values are averages for a mapped soil area, not measurements of one field.
"""
from app.cache import DiskCache
from app.services.base import SourceUnavailable, post_json

SOURCE = "USDA SSURGO (map-unit average)"
CACHE_KEY = "soil_profile"
RESOLUTION_M = 250  # nominal map-unit size, same label as the farm-data soil facts
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
NO_DATA_REASON = "no soil survey data for this location"

# SSURGO frequency classes, least to most often. Used to rank months and in the rules.
FREQUENCY_ORDER = ("none", "very rare", "rare", "occasional", "frequent", "very frequent")


def _frequency_rank_sql(column: str) -> str:
    """SQL CASE that ranks a SSURGO frequency class so the most frequent month sorts first."""
    cases = " ".join(f"WHEN '{name}' THEN {i}" for i, name in enumerate(FREQUENCY_ORDER, start=1))
    return f"CASE LOWER({column}) {cases} ELSE 0 END"


def build_query(lat: float, lon: float) -> str:
    """SQL for every layer of the dominant component at a point.

    lat/lon are converted with float() so only numbers can reach the query text.
    """
    lat, lon = float(lat), float(lon)
    point = f"point({lon:.6f} {lat:.6f})"
    return f"""
        SELECT mu.muname, c.compname, c.comppct_r,
               h.hzname, h.hzdept_r, h.hzdepb_r, h.om_r, h.claytotal_r, h.sandtotal_r, h.awc_r,
               (SELECT TOP 1 t.texdesc FROM chtexturegrp t
                 WHERE t.chkey = h.chkey AND t.rvindicator = 'Yes') AS texdesc,
               (SELECT TOP 1 m.flodfreqcl FROM comonth m WHERE m.cokey = c.cokey
                 ORDER BY {_frequency_rank_sql('m.flodfreqcl')} DESC) AS flodfreqcl,
               (SELECT TOP 1 m.pondfreqcl FROM comonth m WHERE m.cokey = c.cokey
                 ORDER BY {_frequency_rank_sql('m.pondfreqcl')} DESC) AS pondfreqcl
        FROM mapunit mu
        JOIN component c ON c.mukey = mu.mukey
        JOIN chorizon h ON h.cokey = c.cokey
        WHERE c.cokey = (
            SELECT TOP 1 c2.cokey FROM component c2
            WHERE c2.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{point}'))
            ORDER BY c2.comppct_r DESC)
        ORDER BY h.hzdept_r ASC"""


def texture_group(texture: str | None) -> str | None:
    """Group a USDA texture name into one of the soil block colours.

    Examples: "Fine sandy loam" -> "sandy loam", "Silty clay loam" -> "clay loam",
    "Silty clay" -> "clay", "Loamy fine sand" -> "sand", "Unweathered bedrock" -> "bedrock".
    """
    if not texture:
        return None
    t = texture.lower()
    if "bedrock" in t:
        return "bedrock"
    if "muck" in t or "peat" in t:
        return "organic"
    if "clay loam" in t:
        return "clay loam"
    if "clay" in t:
        return "clay"
    if "loamy sand" in t or t.split()[-1] == "sand" or t.endswith(" sand"):
        return "sand"
    if "sandy loam" in t:
        return "sandy loam"
    if "silt" in t:
        return "silt"
    if "loam" in t:
        return "loam"
    return None


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def _frequency(v):
    text = _text(v)
    if text is None:
        return None
    text = text.lower()
    return text if text in FREQUENCY_ORDER else None


def parse_response(data) -> dict:
    """Turn the Soil Data Access JSON into a soil profile. Raises SourceUnavailable when empty."""
    if not isinstance(data, dict):
        raise SourceUnavailable("USDA SSURGO sent data we could not read")
    table = data.get("Table")
    if table is None:
        raise SourceUnavailable(NO_DATA_REASON)  # SDA returns {} when nothing matches
    if not isinstance(table, list) or not all(isinstance(r, list) for r in table):
        raise SourceUnavailable("USDA SSURGO sent data we could not read")
    if len(table) < 2:
        raise SourceUnavailable(NO_DATA_REASON)
    header, rows = table[0], [dict(zip(table[0], r)) for r in table[1:]]
    if "hzdept_r" not in header:
        raise SourceUnavailable("USDA SSURGO sent data we could not read")

    layers, skipped = [], 0
    for row in rows:
        top, bottom = _num(row.get("hzdept_r")), _num(row.get("hzdepb_r"))
        if top is None or bottom is None or bottom <= top:
            skipped += 1  # a layer without a depth range cannot be placed in the profile
            continue
        layer = {"top_cm": top, "bottom_cm": bottom}
        name = _text(row.get("hzname"))
        if name:
            layer["name"] = name
        texture = _text(row.get("texdesc"))
        if texture:
            layer["texture"] = texture
            group = texture_group(texture)
            if group:
                layer["texture_group"] = group
        for key, col in (("om_pct", "om_r"), ("clay_pct", "claytotal_r"), ("sand_pct", "sandtotal_r"), ("awc", "awc_r")):
            value = _num(row.get(col))
            if value is not None:
                layer[key] = value
        layers.append(layer)
    if not layers:
        raise SourceUnavailable(NO_DATA_REASON)
    layers.sort(key=lambda layer: layer["top_cm"])

    first = rows[0]
    profile = {
        "status": "ok",
        "map_unit": _text(first.get("muname")),
        "component": _text(first.get("compname")),
        "component_pct": _num(first.get("comppct_r")),
        "flooding": _frequency(first.get("flodfreqcl")),
        "ponding": _frequency(first.get("pondfreqcl")),
        "layers": layers,
        "skipped_layers": skipped,
        "source": SOURCE,
        "resolution_m": RESOLUTION_M,
    }
    return {k: v for k, v in profile.items() if v is not None}


def is_valid_profile(doc: dict) -> bool:
    """Shape check for a cached profile."""
    layers = doc.get("layers")
    return (
        doc.get("status") == "ok"
        and isinstance(layers, list)
        and bool(layers)
        and all(isinstance(layer, dict) and "top_cm" in layer and "bottom_cm" in layer for layer in layers)
    )


async def fetch(client, lat: float, lon: float, cache: DiskCache) -> dict:
    """Return the soil profile, from cache or live. Raises on failure (never caches one)."""
    cached = cache.read_doc(CACHE_KEY, lat, lon, is_valid_profile)
    if cached is not None:
        return cached
    data = await post_json(client, SDA_URL, {"query": build_query(lat, lon), "format": "JSON+COLUMNNAME"})
    profile = parse_response(data)
    cache.write_doc(CACHE_KEY, lat, lon, profile)
    return dict(profile, live_or_cached="live")
