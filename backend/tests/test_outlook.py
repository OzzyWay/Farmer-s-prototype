"""Open-Meteo outlook tests: delta method, cost, budget guard, 429s, lookup order, loader.

Fixtures are the real Open-Meteo Climate API responses for Webberwood saved on 2026-11-15.
No test sleeps for real or touches the network.
"""
import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.outlook_store import OutlookStore, cell
from app.services import openmeteo
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures"
RECENT_TEXT = (FX / "openmeteo_recent_webberwood.json").read_text(encoding="utf-8")
FUTURE_TEXT = (FX / "openmeteo_future_webberwood.json").read_text(encoding="utf-8")
RECENT, FUTURE = json.loads(RECENT_TEXT), json.loads(FUTURE_TEXT)
LAT, LON = 30.233589, -97.496006
TODAY = date(2026, 11, 15)


def by_id(doc):
    return {i["id"]: i for i in doc["indicators"]}


# ---- delta method ----

@pytest.fixture(scope="module")
def outlook():
    return openmeteo.build_outlook(RECENT, FUTURE, "2026-11-15", LAT, LON)


def test_hot_day_changes_across_the_three_models(outlook):
    change = by_id(outlook)["hot_days"]["change"]
    assert change == {"low": pytest.approx(25.7, abs=0.1), "mid": pytest.approx(28.2, abs=0.1),
                      "high": pytest.approx(38.7, abs=0.1)}
    assert outlook["models"] == list(openmeteo.MODELS)


def test_outlook_metadata_and_indicators(outlook):
    assert outlook["recent"] == "1991-2020" and outlook["future"] == "2030-2049"
    assert "CC BY 4.0" in outlook["licence"] and "RCP8.5" in outlook["scenario"]
    items = by_id(outlook)
    assert set(items) <= set(openmeteo.OUTLOOK_INDICATORS)
    assert "water_balance" not in items and "soil_wetness" not in items
    assert items["frost_days"]["change"]["mid"] < 0       # fewer frosts
    assert items["last_spring_frost"]["change"]["mid"] < 0  # last frost earlier in spring
    for item in items.values():
        c = item["change"]
        assert c["low"] <= c["mid"] <= c["high"] and item["n_models"] == 3


def test_each_model_change_is_its_own_future_minus_recent(outlook):
    for m in outlook["per_model"].values():
        assert m["change"]["hot_days"] == pytest.approx(m["future"]["hot_days"] - m["recent"]["hot_days"], abs=0.01)


def test_future_values_add_the_change_to_the_nasa_baseline(outlook):
    trends = {"indicators": [{"id": "hot_days", "baseline_avg": 70.2}]}
    hot = by_id(openmeteo.apply_to_baseline(outlook, trends))["hot_days"]
    assert hot["baseline_avg"] == 70.2
    assert hot["future_value"]["mid"] == pytest.approx(70.2 + 28.2, abs=0.1)
    assert "future_value" not in by_id(openmeteo.apply_to_baseline(outlook, None))["hot_days"]


def test_too_few_models_is_unavailable():
    broken = json.loads(RECENT_TEXT)
    for key in list(broken["daily"]):
        if key != "time" and not key.endswith("EC_Earth3P_HR"):
            broken["daily"][key] = [None] * len(broken["daily"]["time"])
    with pytest.raises(SourceUnavailable, match="too few"):
        openmeteo.build_outlook(broken, FUTURE, "2026-11-15", LAT, LON)


def test_malformed_response():
    with pytest.raises(SourceUnavailable, match="could not read"):
        openmeteo.build_outlook({"nope": 1}, FUTURE, "2026-11-15", LAT, LON)


# ---- cost and budget ----

def test_request_weight_matches_open_meteo_rule():
    assert openmeteo.request_weight("1991-01-01", "2020-12-31") == pytest.approx(10958 / 14 * 3)
    assert openmeteo.request_weight("2030-01-01", "2049-12-31") == pytest.approx(7305 / 14 * 3)
    assert openmeteo.location_cost() == pytest.approx(3913, abs=1)
    assert openmeteo.request_weight("2030-01-01", "2030-01-02", n_models=1) == 1  # 14-day minimum


def test_budget_counts_per_hour_and_day(tmp_path):
    b = openmeteo.Budget(tmp_path / "b.json", hour_limit=4500, day_limit=9000)
    t1 = datetime(2026, 11, 15, 10, 5, tzinfo=timezone.utc)
    assert b.can_spend(3913, t1)
    b.spend(3913, t1)
    assert not b.can_spend(3913, t1)                                         # same hour: over 4,500
    t2 = datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)
    assert b.can_spend(3913, t2)                                             # new hour
    b.spend(3913, t2)
    t3 = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    assert not b.can_spend(3913, t3)                                         # day total would pass 9,000
    assert b.can_spend(3913, datetime(2026, 11, 16, 0, 1, tzinfo=timezone.utc))  # next day resets


# ---- fetching ----

class FakeOpenMeteo:
    def __init__(self, status=200, error=None):
        self.calls, self.status, self.error = [], status, error

    def handler(self, request):
        self.calls.append(dict(request.url.params))
        if self.error:
            raise self.error
        if self.status != 200:
            return httpx.Response(self.status, json={"reason": "limit", "error": True})
        start = request.url.params["start_date"]
        return httpx.Response(200, text=RECENT_TEXT if start.startswith("1991") else FUTURE_TEXT)


def fetch(fake, budget, sleeps):
    async def fake_sleep(s):
        sleeps.append(s)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            return await openmeteo.fetch_outlook(c, LAT, LON, budget=budget, sleep=fake_sleep, today=TODAY)
    return asyncio.run(go())


def test_fetch_sends_two_requests_65_seconds_apart(tmp_path):
    fake, sleeps = FakeOpenMeteo(), []
    doc = fetch(fake, openmeteo.Budget(tmp_path / "b.json"), sleeps)
    assert [c["start_date"] for c in fake.calls] == ["1991-01-01", "2030-01-01"]
    assert fake.calls[0]["models"] == ",".join(openmeteo.MODELS)
    assert sleeps == [65]
    assert doc["fetched_on"] == "2026-11-15"


def test_fetch_is_refused_when_the_budget_is_spent(tmp_path):
    budget = openmeteo.Budget(tmp_path / "b.json")
    budget.spend(4000)
    fake = FakeOpenMeteo()
    with pytest.raises(SourceUnavailable, match="limit"):
        fetch(fake, budget, [])
    assert fake.calls == []


def test_429_becomes_a_plain_limit_message(tmp_path):
    with pytest.raises(SourceUnavailable, match="free climate-outlook limit"):
        fetch(FakeOpenMeteo(status=429), openmeteo.Budget(tmp_path / "b.json"), [])


def test_other_http_errors_and_timeouts_are_raised(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        fetch(FakeOpenMeteo(status=500), openmeteo.Budget(tmp_path / "b1.json"), [])
    with pytest.raises(httpx.TimeoutException):
        fetch(FakeOpenMeteo(error=httpx.ReadTimeout("slow")), openmeteo.Budget(tmp_path / "b2.json"), [])


# ---- lookup order and loader ----

def make_store(tmp_path, farms=None, precomputed=None, budget_calls=0):
    farms_file = tmp_path / "demo_farms.json"
    farms_file.write_text(json.dumps({"farms": farms or [{"id": "webberwood", "name": "W", "lat": LAT, "lon": LON}]}), encoding="utf-8")
    pre_dir = tmp_path / "outlooks"
    pre_dir.mkdir()
    if precomputed:
        (pre_dir / "webberwood.json").write_text(json.dumps(precomputed), encoding="utf-8")
    budget = openmeteo.Budget(tmp_path / "budget.json")
    if budget_calls:
        budget.spend(budget_calls)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
    store = OutlookStore(DiskCache(tmp_path / "cache"), pre_dir, farms_file, budget=budget, sleep=fake_sleep)
    return store, sleeps


def test_precomputed_file_is_used_inside_the_farm_box(tmp_path, outlook):
    store, _ = make_store(tmp_path, precomputed=outlook)
    got = store.get(LAT + 0.002, LON - 0.002, TODAY)
    assert got["origin"] == "precomputed" and got["farm_id"] == "webberwood"
    assert store.get(LAT + 0.02, LON, TODAY) is None  # 2 km away: outside the box
    assert store.status(LAT, LON, TODAY) == {"status": "ready"}


def test_not_loaded_without_file_or_cache(tmp_path):
    store, _ = make_store(tmp_path)
    assert store.status(LAT, LON, TODAY)["status"] == "not_loaded"


def run_load(store, fake, lat=LAT, lon=LON):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            return await store.load(c, lat, lon, today=TODAY)
    return asyncio.run(go())


def test_on_demand_load_caches_by_grid_cell(tmp_path):
    store, sleeps = make_store(tmp_path)
    assert store.can_start(LAT, LON, TODAY)["status"] == "loading"
    result = run_load(store, FakeOpenMeteo())
    assert result == {"status": "ready"} and sleeps == [65]
    assert cell(LAT, LON) == (30.2, -97.5)
    nearby = store.get(30.24, -97.46, TODAY)  # same 0.1° cell, a few km away
    assert nearby["origin"] == "cached" and nearby["live_or_cached"] == "cached"


def test_cached_outlook_expires_after_30_days(tmp_path):
    store, _ = make_store(tmp_path)
    run_load(store, FakeOpenMeteo())
    assert store.get(LAT, LON, date(2026, 12, 15)) is not None   # 30 days
    assert store.get(LAT, LON, date(2026, 12, 16)) is None       # 31 days


def test_failed_load_is_remembered_with_its_reason(tmp_path):
    store, _ = make_store(tmp_path)
    result = run_load(store, FakeOpenMeteo(status=429))
    assert result["status"] == "unavailable" and "limit" in result["reason"]
    assert store.status(LAT, LON, TODAY)["status"] == "unavailable"
    assert not list((tmp_path / "cache").glob("outlook_*.json")) if (tmp_path / "cache").exists() else True


def test_load_refused_when_budget_spent(tmp_path):
    store, _ = make_store(tmp_path, budget_calls=4000)
    check = store.can_start(LAT, LON, TODAY)
    assert check["status"] == "unavailable" and "limit" in check["reason"]


def test_only_one_load_at_a_time(tmp_path):
    store, _ = make_store(tmp_path)
    store.loading[(31.0, -98.0)] = store.clock()
    check = store.can_start(LAT, LON, TODAY)
    assert check["status"] == "unavailable" and "another" in check["reason"]
    assert store.status(31.0, -98.0, TODAY)["status"] == "loading"


def test_real_demo_farm_file_is_valid():
    path = Path(__file__).resolve().parents[2] / "config" / "outlooks" / "webberwood.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["status"] == "ok" and doc["farm_id"] == "webberwood"
    assert by_id(doc)["hot_days"]["change"]["mid"] == pytest.approx(28.2, abs=0.1)
    assert doc["fetched_on"] == "2026-11-15" and "CC BY 4.0" in doc["licence"]


def test_monthly_change_in_average_high(outlook):
    monthly = outlook["monthly"]["tmax_change_c_mid"]
    assert len(monthly) == 12 and all(v is not None for v in monthly)
    assert all(0 < v < 5 for v in monthly)  # every month warms by a plausible amount
    for m in outlook["per_model"].values():
        assert len(m["monthly_tmax_change_c"]) == 12
