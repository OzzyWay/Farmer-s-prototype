"""Where the MODIS NDVI result for a location comes from.

Only demo farms have one: config/ndvi/<farm_id>.json, prepared by scripts/build_ndvi.py,
used when the location is inside that farm's 1 km field box. Anywhere else the answer is
"not prepared" with the reason, because fetching it live takes several minutes.
"""
import json
from pathlib import Path

from app.outlook_store import DEMO_FARMS_FILE, _inside_box

ROOT = Path(__file__).resolve().parents[2]
NDVI_DIR = ROOT / "config" / "ndvi"
NOT_PREPARED = ("satellite greenness is prepared in advance for the demo farms only, because the NASA "
                "MODIS service takes several minutes per location")


def get(lat: float, lon: float, directory: Path = NDVI_DIR, farms_file: Path = DEMO_FARMS_FILE) -> dict:
    """The prepared NDVI document, or {"status": "not_prepared", "reason"}. Never raises."""
    try:
        farms = json.loads(Path(farms_file).read_text(encoding="utf-8")).get("farms", [])
    except (OSError, ValueError):
        farms = []
    for farm in farms:
        if not _inside_box(lat, lon, farm["lat"], farm["lon"]):
            continue
        try:
            doc = json.loads((Path(directory) / f"{farm['id']}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        if doc.get("status") == "ok" and doc.get("monthly"):
            return dict(doc, origin="precomputed")
        return {"status": "not_prepared", "demo_farm": True,
                "reason": "satellite greenness has not been prepared yet for this demo farm"}
    return {"status": "not_prepared", "demo_farm": False, "reason": NOT_PREPARED}
