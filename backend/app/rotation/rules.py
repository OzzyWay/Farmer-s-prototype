"""Rules that rule a crop out for this field, each with a plain reason (Req 7.3, 7.4).

Every rule looks at one crop's attributes (config/crops.json) and the field's facts, and
returns an Exclusion when they conflict, or None. The rules run twice: for "today" (recent
conditions) and for the "outlook" (2030-2049). A crop that passes today but fails under the
outlook stays in the options and is shown as a future risk (Req 18.7).

The rules are deliberately simple and conservative. Each one says which fact caused it, so
the farmer can disagree with a specific number instead of a black box.
"""
from app.rotation.site_facts import WET_DRAINAGE, SiteFacts, frequency_at_least

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _months_text(months) -> str:
    return ", ".join(MONTHS[m - 1] for m in sorted(months))


def _exclusion(crop, rule, period, text, evidence):
    return {
        "crop_id": crop["id"],
        "crop_name": crop["name"],
        "rule": rule,
        "period": period,
        "text": text,
        "evidence": [e for e in evidence if e],
    }


def wet_soil(crop: dict, facts: SiteFacts):
    """Crops that do not tolerate wet soil, on soils that flood, pond or drain poorly.

    Hydrologic group D alone is NOT a reason: it means water soaks in slowly, and group D
    Blackland clays widely grow cotton and corn. It is reported as a runoff risk instead.
    """
    if crop["wet_soil_tolerance"] != "low":
        return None
    reasons, evidence = [], []
    for name, fact in (("floods", facts.flooding), ("ponds", facts.ponding)):
        if fact and frequency_at_least(fact.value, "occasional"):
            reasons.append(f"{name} {fact.value}ly" if fact.value == "occasional" else f"{name} ({fact.value})")
            evidence.append(fact.cite())
    if facts.drainage and str(facts.drainage.value).lower() in WET_DRAINAGE:
        reasons.append(f"is {str(facts.drainage.value).lower()}")
        evidence.append(facts.drainage.cite())
    if not reasons:
        return None
    return _exclusion(crop, "wet_soil", facts.period,
                      f"{crop['name']} does not tolerate wet soil, and this soil {' and '.join(reasons)}.", evidence)


def heat(crop: dict, facts: SiteFacts):
    """Heat-sensitive crops growing during months whose average daily high is above 35 °C."""
    if crop["heat_tolerance"] != "low" or not facts.heat_months:
        return None
    overlap = set(crop["growing_months"]) & set(facts.heat_months)
    if not overlap:
        return None
    when = "today" if facts.period == "today" else "in 2030-2049"
    return _exclusion(crop, "heat", facts.period,
                      f"{crop['name']} does not tolerate heat, and {_months_text(overlap)} average highs above 35 °C {when}.",
                      [facts.hot_days.cite() if facts.hot_days else None])


def frost(crop: dict, facts: SiteFacts):
    """Frost-sensitive crops growing during the frost season."""
    if crop["frost_tolerance"] != "low" or not facts.frost_months:
        return None
    overlap = set(crop["growing_months"]) & set(facts.frost_months)
    if not overlap:
        return None
    return _exclusion(crop, "frost", facts.period,
                      f"{crop['name']} is killed by frost, and frost is typical in {_months_text(overlap)}.",
                      [facts.frost_days.cite() if facts.frost_days else None,
                       facts.first_frost_doy.cite() if facts.first_frost_doy else None])


def water(crop: dict, facts: SiteFacts, irrigation: bool):
    """High-water crops without irrigation where yearly rain is below what they need."""
    limit = crop["limits"].get("min_rain_mm_rainfed")
    if crop["water_need"] != "high" or irrigation or limit is None or not facts.rain_total:
        return None
    if facts.rain_total.value >= limit:
        return None
    when = "recent years" if facts.period == "today" else "2030-2049"
    return _exclusion(crop, "water", facts.period,
                      f"{crop['name']} needs about {limit:g} mm of rain a year without irrigation; "
                      f"this field averaged {facts.rain_total.value:g} mm in {when}, and you said there is no irrigation.",
                      [facts.rain_total.cite()])


def check_crop(crop: dict, facts: SiteFacts, irrigation: bool) -> list[dict]:
    """All exclusions for one crop under one set of facts."""
    found = [wet_soil(crop, facts), heat(crop, facts), frost(crop, facts), water(crop, facts, irrigation)]
    return [f for f in found if f]


def evaluate(crops: dict, today: SiteFacts, outlook: SiteFacts | None, irrigation: bool) -> dict:
    """Run every rule for every crop.

    Returns {"excluded": {crop_id: [exclusion, ...]},           # ruled out today
             "future": {crop_id: [exclusion, ...]}}              # fine today, ruled out in 2030-2049
    """
    excluded, future = {}, {}
    for crop_id, crop in crops.items():
        now = check_crop(crop, today, irrigation)
        if now:
            excluded[crop_id] = now
            continue
        if outlook is not None:
            later = check_crop(crop, outlook, irrigation)
            if later:
                future[crop_id] = later
    return {"excluded": excluded, "future": future}
