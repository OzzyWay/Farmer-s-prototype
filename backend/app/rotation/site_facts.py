"""The facts the rotation engine works from, each one carrying where it came from.

A Fact is one value (for example "91 hot days a year") plus its units, source, resolution and
period, so any rule or sentence that uses it can say exactly what it is based on.

SiteFacts holds every fact about one field for one period: "today" (recent years) or the
"outlook" (2030-2049 projection). A missing source leaves its facts as None; the rules then
skip what they cannot check, and the confidence of the result goes down.

FarmInputs holds what the farmer told us: priorities and constraints.
"""
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

# Farmer priorities the tool understands (Req 9.1). The values are the API spellings.
PRIORITIES = ("save_water", "build_soil", "forage", "income", "fewer_passes")
LIVESTOCK_VALUES = ("yes", "no", "unknown")


@dataclass(frozen=True)
class Fact:
    """One value with its provenance."""

    value: float | int | str | None
    units: str = ""
    source: str = ""
    resolution_m: int | None = None
    period: str = ""  # e.g. "2016-2025", "current survey", "2030-2049 (middle of 3 models)"

    def cite(self) -> dict:
        """The evidence entry shown next to a finding or a reason."""
        return {
            "value": self.value,
            "units": self.units,
            "source": self.source,
            "resolution_m": self.resolution_m,
            "period": self.period,
        }


@dataclass(frozen=True)
class SiteFacts:
    """Everything known about one field for one period. Any field can be None (unknown)."""

    period: str = "today"  # "today" or "outlook"

    # Climate (NASA POWER daily for today; delta-method projection for the outlook)
    hot_days: Fact | None = None          # days a year above 35 °C
    warm_nights: Fact | None = None       # nights a year above 24 °C
    frost_days: Fact | None = None        # days a year at or below 0 °C
    last_frost_doy: Fact | None = None    # typical last spring frost, day of year
    first_frost_doy: Fact | None = None   # typical first fall frost, day of year
    rain_total: Fact | None = None        # mm a year
    rain_growing: Fact | None = None      # mm, April to September
    rain_cv: Fact | None = None           # year-to-year variation of rain, % (coefficient of variation)
    wettest_month: Fact | None = None     # 1..12
    heat_months: tuple[int, ...] = ()     # months whose average daily high is above 35 °C
    frost_months: tuple[int, ...] = ()    # months between first fall and last spring frost

    # Soil (USDA SSURGO dominant component, or the farmer's soil test in Phase 2)
    hydro_group: Fact | None = None       # A, B, C, D or dual like "C/D"
    drainage: Fact | None = None          # e.g. "Moderately well drained"
    flooding: Fact | None = None          # none, very rare, rare, occasional, frequent, very frequent
    ponding: Fact | None = None
    slope_high: Fact | None = None        # % (top of the slope range)
    om_pct: Fact | None = None            # surface organic matter, %
    awc: Fact | None = None               # available water capacity, in/in
    k_factor: Fact | None = None          # erodibility K
    texture_group: Fact | None = None     # clay, clay loam, loam, sandy loam, sand, silt

    # Sources that were not available for this field (names shown to the farmer)
    missing_sources: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FarmInputs:
    """What the farmer chose in the priority picker (Req 9)."""

    priorities: frozenset[str] = frozenset()
    irrigation: bool = False
    livestock: str = "unknown"            # "yes", "no" or "unknown"
    no_till: bool = False
    current_override: str | None = None   # crop id the farmer picked as the current rotation


# ---------------------------------------------------------------------------
# Builders: turn the raw results from each source into SiteFacts (task 7.1)
# ---------------------------------------------------------------------------

WET_DRAINAGE = ("somewhat poorly drained", "poorly drained", "very poorly drained")
FREQUENCY_ORDER = ("none", "very rare", "rare", "occasional", "frequent", "very frequent")
HEAT_MONTH_C = 35.0  # a month is a heat-stress month when its average daily high is above this


def frequency_at_least(value: str | None, threshold: str) -> bool:
    """True when a SSURGO frequency class is at least as frequent as threshold."""
    if value not in FREQUENCY_ORDER:
        return False
    return FREQUENCY_ORDER.index(value) >= FREQUENCY_ORDER.index(threshold)


def parse_slope_high(text) -> float | None:
    """'0 to 1' -> 1.0, '8 to 20' -> 20.0, '3' -> 3.0. None when there is no number."""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(text or ""))
    return float(numbers[-1]) if numbers else None


def doy_month(doy) -> int | None:
    """Day of year (non-leap calendar) -> month number."""
    try:
        return (date(2001, 1, 1) + timedelta(days=int(round(float(doy))) - 1)).month
    except (TypeError, ValueError, OverflowError):
        return None


def frost_months(first_fall_doy, last_spring_doy) -> tuple[int, ...]:
    """Months from the typical first fall frost to the typical last spring frost."""
    first, last = doy_month(first_fall_doy), doy_month(last_spring_doy)
    if first is None or last is None:
        return ()
    return tuple(sorted(set(range(first, 13)) | set(range(1, last + 1))))


def _records(farm_sources: dict, key: str) -> list:
    group = (farm_sources or {}).get(key) or {}
    return group.get("records", []) if group.get("status") == "ok" else []


def _by_var(records):
    out = {}
    for r in records:
        out.setdefault(r["variable"], []).append(r)
    return out


def _monthly(values_by_month: dict) -> list | None:
    if len(values_by_month) != 12:
        return None
    return [values_by_month[m] for m in range(1, 13)]


def build_today(farm_sources: dict | None, profile: dict | None, trends: dict | None) -> SiteFacts:
    """SiteFacts for recent conditions.

    farm_sources: the "sources" part of the /api/farm-data result (NASA POWER, SSURGO, CDL).
    profile: the soil profile (all SSURGO layers, flooding, ponding) or None.
    trends: the NASA POWER 1981+ trends summary or None.
    """
    missing = []
    farm_sources = farm_sources or {}
    for key, label in (("nasa_power", "NASA POWER climate normals"), ("ssurgo", "USDA SSURGO soil"),
                       ("cdl", "USDA NASS CDL crop history")):
        if (farm_sources.get(key) or {}).get("status") != "ok":
            missing.append(label)
    if not profile or profile.get("status") != "ok":
        missing.append("USDA SSURGO soil profile")
        profile = None
    if not trends or trends.get("status") != "ok":
        missing.append("NASA POWER daily climate since 1981")
        trends = None

    facts: dict = {}

    # --- climate: last 10 years of NASA POWER daily data ---
    if trends:
        period = trends.get("recent_period") or ""
        items = {i["id"]: i for i in trends.get("indicators", [])}

        def recent(key, units):
            item = items.get(key)
            if item and item.get("recent_avg") is not None:
                return Fact(item["recent_avg"], units, "NASA POWER", 50000, period)
            return None
        facts["hot_days"] = recent("hot_days", "days/year")
        facts["warm_nights"] = recent("warm_nights", "nights/year")
        facts["frost_days"] = recent("frost_days", "days/year")
        facts["last_frost_doy"] = recent("last_spring_frost", "day of year")
        facts["first_frost_doy"] = recent("first_fall_frost", "day of year")
        facts["rain_total"] = recent("rain_total", "mm/year")
        facts["rain_growing"] = recent("rain_growing", "mm")
        if trends.get("rain_cv_pct") is not None:
            facts["rain_cv"] = Fact(trends["rain_cv_pct"], "%", "NASA POWER", 50000, trends.get("period", ""))
        monthly = trends.get("monthly") or {}
        highs, rain = monthly.get("avg_high_c"), monthly.get("rain_mm")
        if highs and all(h is not None for h in highs):
            facts["heat_months"] = tuple(m for m, h in enumerate(highs, start=1) if h > HEAT_MONTH_C)
        if rain and all(r is not None for r in rain):
            wettest = max(range(12), key=lambda i: rain[i]) + 1
            facts["wettest_month"] = Fact(wettest, "month", "NASA POWER", 50000, monthly.get("period", ""))
        if facts.get("last_frost_doy") and facts.get("first_frost_doy"):
            facts["frost_months"] = frost_months(facts["first_frost_doy"].value, facts["last_frost_doy"].value)

    # Fall back to the farm-data monthly normals when the daily trends are missing.
    power = _by_var(_records(farm_sources, "nasa_power"))
    if "heat_months" not in facts and power.get("temperature_max"):
        highs = _monthly({int(r["date"]): r["value"] for r in power["temperature_max"]})
        if highs:
            facts["heat_months"] = tuple(m for m, h in enumerate(highs, start=1) if h > HEAT_MONTH_C)
    if "wettest_month" not in facts and power.get("precipitation"):
        rain = _monthly({int(r["date"]): r["value"] for r in power["precipitation"]})
        if rain:
            facts["wettest_month"] = Fact(max(range(12), key=lambda i: rain[i]) + 1, "month", "NASA POWER", 50000, "climatology")
    if not facts.get("hot_days") and power.get("heat_days_per_year"):
        r = power["heat_days_per_year"][0]
        facts["hot_days"] = Fact(r["value"], "days/year", r["source"], r["resolution_m"], r["date"])
    if not facts.get("frost_days") and power.get("frost_days_per_year"):
        r = power["frost_days_per_year"][0]
        facts["frost_days"] = Fact(r["value"], "days/year", r["source"], r["resolution_m"], r["date"])
    if not facts.get("rain_total") and power.get("precipitation") and len(power["precipitation"]) == 12:
        facts["rain_total"] = Fact(round(sum(r["value"] for r in power["precipitation"])), "mm/year",
                                   "NASA POWER", 50000, "climatology")

    # --- soil: SSURGO surface facts plus the profile's flooding and ponding ---
    soil = {r["variable"]: r for r in _records(farm_sources, "ssurgo")}

    def soil_fact(variable, units="", convert=lambda v: v):
        r = soil.get(variable)
        if r is None:
            return None
        value = convert(r["value"])
        return None if value is None else Fact(value, units or r.get("units", ""), r["source"], r["resolution_m"], "current survey")
    facts["hydro_group"] = soil_fact("soil_hydrologic_group")
    facts["drainage"] = soil_fact("soil_drainage_class")
    facts["om_pct"] = soil_fact("soil_organic_matter", "%")
    facts["awc"] = soil_fact("soil_available_water_capacity", "in/in")
    facts["k_factor"] = soil_fact("soil_erodibility_k")
    facts["slope_high"] = soil_fact("soil_slope_range", "%", parse_slope_high)
    if profile:
        source, res = profile.get("source", "USDA SSURGO"), profile.get("resolution_m")
        for key in ("flooding", "ponding"):
            if profile.get(key):
                facts[key] = Fact(profile[key], "", source, res, "current survey")
        top = (profile.get("layers") or [{}])[0]
        if top.get("texture_group"):
            facts["texture_group"] = Fact(top["texture_group"], "", source, res, "current survey")
        if facts.get("om_pct") is None and top.get("om_pct") is not None:
            facts["om_pct"] = Fact(top["om_pct"], "%", source, res, "current survey")

    return SiteFacts(period="today", missing_sources=tuple(missing),
                     **{k: v for k, v in facts.items() if v is not None})


def build_outlook_facts(today: SiteFacts, outlook: dict | None, trends: dict | None = None) -> SiteFacts | None:
    """SiteFacts for 2030-2049: today's facts with the projected climate (delta method).

    outlook must already have future values added (openmeteo.apply_to_baseline). Soil facts
    are unchanged. Returns None when no outlook is available.
    """
    if not outlook or outlook.get("status") != "ok":
        return None
    items = {i["id"]: i for i in outlook.get("indicators", [])}
    n = len(outlook.get("models", []))
    period = f"{outlook.get('future', '2030-2049')} (middle of {n} models)"
    source = outlook.get("source", "Open-Meteo Climate API")

    def future(key, units):
        value = (items.get(key) or {}).get("future_value", {}).get("mid")
        return Fact(value, units, source, (outlook.get("resolution_km") or 10) * 1000, period) if value is not None else None

    changes = {}
    for field, key, units in (("hot_days", "hot_days", "days/year"), ("warm_nights", "warm_nights", "nights/year"),
                              ("frost_days", "frost_days", "days/year"), ("last_frost_doy", "last_spring_frost", "day of year"),
                              ("first_frost_doy", "first_fall_frost", "day of year"), ("rain_total", "rain_total", "mm/year"),
                              ("rain_growing", "rain_growing", "mm")):
        fact = future(key, units)
        if fact is not None:
            changes[field] = fact

    # Heat months: today's average daily high plus the models' middle monthly warming.
    highs = ((trends or {}).get("monthly") or {}).get("avg_high_c")
    warming = (outlook.get("monthly") or {}).get("tmax_change_c_mid")
    if highs and warming and all(h is not None for h in highs) and all(w is not None for w in warming):
        changes["heat_months"] = tuple(m for m, (h, w) in enumerate(zip(highs, warming), start=1) if h + w > HEAT_MONTH_C)
    first = changes.get("first_frost_doy") or today.first_frost_doy
    last = changes.get("last_frost_doy") or today.last_frost_doy
    if first and last:
        changes["frost_months"] = frost_months(first.value, last.value)

    return replace(today, period="outlook", **changes)
