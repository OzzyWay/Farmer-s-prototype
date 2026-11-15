"""Shared inputs for the rotation engine tests: the Webberwood demo farm, built from saved data.

- Climate trends: the real NASA POWER daily fixture (1981-2025).
- Soil profile: the real Soil Data Access fixture (Tinn clay, occasionally flooded).
- Surface soil facts: the values the live SSURGO service returned for this point on 2026-11-14
  (Tinn clay, 2.5% organic matter, group D, moderately well drained, AWC 0.18, K 0.24, slope 0-1%).
- Crop history: Grass/Pasture in 7 of 8 years (2023 Evergreen Forest), as the live CDL returned.
- Outlook: the precomputed config/outlooks/webberwood.json.
"""
import json
from functools import lru_cache
from pathlib import Path

from app.records import make_record
from app.rotation.crops import load
from app.rotation.current import infer
from app.rotation.site_facts import build_outlook_facts, build_today
from app.services import climate_trends, openmeteo, soil_profile

FX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
SSURGO = "USDA SSURGO (map-unit average)"


def ssurgo_records(hydro="D", drainage="Moderately well drained", om=2.5, k=0.24, slope="0 to 1", texture="Clay"):
    rec = lambda v, val, u="": make_record(v, SSURGO, 250, "current survey", val, u)  # noqa: E731
    out = [rec("soil_map_unit_name", "Tinn clay, 0 to 1 percent slopes, occasionally flooded"),
           rec("soil_texture", texture), rec("soil_drainage_class", drainage), rec("soil_hydrologic_group", hydro),
           rec("soil_available_water_capacity", 0.18, "in/in"), rec("soil_slope_range", slope, "%")]
    if om is not None:
        out.append(rec("soil_organic_matter", om, "%"))
    if k is not None:
        out.append(rec("soil_erodibility_k", k))
    return out


def cdl_records(*categories, start=2018):
    return [make_record("crop_type", "USDA NASS CDL", 30, str(start + i), c, "") for i, c in enumerate(categories)]


WEBBERWOOD_CDL = ("Grass/Pasture",) * 5 + ("Evergreen Forest", "Grass/Pasture", "Grass/Pasture")


@lru_cache(maxsize=1)
def crops():
    return load()


@lru_cache(maxsize=1)
def trends():
    return climate_trends.summarize(json.loads((FX / "power_daily_webberwood.json").read_text(encoding="utf-8")), 2025)


@lru_cache(maxsize=1)
def profile():
    return soil_profile.parse_response(json.loads((FX / "soil_profile_webberwood.json").read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def outlook_doc():
    doc = json.loads((ROOT / "config" / "outlooks" / "webberwood.json").read_text(encoding="utf-8"))
    return openmeteo.apply_to_baseline(doc, trends())


def farm_sources(ssurgo=None, cdl=None, power_ok=True):
    return {
        "nasa_power": {"status": "ok", "records": []} if power_ok else {"status": "unavailable", "source": "NASA POWER", "reason": "x"},
        "ssurgo": {"status": "ok", "records": ssurgo if ssurgo is not None else ssurgo_records()},
        "cdl": {"status": "ok", "records": cdl if cdl is not None else cdl_records(*WEBBERWOOD_CDL)},
    }


def webberwood(with_outlook=True):
    """(today, outlook_facts, current, outlook_doc) for the demo farm."""
    sources = farm_sources()
    today = build_today(sources, profile(), trends())
    doc = outlook_doc() if with_outlook else None
    outlook = build_outlook_facts(today, doc, trends()) if with_outlook else None
    current = infer(sources["cdl"]["records"], crops())
    return today, outlook, current, doc
