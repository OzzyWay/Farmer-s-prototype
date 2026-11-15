"""The rotation patterns the tool can suggest, and how they are filled with crops (Req 7.2).

A template is a short list of "slots" in time order (for example "summer crop", then
"winter cover"). Each slot lists candidate crops in order of preference. The engine fills
each slot with the first candidate that:

- is not ruled out for this field today (rules.py),
- is not from the same pest or disease family as the crop just before it (Req 7.6),
- and, at the end, does not clash with the first crop when the rotation starts over.

If a choice makes a later slot impossible, the search goes back one step and tries the next
candidate. It is a small, ordered search, so the result is always the same for the same
field (Req 10.5). A template that cannot be filled is simply not suggested.

Templates that build on the current rotation keep the farmer's crops and add to them.
"""
CURRENT = "CURRENT"

WINTER_LEGUMES = ["hairy_vetch", "crimson_clover", "winter_wheat_cover"]
WINTER_COVERS = ["winter_wheat_cover", "annual_ryegrass", "hairy_vetch"]
SUMMER_COVERS = ["cowpea", "sunn_hemp", "sorghum_sudangrass"]

# Purpose of each template, used for the "why" text and the livestock constraint.
TEMPLATES = [
    {
        "id": "add_winter_legume",
        "name": "Keep your crop, add a winter legume",
        "purpose": "soil",
        "uses_current": True,
        "added_season": "winter",
        "candidates": WINTER_LEGUMES,
    },
    {
        "id": "forage_double",
        "name": "Summer forage + winter grazing",
        "purpose": "forage",
        "needs_livestock": True,
        "slots": [
            {"role": "summer", "year": 1, "candidates": ["sorghum_sudangrass", "cowpea"]},
            {"role": "winter", "year": 1, "candidates": ["forage_oats", "annual_ryegrass"]},
        ],
    },
    {
        "id": "native_perennial",
        "name": "Native warm-season grass with a winter legume",
        "purpose": "erosion_water",
        "slots": [
            {"role": "perennial", "year": 1, "candidates": ["native_grass_mix"]},
            {"role": "winter", "year": 1, "candidates": ["hairy_vetch", "crimson_clover"], "optional": True, "overseed": True},
        ],
    },
    {
        "id": "cover_system",
        "name": "Summer cover crop + winter cover crop",
        "purpose": "soil",
        "slots": [
            {"role": "summer", "year": 1, "candidates": SUMMER_COVERS},
            {"role": "winter", "year": 1, "candidates": WINTER_COVERS},
        ],
    },
    {
        "id": "drought_row",
        "name": "Drought-tolerant 3-year row-crop rotation",
        "purpose": "income",
        "slots": [
            {"role": "summer", "year": 1, "candidates": ["grain_sorghum"]},
            {"role": "winter", "year": 1, "candidates": ["hairy_vetch", "winter_wheat_cover"]},
            {"role": "summer", "year": 2, "candidates": ["cotton", "soybean"]},
            {"role": "winter", "year": 2, "candidates": ["winter_wheat_grain"]},
            {"role": "summer", "year": 3, "candidates": ["sunn_hemp", "cowpea"], "optional": True},
        ],
    },
    {
        "id": "cover_only",
        "name": "Keep your crop, add a cover crop in the open season",
        "purpose": "cover",
        "uses_current": True,
        "added_season": "open",
    },
]
TEMPLATE_ORDER = [t["id"] for t in TEMPLATES]


def _season_of(crop: dict) -> str:
    return crop["season"]  # "warm", "cool" or "perennial"


def current_slots(current: dict, crops: dict) -> list[dict]:
    """Fixed slots for the farmer's current rotation, one per year of its sequence."""
    slots = []
    for year, unit in enumerate(current.get("sequence") or [], start=1):
        ids = [c for c in unit if c in crops]
        if ids:
            slots.append({"role": "current", "year": year, "fixed": ids})
    return slots


def _slots_for(template: dict, current: dict | None, crops: dict) -> list[dict] | None:
    """The slot list for a template, or None when the template does not apply."""
    if not template.get("uses_current"):
        return [dict(s) for s in template["slots"]]
    if not current or not current.get("sequence"):
        return None
    slots = []
    added = False
    for slot in current_slots(current, crops):
        slots.append(slot)
        seasons = {_season_of(crops[c]) for c in slot["fixed"]}
        has_winter = "cool" in seasons
        has_summer = "warm" in seasons or "perennial" in seasons
        overseed = "perennial" in seasons
        if template["added_season"] == "winter":
            if has_winter:
                continue
            slots.append({"role": "winter", "year": slot["year"], "candidates": template["candidates"], "overseed": overseed})
            added = True
        else:  # "open": fill whichever season the current crop leaves bare
            if has_winter and has_summer:
                continue
            if has_summer:
                slots.append({"role": "winter", "year": slot["year"], "candidates": WINTER_COVERS, "overseed": overseed})
            else:
                slots.append({"role": "summer", "year": slot["year"], "candidates": SUMMER_COVERS})
            added = True
    return slots if added else None


def _families(choice, crops) -> set:
    return {f for c in choice for f in crops[c]["pest_families"]}


def _clash(a, b, crops) -> bool:
    return bool(a) and bool(b) and bool(_families(a, crops) & _families(b, crops))


def fill(template: dict, current: dict | None, crops: dict, excluded: set) -> dict | None:
    """Fill a template with crops for this field. Returns a strategy dict, or None."""
    slots = _slots_for(template, current, crops)
    if not slots:
        return None

    options = []
    for slot in slots:
        if "fixed" in slot:
            options.append([tuple(slot["fixed"])])
            continue
        allowed = [(c,) for c in slot["candidates"] if c in crops and c not in excluded]
        if slot.get("optional"):
            allowed.append(())  # leaving it empty is allowed
        options.append(allowed)

    def previous_crop(chosen):
        for choice in reversed(chosen):
            if choice:
                return choice
        return ()

    def search(i, chosen):
        if i == len(slots):
            first = next((c for c in chosen if c), ())
            last = previous_crop(chosen)
            if len([c for c in chosen if c]) > 1 and _clash(last, first, crops):
                return None  # the rotation would clash when it starts over
            return chosen
        for choice in options[i]:
            if choice and _clash(previous_crop(chosen), choice, crops):
                continue
            found = search(i + 1, chosen + [choice])
            if found is not None:
                return found
        return None

    chosen = search(0, [])
    if chosen is None or not any(chosen):
        return None

    filled = []
    for slot, choice in zip(slots, chosen):
        if choice:
            filled.append({
                "crop_ids": list(choice),
                "year": slot["year"],
                "role": slot["role"],
                "overseed": bool(slot.get("overseed")),
                "fixed": "fixed" in slot,
            })
    years = max(s["year"] for s in filled)
    return {
        "id": template["id"],
        "name": template["name"],
        "purpose": template["purpose"],
        "is_current": False,
        "years": years,
        "slots": filled,
        "crop_ids": list(dict.fromkeys(c for s in filled for c in s["crop_ids"])),
    }


def current_strategy(current: dict, crops: dict) -> dict:
    """The farmer's current rotation as a strategy (it may have no crops if unknown)."""
    slots = [{"crop_ids": s["fixed"], "year": s["year"], "role": "current", "overseed": False, "fixed": True}
             for s in current_slots(current, crops)]
    return {
        "id": "current",
        "name": f"Current: {current.get('label', 'not known')}",
        "purpose": "current",
        "is_current": True,
        "years": max([s["year"] for s in slots], default=1),
        "slots": slots,
        "crop_ids": list(dict.fromkeys(c for s in slots for c in s["crop_ids"])),
    }


def calendar(strategy: dict, crops: dict, facts) -> list[list[dict]]:
    """12 months for each year of the rotation: what is in the ground, and the month flags.

    A crop's months that come before its first listed month (for example January for a
    crop in the ground from October) belong to the next year of the rotation.
    """
    n = max(1, strategy["years"])
    cells = [[set() for _ in range(12)] for _ in range(n)]
    for slot in strategy["slots"]:
        for crop_id in slot["crop_ids"]:
            months = crops[crop_id]["in_ground_months"]
            first = months[0]
            for m in months:
                year_index = (slot["year"] - 1 + (1 if m < first else 0)) % n
                cells[year_index][m - 1].add(crop_id)
    heat = set(getattr(facts, "heat_months", ()) or ())
    frost = set(getattr(facts, "frost_months", ()) or ())
    wettest = facts.wettest_month.value if getattr(facts, "wettest_month", None) else None
    return [
        [{"month": m + 1, "crop_ids": sorted(year[m]), "bare": not year[m],
          "heat": (m + 1) in heat, "frost": (m + 1) in frost, "wettest": (m + 1) == wettest}
         for m in range(12)]
        for year in cells
    ]


def in_season(strategy: dict, crops: dict) -> bool:
    """Every crop is only placed in its own months (Req 7.7). True by construction; checked in tests."""
    for year in calendar(strategy, crops, None):
        for cell in year:
            for crop_id in cell["crop_ids"]:
                if cell["month"] not in crops[crop_id]["in_ground_months"]:
                    return False
    return True
