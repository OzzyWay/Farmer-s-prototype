"""National Weather Service tests: parsing, farm-alert thresholds, and GET /api/weather.

Fixtures: nws_points.json and nws_forecast.json are real api.weather.gov answers for Webberwood
saved on 2026-11-14 (trimmed to the fields we read). The real alerts answer was empty that day, so
nws_alerts.json is hand-written from the documented alerts/active shape; nws_alerts_empty.json is
that empty answer. All upstream calls go to httpx.MockTransport; no real network.
"""
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.cache import DiskCache
from app.services import nws
from app.services.base import get_json
from app.weather_data import CACHE_TTL_S

FX = Path(__file__).parent / "fixtures"
TEXT = {name: (FX / f"nws_{name}.json").read_text(encoding="utf-8")
        for name in ("points", "forecast", "alerts", "alerts_empty")}
FARM = {"lat": "30.233589", "lon": "-97.496006"}


# ---------- parsing ----------

def test_parse_real_forecast():
    periods = nws.parse_periods(json.loads(TEXT["forecast"]))
    assert len(periods) == 14
    p = periods[0]
    assert p == {"name": "Tonight", "start": "2026-11-14T22:00:00-06:00", "is_day": False, "temp_f": 54,
                 "rain_pct": 67, "wind": "10 mph", "wind_max_mph": 10, "short": "Rain Showers Likely",
                 "detail": p["detail"]}
    assert "low around 54" in p["detail"]


def test_celsius_is_converted_and_missing_rain_is_zero():
    body = {"properties": {"periods": [{"name": "Today", "startTime": "2026-01-01T06:00:00-06:00",
            "isDaytime": True, "temperature": 0, "temperatureUnit": "C",
            "probabilityOfPrecipitation": {"value": None}, "windSpeed": "Calm", "shortForecast": "Sunny"}]}}
    p = nws.parse_periods(body)[0]
    assert p["temp_f"] == 32 and p["rain_pct"] == 0 and p["wind_max_mph"] == 0 and p["detail"] == ""


def test_wind_max_takes_the_largest_number():
    assert nws._wind_max("5 to 15 mph") == 15
    assert nws._wind_max("") == 0


def test_official_alert_level_and_end_time():
    a, b = nws.parse_official_alerts(json.loads(TEXT["alerts"]))
    assert a["level"] == "danger" and a["title"] == "Severe Thunderstorm Warning"
    assert a["until"] == "2026-11-15T18:00:00-06:00"
    assert "interior room" in a["detail"] and a["source"] == "National Weather Service"
    assert b["level"] == "warn" and b["until"] == "2026-11-16T00:00:00-06:00"  # no ends -> expires
    assert nws.parse_official_alerts(json.loads(TEXT["alerts_empty"])) == []


def test_get_json_without_headers_still_works():
    import asyncio

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": 1}))) as c:
            return await get_json(c, "https://example.test/x", {"a": 1})
    assert asyncio.run(go()) == {"ok": 1}


# ---------- farm alerts ----------

def period(i, is_day, temp, rain=0, wind="5 mph", short="Sunny", detail=""):
    return {"name": f"P{i}", "start": f"2026-11-{15 + i // 2:02d}T{'06' if is_day else '18'}:00:00-06:00",
            "is_day": is_day, "temp_f": temp, "rain_pct": rain, "wind": wind,
            "wind_max_mph": nws._wind_max(wind), "short": short, "detail": detail}


def week(night_low=50, day_high=80, **changes):
    """6+ alternating day/night periods with mild weather; `changes` maps index -> dict of fields."""
    out = [period(i, i % 2 == 0, day_high if i % 2 == 0 else night_low) for i in range(10)]
    for i, fields in changes.items():
        out[int(i[1:])].update(fields)
    return out


def kinds(alerts):
    return {a["kind"]: a for a in alerts}


def test_mild_weather_gives_no_alerts():
    assert nws.farm_alerts(week()) == []
    assert nws.farm_alerts([]) == []


@pytest.mark.parametrize("low,level,title", [
    (28, "danger", "Hard freeze"), (29, "warn", "Freeze"), (32, "warn", "Freeze"),
    (33, "info", "Frost possible"), (36, "info", "Frost possible"), (37, None, None)])
def test_frost_edges(low, level, title):
    a = kinds(nws.farm_alerts(week(night_low=low))).get("frost_freeze")
    if level is None:
        assert a is None
    else:
        assert (a["level"], a["title"]) == (level, title)
        assert a["source"] == "Based on NWS forecast" and a["action"] and f"{low} °F" in a["reason"]


@pytest.mark.parametrize("high,level", [(94, None), (95, "warn"), (99, "warn"), (100, "danger")])
def test_heat_edges(high, level):
    a = kinds(nws.farm_alerts(week(day_high=high))).get("extreme_heat")
    assert (a["level"] if a else None) == level
    if a:
        assert a["title"] == ("Extreme heat" if level == "danger" else "Heat")


@pytest.mark.parametrize("pct,short,level,title", [
    (69, "Rain", None, None), (70, "Rain Showers", "info", "Rain likely"),
    (70, "Chance Thunderstorms", "warn", "Storms likely"), (80, "Heavy Rain", "warn", "Storms likely")])
def test_rain_edges(pct, short, level, title):
    a = kinds(nws.farm_alerts(week(p3={"rain_pct": pct, "short": short}))).get("heavy_rain_storm")
    assert (a["level"], a["title"]) == (level, title) if level else a is None


def test_storm_word_in_detail_counts():
    a = kinds(nws.farm_alerts(week(p2={"rain_pct": 90, "short": "Rain", "detail": "A storm is possible."})))
    assert a["heavy_rain_storm"]["title"] == "Storms likely"


@pytest.mark.parametrize("wind,level", [("19 mph", None), ("20 mph", "info"), ("10 to 29 mph", "info"), ("30 mph", "warn")])
def test_wind_edges(wind, level):
    a = kinds(nws.farm_alerts(week(p1={"wind": wind, "wind_max_mph": nws._wind_max(wind)}))).get("wind_spray")
    assert (a["level"] if a else None) == level
    if a:
        assert "Too windy to spray" in a["action"]


def test_only_the_first_six_periods_count():
    cold_late = week(p7={"temp_f": 20})  # index 7 is the 8th period, outside the window
    assert "frost_freeze" not in kinds(nws.farm_alerts(cold_late))
    cold_early = week(p5={"temp_f": 20})
    assert kinds(nws.farm_alerts(cold_early))["frost_freeze"]["level"] == "danger"


def test_one_alert_per_kind_from_the_worst_period_most_serious_first():
    alerts = nws.farm_alerts(week(p1={"temp_f": 34}, p3={"temp_f": 27}, p0={"temp_f": 101},
                                  p2={"wind": "25 mph", "wind_max_mph": 25}))
    assert [a["kind"] for a in alerts] == ["frost_freeze", "extreme_heat", "wind_spray"]
    assert alerts[0]["reason"] == "P3: 27 °F" and alerts[0]["until"] == week()[3]["start"]
    assert len({a["kind"] for a in alerts}) == len(alerts)


def test_no_night_or_no_day_period():
    days_only = [period(i, True, 101) for i in range(6)]
    assert [a["kind"] for a in nws.farm_alerts(days_only)] == ["extreme_heat"]
    nights_only = [period(i, False, 20) for i in range(6)]
    assert [a["kind"] for a in nws.farm_alerts(nights_only)] == ["frost_freeze"]


# ---------- GET /api/weather ----------

class Upstream:
    def __init__(self, points=200, forecast=200, alerts=200, alerts_body="alerts", forecast_mode=None):
        self.points, self.forecast, self.alerts = points, forecast, alerts
        self.alerts_body, self.forecast_mode = alerts_body, forecast_mode
        self.calls, self.headers = [], []

    def handler(self, request: httpx.Request):
        path = request.url.path
        self.headers.append(dict(request.headers))
        if path.startswith("/points/"):
            self.calls.append("points")
            return httpx.Response(self.points, text=TEXT["points"] if self.points == 200 else '{"title":"x"}')
        if path.startswith("/gridpoints/"):
            self.calls.append("forecast")
            if self.forecast_mode == "timeout":
                raise httpx.ReadTimeout("slow")
            if self.forecast_mode == "junk":
                return httpx.Response(200, text="<html>maintenance</html>")
            return httpx.Response(self.forecast, text=TEXT["forecast"])
        if path == "/alerts/active":
            self.calls.append("alerts")
            return httpx.Response(self.alerts, text=TEXT[self.alerts_body])
        raise AssertionError(path)


@pytest.fixture
def api(tmp_path):
    def build(up, clock=None):
        async def client_override():
            async with httpx.AsyncClient(transport=httpx.MockTransport(up.handler)) as c:
                yield c
        main.app.dependency_overrides[main.get_http_client] = client_override
        main.app.dependency_overrides[main.get_cache] = lambda: DiskCache(tmp_path)
        return TestClient(main.app, raise_server_exceptions=False)
    yield build
    main.app.dependency_overrides.clear()


def test_weather_success_shape(api):
    up = Upstream()
    r = api(up).get("/api/weather", params=FARM)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "National Weather Service"
    assert body["page_url"] == "https://forecast.weather.gov/MapClick.php?lat=30.2336&lon=-97.4960"
    assert body["forecast"]["status"] == "ok" and len(body["forecast"]["periods"]) == 14
    assert body["alerts"]["status"] == "ok" and len(body["alerts"]["official"]) == 2
    assert isinstance(body["alerts"]["farm"], list)
    assert up.calls.index("points") < up.calls.index("forecast")


def test_every_request_has_a_user_agent_and_no_key(api):
    up = Upstream()
    api(up).get("/api/weather", params=FARM)
    for h in up.headers:
        assert h["user-agent"].startswith("FieldShiftHackathon")
        assert not any(k in h for k in ("authorization", "api-key", "x-api-key"))


@pytest.mark.parametrize("params,fragment", [
    ({}, "required"), ({"lat": "abc", "lon": "-97"}, "numbers"), ({"lat": "95", "lon": "-97"}, "out of range"),
    ({"lat": "48.8566", "lon": "2.3522"}, "only covers US farms")])
def test_bad_location_is_400(api, params, fragment):
    up = Upstream()
    r = api(up).get("/api/weather", params=params)
    assert r.status_code == 400 and fragment in r.json()["detail"] and up.calls == []


def test_outside_coverage_marks_both_parts(api):
    # A valid location that the NWS answers with 404 (seen live for points outside its grid).
    r = api(Upstream(points=404)).get("/api/weather", params=FARM)
    assert r.status_code == 200
    body = r.json()
    for part in ("forecast", "alerts"):
        assert body[part]["status"] == "unavailable" and "outside its coverage" in body[part]["reason"]


def test_forecast_down_alerts_still_returned(api):
    body = api(Upstream(forecast_mode="timeout")).get("/api/weather", params=FARM).json()
    assert body["forecast"]["status"] == "unavailable" and "did not respond in time" in body["forecast"]["reason"]
    assert body["alerts"]["status"] == "ok" and len(body["alerts"]["official"]) == 2 and body["alerts"]["farm"] == []


def test_alerts_down_forecast_still_returned(api):
    body = api(Upstream(alerts=503)).get("/api/weather", params=FARM).json()
    assert body["forecast"]["status"] == "ok"
    assert body["alerts"]["status"] == "unavailable" and "(503)" in body["alerts"]["reason"]
    assert body["alerts"]["official"] == []


@pytest.mark.parametrize("mode", ["timeout", "junk"])
def test_never_500(api, mode):
    r = api(Upstream(forecast_mode=mode, alerts=500)).get("/api/weather", params=FARM)
    assert r.status_code == 200
    assert r.json()["forecast"]["status"] == "unavailable"


def test_cache_hit_then_expiry(api, tmp_path, monkeypatch):
    import app.weather_data as wd
    now = [1_000_000.0]
    monkeypatch.setattr(wd.time, "time", lambda: now[0])
    up = Upstream()
    client = api(up)
    first = client.get("/api/weather", params=FARM).json()
    assert first["forecast"]["live_or_cached"] == "live"
    up.calls.clear()
    second = client.get("/api/weather", params=FARM).json()
    assert up.calls == [] and second["forecast"]["live_or_cached"] == "cached"
    now[0] += CACHE_TTL_S + 1
    client.get("/api/weather", params=FARM)
    assert "forecast" in up.calls and "alerts" in up.calls


def test_failed_part_is_not_cached(api, tmp_path):
    api(Upstream(alerts=500)).get("/api/weather", params=FARM)
    names = {p.name.split("_3")[0] for p in tmp_path.glob("*.json")}
    assert "nws_forecast" in names and "nws_alerts" not in names


def test_logs_name_only_the_source_and_error(api, caplog):
    caplog.set_level(logging.WARNING, logger="farm_data")
    api(Upstream(alerts=500)).get("/api/weather", params=FARM)
    lines = [r.getMessage() for r in caplog.records if r.name == "farm_data"]
    assert "farm_data source=nws error=HTTPStatusError" in lines
    assert not any("weather.gov" in line or "30.23" in line for line in lines)
