"""Climate outlook to 2049 from the Open-Meteo Climate API (free, no key, non-commercial use).

What it does:
1. Asks three climate models (CMIP6 HighResMIP, downscaled to about 10 km) for daily highs,
   lows and rain in two periods: 1991-2020 ("recent") and 2030-2049 ("future").
   Open-Meteo data stops on 2050-01-01, so the future period ends in 2049.
2. Computes the same yearly indicators as the NASA POWER trends, for each model and period.
3. The outlook is each model's change from its own recent period to its own future period.
   Comparing a model with itself cancels most of its bias (the "delta method").
   The farmer sees the lowest, middle and highest change across the three models.

Cost and limits (measured on 2026-11-14):
Open-Meteo counts a request as (days / 14) x max(1, variables / 10) x models "calls".
One location costs about 2,348 + 1,565 = 3,913 calls, while the free limits are 600 a
minute, 5,000 an hour and 10,000 a day. So the two requests are sent at least 65 seconds
apart, and a small budget file refuses new loads above 4,500 an hour or 9,000 a day.
Open-Meteo does not report the weight back, so the budget is an estimate with a margin.

Data: Open-Meteo.com, CC BY 4.0. The models follow a high-emissions path (close to RCP8.5).
These are model projections, not measurements and not a forecast of any single year.
"""
import asyncio
import json
import logging
import statistics
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from app.cache import DEFAULT_CACHE_DIR
from app.rotation import indicators as ind
from app.services.base import SourceUnavailable, get_json

log = logging.getLogger("farm_data")

SOURCE = "Open-Meteo Climate API"
LICENCE = "Data: Open-Meteo.com, CC BY 4.0"
URL = "https://climate-api.open-meteo.com/v1/climate"
MODELS = ("EC_Earth3P_HR", "MPI_ESM1_2_XR", "MRI_AGCM3_2_S")
VARIABLES = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum")
RECENT = ("1991-01-01", "2020-12-31")
FUTURE = ("2030-01-01", "2049-12-31")
GAP_SECONDS = 65            # wait between the two requests (per-minute limit)
RESOLUTION_KM = 10
SCENARIO = "high emissions (close to RCP8.5)"

HOUR_LIMIT = 4500           # our guard, under Open-Meteo's 5,000 an hour
DAY_LIMIT = 9000            # our guard, under Open-Meteo's 10,000 a day
BUDGET_FILE = DEFAULT_CACHE_DIR / "openmeteo_budget.json"

# Indicators the models can supply (no evaporation or soil moisture in all three models).
OUTLOOK_INDICATORS = (
    "hot_days", "warm_nights", "frost_days", "last_spring_frost", "first_fall_frost",
    "rain_total", "rain_growing", "dry_spell", "heavy_rain_days",
)
LIMIT_REASON = "the free climate-outlook limit is reached for now; try again in about an hour"


# ---------- cost and budget ----------

def request_weight(start: str, end: str, n_variables: int = len(VARIABLES), n_models: int = len(MODELS)) -> float:
    """Open-Meteo's documented call weight for one location."""
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    return max(days, 14) / 14 * max(1.0, n_variables / 10) * n_models


def location_cost() -> float:
    return request_weight(*RECENT) + request_weight(*FUTURE)


class Budget:
    """Counts our estimated Open-Meteo calls per clock hour and per day, in a small JSON file."""

    def __init__(self, path: Path | str = BUDGET_FILE, hour_limit: float = HOUR_LIMIT, day_limit: float = DAY_LIMIT):
        self.path = Path(path)
        self.hour_limit, self.day_limit = hour_limit, day_limit

    def _load(self, now: datetime) -> dict:
        hour, day = now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {
            "hour": hour, "day": day,
            "hour_calls": data.get("hour_calls", 0) if data.get("hour") == hour else 0,
            "day_calls": data.get("day_calls", 0) if data.get("day") == day else 0,
        }

    def can_spend(self, weight: float, now: datetime | None = None) -> bool:
        state = self._load(now or datetime.now(timezone.utc))
        return state["hour_calls"] + weight <= self.hour_limit and state["day_calls"] + weight <= self.day_limit

    def spend(self, weight: float, now: datetime | None = None) -> None:
        state = self._load(now or datetime.now(timezone.utc))
        state["hour_calls"] += weight
        state["day_calls"] += weight
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(state), encoding="utf-8")
        except OSError as e:
            log.warning("farm_data source=open_meteo budget_write error=%s", type(e).__name__)


# ---------- turning responses into an outlook ----------

def model_series(response: dict, model: str) -> tuple[dict, dict, dict]:
    """(tmin, tmax, rain) as {date: value} for one model from a Climate API response."""
    daily = response.get("daily") if isinstance(response, dict) else None
    if not isinstance(daily, dict) or "time" not in daily:
        raise SourceUnavailable("Open-Meteo sent data we could not read")
    times = daily["time"]
    get = lambda var: ind.from_lists(times, daily.get(f"{var}_{model}") or [])  # noqa: E731
    return get("temperature_2m_min"), get("temperature_2m_max"), get("precipitation_sum")


def _period_averages(tmin, tmax, rain, heavy_threshold) -> dict[str, float]:
    yearly = ind.yearly_indicators(tmin, tmax, rain, heavy_threshold=heavy_threshold)
    out = {}
    for key in OUTLOOK_INDICATORS:
        series = yearly.get(key)
        if series:
            out[key] = round(statistics.fmean(series.values()), 2)
    return out


def _monthly_mean(daily: dict) -> list:
    """Average of a daily series for each calendar month (12 values, None where empty)."""
    sums = [[0.0, 0] for _ in range(12)]
    for d, v in daily.items():
        sums[d.month - 1][0] += v
        sums[d.month - 1][1] += 1
    return [s / n if n else None for s, n in sums]


def build_outlook(recent: dict, future: dict, fetched_on: str, lat: float, lon: float) -> dict:
    """Combine the recent and future responses into an outlook document.

    For each model and indicator: change = future average - recent average. The heavy-rain
    threshold is each model's own 95th percentile of wet days in 1991-2020, so the change
    in heavy-rain days is measured on the model's own scale.
    """
    per_model = {}
    for model in MODELS:
        r_tmin, r_tmax, r_rain = model_series(recent, model)
        f_tmin, f_tmax, f_rain = model_series(future, model)
        if not ind.by_year(r_tmax) or not ind.by_year(f_tmax):
            continue  # this model returned nothing usable; the others still count
        threshold = ind.heavy_rain_threshold(r_rain, 1991, 2020)
        rec = _period_averages(r_tmin, r_tmax, r_rain, threshold)
        fut = _period_averages(f_tmin, f_tmax, f_rain, threshold)
        rec_highs, fut_highs = _monthly_mean(r_tmax), _monthly_mean(f_tmax)
        per_model[model] = {
            "recent": rec,
            "future": fut,
            "change": {k: round(fut[k] - rec[k], 2) for k in rec if k in fut},
            "heavy_rain_threshold_mm": threshold,
            "monthly_tmax_change_c": [
                round(f - r, 2) if f is not None and r is not None else None
                for f, r in zip(fut_highs, rec_highs)
            ],
        }
    if len(per_model) < 2:
        raise SourceUnavailable("Open-Meteo returned too few climate models for an outlook")

    items = []
    for key in OUTLOOK_INDICATORS:
        changes = sorted(m["change"][key] for m in per_model.values() if key in m["change"])
        if len(changes) < 2:
            continue
        label, units = ind.INDICATORS[key]
        items.append({
            "id": key, "label": label, "units": units,
            "change": {"low": changes[0], "mid": round(statistics.median(changes), 2), "high": changes[-1]},
            "n_models": len(changes),
        })

    # Middle (median) change of the average daily high for each month, across models.
    monthly_tmax = []
    for i in range(12):
        values = [m["monthly_tmax_change_c"][i] for m in per_model.values() if m["monthly_tmax_change_c"][i] is not None]
        monthly_tmax.append(round(statistics.median(values), 2) if values else None)
    return {
        "status": "ok",
        "source": SOURCE,
        "licence": LICENCE,
        "models": list(per_model),
        "recent": "1991-2020",
        "future": "2030-2049",
        "resolution_km": RESOLUTION_KM,
        "scenario": SCENARIO,
        "grid_point": {"lat": recent.get("latitude"), "lon": recent.get("longitude")},
        "requested_for": {"lat": round(lat, 4), "lon": round(lon, 4)},
        "fetched_on": fetched_on,
        "indicators": items,
        "monthly": {"tmax_change_c_mid": monthly_tmax},
        "per_model": per_model,
    }


def apply_to_baseline(outlook: dict, trends: dict | None) -> dict:
    """Add projected future values: NASA POWER 1991-2020 observed average + model change.

    Returns a copy of the outlook where each indicator also has "future_value" (low/mid/high)
    and "baseline_avg", when the trends summary has a 1991-2020 average for it.
    """
    baselines = {}
    for item in (trends or {}).get("indicators", []):
        if item.get("baseline_avg") is not None:
            baselines[item["id"]] = item["baseline_avg"]
    items = []
    for item in outlook.get("indicators", []):
        base = baselines.get(item["id"])
        if base is not None:
            item = dict(item, baseline_avg=base,
                        future_value={k: round(base + v, 1) for k, v in item["change"].items()})
        items.append(item)
    return dict(outlook, indicators=items)


# ---------- fetching ----------

def _params(lat: float, lon: float, start: str, end: str) -> dict:
    return {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "start_date": start, "end_date": end,
        "models": ",".join(MODELS), "daily": ",".join(VARIABLES),
    }


async def _get(client, lat, lon, period, budget: Budget):
    weight = request_weight(*period)
    if not budget.can_spend(weight):
        raise SourceUnavailable(LIMIT_REASON)
    budget.spend(weight)  # count it before sending: Open-Meteo counts refused requests too
    try:
        return await get_json(client, URL, _params(lat, lon, *period))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise SourceUnavailable(LIMIT_REASON) from e
        raise


async def fetch_outlook(client, lat: float, lon: float, budget: Budget | None = None,
                        sleep=asyncio.sleep, today: date | None = None) -> dict:
    """Fetch both periods (65 s apart) and build the outlook. Raises SourceUnavailable or httpx errors."""
    budget = budget or Budget()
    if not budget.can_spend(location_cost()):
        raise SourceUnavailable(LIMIT_REASON)
    recent = await _get(client, lat, lon, RECENT, budget)
    await sleep(GAP_SECONDS)
    future = await _get(client, lat, lon, FUTURE, budget)
    return build_outlook(recent, future, (today or date.today()).isoformat(), lat, lon)
