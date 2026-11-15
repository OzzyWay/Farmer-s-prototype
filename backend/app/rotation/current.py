"""What the field grows now, from the USDA Cropland Data Layer (CDL) history (Req 6).

The CDL labels each 30 m square every year from satellite images. This module reads those
labels and describes the current rotation in the crop table's terms:

- Continuous: one land cover in at least 6 of the years (or in every year when fewer than
  6 years are available), for example "Grass/Pasture in 7 of 8 years".
- Alternating: two or three crops that each appear at least twice, in the order they last
  occurred, for example "corn then soybean".
- Unknown: no history, or more than half the years are not farmland (forest, towns, water).
  The farmer then picks the current crop from the crop table.

The farmer's own choice always wins over the CDL guess.
The CDL can be wrong for a single square; the evidence line lets the farmer judge.
"""
from collections import Counter

# CDL category name -> crop table ids. A double crop maps to two crops in one year.
CDL_TO_CROPS = {
    "Corn": ["corn"], "Sweet Corn": ["corn"], "Pop or Orn Corn": ["corn"],
    "Cotton": ["cotton"],
    "Sorghum": ["grain_sorghum"],
    "Soybeans": ["soybean"],
    "Winter Wheat": ["winter_wheat_grain"],
    "Oats": ["forage_oats"],
    "Grass/Pasture": ["bermudagrass"], "Grassland/Pasture": ["bermudagrass"],
    "Other Hay/Non Alfalfa": ["bermudagrass"],
    "Switchgrass": ["native_grass_mix"],
    "Dbl Crop WinWht/Soybeans": ["winter_wheat_grain", "soybean"],
    "Dbl Crop WinWht/Corn": ["winter_wheat_grain", "corn"],
    "Dbl Crop WinWht/Sorghum": ["winter_wheat_grain", "grain_sorghum"],
    "Dbl Crop WinWht/Cotton": ["winter_wheat_grain", "cotton"],
    "Dbl Crop Oats/Corn": ["forage_oats", "corn"],
}
# Farmland with no crop that year.
FALLOW = {"Fallow/Idle Cropland"}
# Farmland the crop table does not cover (counted as farmland, but not mapped to a crop).
OTHER_FARM = {
    "Rice", "Peanuts", "Sunflower", "Barley", "Rye", "Alfalfa", "Spring Wheat", "Durum Wheat",
    "Millet", "Triticale", "Sod/Grass Seed", "Canola", "Sugarcane", "Pecans", "Peaches", "Watermelons",
}
CONTINUOUS_YEARS = 6
PASTURE_LABEL = "Pasture or hay (shown as bermudagrass)"


def is_farmland(category: str) -> bool:
    return category in CDL_TO_CROPS or category in FALLOW or category in OTHER_FARM


def _history(cdl_records: list[dict]) -> list[dict]:
    """Year-by-year CDL labels, oldest first, from the farm-data CDL Feature_Records."""
    rows = []
    for r in cdl_records or []:
        if r.get("variable") != "crop_type":
            continue
        try:
            year = int(r["date"])
        except (KeyError, TypeError, ValueError):
            continue
        category = str(r.get("value", "")).strip()
        if category:
            rows.append({"year": year, "category": category, "crop_ids": CDL_TO_CROPS.get(category, [])})
    return sorted(rows, key=lambda row: row["year"])


def _names(crop_ids, crops) -> str:
    return " + ".join(crops[c]["name"] if c in crops else c for c in crop_ids)


def _years_text(count: int, total: int) -> str:
    return f"{count} of {total} year{'s' if total != 1 else ''}"


def infer(cdl_records: list[dict], crops: dict, override: str | None = None) -> dict:
    """Describe the current rotation.

    Returns {"status": "inferred" | "unknown" | "farmer_choice", "crop_ids", "sequence"
    (a list of yearly crop lists), "label", "evidence", "inferred", "history", "reason"?}.
    Raises ValueError if override is not a crop id in the table.
    """
    history = _history(cdl_records)
    span = f"{history[0]['year']}-{history[-1]['year']}" if history else None

    if override:
        if override not in crops:
            raise ValueError(f"unknown crop id '{override}'")
        return {
            "status": "farmer_choice", "crop_ids": [override], "sequence": [[override]],
            "label": crops[override]["name"], "evidence": "Chosen by you",
            "inferred": False, "history": history,
        }

    def unknown(reason):
        return {"status": "unknown", "crop_ids": [], "sequence": [], "label": "Not known",
                "evidence": reason, "reason": reason, "inferred": False, "history": history}

    if not history:
        return unknown("No crop map history for this spot. Choose what you grow now.")

    total = len(history)
    counts = Counter(row["category"] for row in history)
    non_farm = [row for row in history if not is_farmland(row["category"])]
    if len(non_farm) * 2 > total:
        top, n = Counter(row["category"] for row in non_farm).most_common(1)[0]
        return unknown(f"The crop map shows mostly {top} here ({_years_text(n, total)}, {span}), "
                       "not farmland. Choose what you grow now.")

    # Continuous: one land cover in at least 6 years (or every year when fewer are available).
    top, n = counts.most_common(1)[0]
    needed = CONTINUOUS_YEARS if total >= CONTINUOUS_YEARS else total
    if n >= needed and CDL_TO_CROPS.get(top):
        crop_ids = CDL_TO_CROPS[top]
        label = PASTURE_LABEL if crop_ids == ["bermudagrass"] else f"Continuous {_names(crop_ids, crops).lower()}"
        return {
            "status": "inferred", "crop_ids": list(dict.fromkeys(crop_ids)), "sequence": [crop_ids],
            "label": label, "evidence": f"{top} in {_years_text(n, total)} ({span})",
            "inferred": True, "history": history,
        }

    # Alternating: mapped yearly units that appear at least twice, ordered by last occurrence.
    units = [tuple(row["crop_ids"]) for row in history if row["crop_ids"]]
    if not units:
        return unknown(f"The crop map shows farmland here, but not crops in the crop table ({span}). "
                       "Choose what you grow now.")
    unit_counts = Counter(units)
    repeated = [u for u, c in unit_counts.most_common(3) if c >= 2]
    if len(repeated) >= 2:
        last_seen = {u: max(i for i, x in enumerate(units) if x == u) for u in repeated}
        sequence = [list(u) for u in sorted(repeated, key=last_seen.get)]
        label = " then ".join(_names(u, crops) for u in sequence)
        category_of = {tuple(row["crop_ids"]): row["category"] for row in history if row["crop_ids"]}
        evidence = ", ".join(f"{category_of[tuple(u)]} in {unit_counts[tuple(u)]}" for u in sequence)
        crop_ids = list(dict.fromkeys(c for u in sequence for c in u))
        return {
            "status": "inferred", "crop_ids": crop_ids, "sequence": sequence,
            "label": label[0].upper() + label[1:], "evidence": f"{evidence} of {total} years ({span})",
            "inferred": True, "history": history,
        }

    # Mixed history: use the most recent mapped crop, and say so.
    latest = next(row for row in reversed(history) if row["crop_ids"])
    return {
        "status": "inferred", "crop_ids": list(dict.fromkeys(latest["crop_ids"])), "sequence": [latest["crop_ids"]],
        "label": _names(latest["crop_ids"], crops),
        "evidence": f"Mixed history; most recent mapped crop: {latest['category']} ({latest['year']})",
        "inferred": True, "history": history,
    }
