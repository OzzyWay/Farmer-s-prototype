"""Load and check the crop table in config/crops.json.

Every crop must have every attribute the rules and scores use, with allowed values, and at
least one source with a title and a web link. If anything is wrong, loading stops with a
message that names the crop and the field, so a bad edit is caught when the server starts
instead of quietly changing the advice (Req 5.5).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CROPS_FILE = ROOT / "config" / "crops.json"

LEVEL = ("low", "medium", "high")
ALLOWED = {
    "category": (
        "perennial_forage", "native_perennial", "summer_forage", "cool_forage",
        "legume_cover", "summer_legume_cover", "cereal_cover", "row_crop",
    ),
    "season": ("warm", "cool", "perennial"),
    "water_need": LEVEL,
    "drought_tolerance": LEVEL,
    "heat_tolerance": LEVEL,
    "frost_tolerance": LEVEL,
    "wet_soil_tolerance": LEVEL,
    "residue": LEVEL,
    "erosion_protection": LEVEL,
    "root_depth": ("shallow", "medium", "deep"),
    "forage_value": ("none", "low", "medium", "high"),
    "income": ("none", "low", "medium", "high"),
}
MONTH_FIELDS = ("plant_months", "growing_months", "in_ground_months")
OTHER_REQUIRED = {
    "id": str, "name": str, "annual": bool, "nitrogen_fixing": bool, "pest_families": list,
    "field_passes_per_year": int, "limits": dict, "soil_note": str, "risks": list, "sources": list,
}


class CropTableError(ValueError):
    """The crop table has a problem. The message names the crop and the field."""


def _check_crop(crop: dict, index: int) -> None:
    label = crop.get("id") or f"crop #{index + 1}"

    def fail(field: str, problem: str):
        raise CropTableError(f"config/crops.json: crop '{label}', field '{field}': {problem}")

    for field, allowed in ALLOWED.items():
        if field not in crop:
            fail(field, "missing")
        if crop[field] not in allowed:
            fail(field, f"'{crop[field]}' is not one of {', '.join(allowed)}")
    for field, kind in OTHER_REQUIRED.items():
        if field not in crop:
            fail(field, "missing")
        if not isinstance(crop[field], kind) or (kind is int and isinstance(crop[field], bool)):
            fail(field, f"must be a {kind.__name__}")
    for field in MONTH_FIELDS:
        months = crop.get(field)
        if not isinstance(months, list) or not months:
            fail(field, "missing or empty")
        if any(not isinstance(m, int) or isinstance(m, bool) or not 1 <= m <= 12 for m in months):
            fail(field, "months must be whole numbers from 1 to 12")
    if not set(crop["growing_months"]) <= set(crop["in_ground_months"]):
        fail("growing_months", "must be inside in_ground_months")
    if not crop["pest_families"] or not all(isinstance(p, str) and p for p in crop["pest_families"]):
        fail("pest_families", "needs at least one family name")
    rain = crop["limits"].get("min_rain_mm_rainfed")
    if rain is not None and (not isinstance(rain, (int, float)) or isinstance(rain, bool) or rain < 0):
        fail("limits.min_rain_mm_rainfed", "must be a positive number or null")
    if not crop["sources"]:
        fail("sources", "needs at least one source")
    for i, src in enumerate(crop["sources"]):
        if not isinstance(src, dict) or not str(src.get("title", "")).strip():
            fail(f"sources[{i}].title", "missing")
        url = str(src.get("url", ""))
        if not url.startswith(("https://", "http://")):
            fail(f"sources[{i}].url", "must be a web link starting with http:// or https://")


def validate(data: dict) -> dict[str, dict]:
    """Check the whole table and return the crops keyed by id. Raises CropTableError."""
    crops = data.get("crops") if isinstance(data, dict) else None
    if not isinstance(crops, list) or not crops:
        raise CropTableError("config/crops.json: needs a non-empty 'crops' list")
    by_id = {}
    for i, crop in enumerate(crops):
        if not isinstance(crop, dict):
            raise CropTableError(f"config/crops.json: crop #{i + 1} must be an object")
        _check_crop(crop, i)
        if crop["id"] in by_id:
            raise CropTableError(f"config/crops.json: crop id '{crop['id']}' is used twice")
        by_id[crop["id"]] = crop
    return by_id


def load(path: Path | str = CROPS_FILE) -> dict[str, dict]:
    """Read and validate the crop table. Raises CropTableError with a plain message."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CropTableError(f"crop table not found at {path}")
    except ValueError as e:
        raise CropTableError(f"config/crops.json is not valid JSON: {e}")
    return validate(data)
