"""National Weather Service (api.weather.gov): 7-day forecast and active alerts. Free, no key, US only.

fetch_periods()         the forecast as 12-hour periods (about 7 days, up to 14 periods)
fetch_official_alerts() active NWS watches, warnings and advisories for the point
farm_alerts()           alerts this app works out from the next 3 days of forecast:
                        frost or freeze, heat, rain or storms, and wind too strong to spray

The alert thresholds and the "what to do" texts come from the colleague's
Farmers-Helpers project (farmhelper/weather.py). Each threshold is one named constant.
The NWS asks every client to identify itself with a User-Agent header; no key is used.
"""
import asyncio
import re

import httpx

from app.services.base import SourceUnavailable, get_json

NWS = "https://api.weather.gov"
NWS_HEADERS = {
    "User-Agent": "FieldShiftHackathon/1.0 (https://github.com/rowitus/Farmer-s-prototype)",
    "Accept": "application/geo+json",
}
FORECAST_TOTAL_TIMEOUT = 15.0  # /points then the forecast URL: two calls of up to 10 s each, capped here

# --- Farm alert thresholds (from the colleague's farmhelper/weather.py) ---
ALERT_WINDOW_PERIODS = 6   # first 6 twelve-hour periods, about 3 days
FROST_DANGER_F = 28        # coldest night at or below: "danger", Hard freeze
FROST_WARN_F = 32          # at or below: "warn", Freeze
FROST_INFO_F = 36          # at or below: "info", Frost possible
HEAT_WARN_F = 95           # hottest day at or above: "warn", Heat
HEAT_DANGER_F = 100        # at or above: "danger", Extreme heat
RAIN_PCT = 70              # highest precipitation chance at or above: rain alert
WIND_INFO_MPH = 20         # highest wind at or above: "info"
WIND_WARN_MPH = 30         # at or above: "warn"
HEAVY_WORDS = re.compile(r"heavy|thunderstorm|storm", re.I)

FARM_SOURCE = "Based on NWS forecast"
OFFICIAL_SOURCE = "National Weather Service"
SEVERITY_RANK = {"danger": 0, "warn": 1, "info": 2}

# What to do, in plain words (copied from the colleague's weather.py).
FROST_ACTIONS = {
    "danger": ("Cold enough to kill most unprotected crops. Harvest what's ready, cover or bring in tender plants, "
               "drain irrigation lines and hoses, and make sure livestock water won't freeze."),
    "warn": ("Tender plants (tomatoes, peppers, beans, squash, melons) will be damaged. Cover them with "
             "frost cloth or sheets before sunset, or harvest now. Cool-season crops will be fine."),
    "info": "Frost can form on clear, calm nights even above freezing. Cover tender seedlings tonight.",
}
HEAT_ACTION = ("Water early in the morning so plants go into the heat hydrated, shade young transplants, "
               "give livestock extra water and shade, and do heavy field work before 10 AM.")
RAIN_ACTION = ("Hold off on spraying or spreading fertilizer, since rain will wash it off or into ditches. "
               "Skip irrigation and check that field drainage is clear.")
WIND_ACTION = ("Too windy to spray: pesticide and herbicide drift onto neighbors' fields. Secure row covers "
               "and stake tall plants. Dry, windy days also raise grass-fire risk.")


class OutsideCoverage(SourceUnavailable):
    """The point is outside NWS coverage (HTTP 404 from /points)."""


def forecast_page_url(lat: float, lon: float) -> str:
    return f"https://forecast.weather.gov/MapClick.php?lat={lat:.4f}&lon={lon:.4f}"


# ---------- parsing (pure) ----------

def _wind_max(text) -> int:
    """'5 to 10 mph' -> 10, 'Calm' -> 0."""
    numbers = [int(n) for n in re.findall(r"\d+", str(text or ""))]
    return max(numbers) if numbers else 0


def parse_periods(data: dict) -> list[dict]:
    """NWS forecast JSON -> list of periods. Raises KeyError/TypeError on a body that is not NWS-shaped."""
    out = []
    for p in data["properties"]["periods"]:
        temp = p["temperature"]
        if p.get("temperatureUnit") == "C" and temp is not None:
            temp = round(temp * 9 / 5 + 32)
        out.append({
            "name": p["name"],
            "start": p["startTime"],
            "is_day": bool(p["isDaytime"]),
            "temp_f": temp,
            "rain_pct": (p.get("probabilityOfPrecipitation") or {}).get("value") or 0,
            "wind": p.get("windSpeed") or "",
            "wind_max_mph": _wind_max(p.get("windSpeed")),
            "short": p.get("shortForecast") or "",
            "detail": p.get("detailedForecast") or "",
        })
    return out


def parse_official_alerts(data: dict) -> list[dict]:
    """alerts/active JSON -> list of official alerts."""
    out = []
    for f in data.get("features") or []:
        p = f.get("properties") or {}
        severity = (p.get("severity") or "").lower()
        out.append({
            "id": p.get("id") or f.get("id"),
            "kind": "official",
            "source": OFFICIAL_SOURCE,
            "level": "danger" if severity in ("extreme", "severe") else "warn",
            "title": p.get("event") or "Weather alert",
            "text": p.get("headline") or "",
            "detail": "\n\n".join(x for x in (p.get("description"), p.get("instruction")) if x),
            "until": p.get("ends") or p.get("expires"),
        })
    return out


# ---------- farm alerts (pure: no I/O, no clock) ----------

def _alert(kind, period, value, level, title, reason, action) -> dict:
    return {"id": f"{kind}-{period['start'][:10]}-{value}", "kind": kind, "source": FARM_SOURCE,
            "level": level, "title": title, "reason": reason, "action": action, "until": period["start"]}


def farm_alerts(periods: list[dict]) -> list[dict]:
    """At most one alert per kind from the first ALERT_WINDOW_PERIODS periods, most serious first."""
    soon = [p for p in (periods or [])[:ALERT_WINDOW_PERIODS] if p.get("temp_f") is not None]
    out = []

    nights = [p for p in soon if not p["is_day"]]
    if nights:
        cold = min(nights, key=lambda p: p["temp_f"])
        t = cold["temp_f"]
        if t <= FROST_INFO_F:
            if t <= FROST_DANGER_F:
                level, title = "danger", "Hard freeze"
            elif t <= FROST_WARN_F:
                level, title = "warn", "Freeze"
            else:
                level, title = "info", "Frost possible"
            out.append(_alert("frost_freeze", cold, t, level, title, f"{cold['name']}: {t} °F", FROST_ACTIONS[level]))

    days = [p for p in soon if p["is_day"]]
    if days:
        hot = max(days, key=lambda p: p["temp_f"])
        t = hot["temp_f"]
        if t >= HEAT_WARN_F:
            level, title = ("danger", "Extreme heat") if t >= HEAT_DANGER_F else ("warn", "Heat")
            out.append(_alert("extreme_heat", hot, t, level, title, f"{hot['name']}: {t} °F", HEAT_ACTION))

    window = (periods or [])[:ALERT_WINDOW_PERIODS]
    if window:
        wet = max(window, key=lambda p: p.get("rain_pct") or 0)
        pct = wet.get("rain_pct") or 0
        if pct >= RAIN_PCT:
            heavy = HEAVY_WORDS.search(f"{wet.get('short', '')} {wet.get('detail', '')}")
            level, title = ("warn", "Storms likely") if heavy else ("info", "Rain likely")
            out.append(_alert("heavy_rain_storm", wet, pct, level, title, f"{wet['name']}: {pct}% chance", RAIN_ACTION))

        windy = max(window, key=lambda p: p.get("wind_max_mph") or 0)
        mph = windy.get("wind_max_mph") or 0
        if mph >= WIND_INFO_MPH:
            level = "warn" if mph >= WIND_WARN_MPH else "info"
            out.append(_alert("wind_spray", windy, mph, level, "Windy", f"{windy['name']}: up to {mph} mph", WIND_ACTION))

    return sorted(out, key=lambda a: SEVERITY_RANK[a["level"]])  # stable sort keeps kind order on ties


# ---------- fetching ----------

async def fetch_periods(client, lat: float, lon: float) -> list[dict]:
    """Forecast periods for a point. Raises OutsideCoverage on a 404 from /points."""
    async def chain():
        try:
            point = await get_json(client, f"{NWS}/points/{lat:.4f},{lon:.4f}", headers=NWS_HEADERS)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise OutsideCoverage("The National Weather Service only covers US locations, "
                                      "and this point is outside its coverage") from e
            raise
        data = await get_json(client, point["properties"]["forecast"], headers=NWS_HEADERS)
        return parse_periods(data)
    return await asyncio.wait_for(chain(), FORECAST_TOTAL_TIMEOUT)


async def fetch_official_alerts(client, lat: float, lon: float) -> list[dict]:
    data = await get_json(client, f"{NWS}/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"},
                          headers=NWS_HEADERS)
    return parse_official_alerts(data)
