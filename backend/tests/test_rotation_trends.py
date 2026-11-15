"""Trend method tests (Req 14.9) and the climate trends service (Req 17), offline."""
import asyncio
import json
import random
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.rotation.trends import mann_kendall_p, theil_sen_slope, trend
from app.services import climate_trends
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures"
POWER = (FX / "power_daily_webberwood.json").read_text(encoding="utf-8")
TODAY = date(2026, 11, 14)
YEARS = list(range(1981, 2026))


# ---- the method ----

def test_known_slope_is_recovered_within_5_percent():
    rng = random.Random(7)
    series = {y: 50 + 1.2 * (y - 1981) + rng.uniform(-3, 3) for y in YEARS}
    t = trend(series)
    assert t["method"] == "theil_sen" and t["clear"] is True
    assert t["per_decade"] == pytest.approx(12.0, rel=0.05)


def test_flat_noise_is_not_a_clear_change():
    rng = random.Random(3)
    series = {y: 800 + rng.gauss(0, 120) for y in YEARS}
    t = trend(series)
    assert t["clear"] is False and t["p_value"] >= 0.05


def test_one_extreme_year_barely_moves_the_slope():
    base = {y: 2.0 * (y - 1981) for y in YEARS}
    spiked = {**base, 2011: 500.0}
    assert theil_sen_slope(YEARS, [spiked[y] for y in YEARS]) == pytest.approx(2.0, abs=0.1)


def test_missing_years_are_handled():
    series = {y: 3.0 * (y - 1981) for y in YEARS if y % 4}  # every 4th year missing
    t = trend(series)
    assert t["per_decade"] == pytest.approx(30.0) and t["n_years"] == len(series)


def test_rare_events_compare_first_and_last_15_years():
    series = {y: 0 for y in YEARS}
    for y in (2012, 2015, 2018, 2021, 2024, 2025):
        series[y] = 1
    series[1983] = 1
    t = trend(series)
    assert t["method"] == "first_last_15" and t["per_decade"] is None
    # last 15 years (2011-2025) have 6 heavy-rain years, the first 15 (1981-1995) have 1
    assert t["change"] == pytest.approx(6 / 15 - 1 / 15, abs=0.01)


def test_too_few_years():
    t = trend({2020: 1, 2021: 2, 2022: 3})
    assert t["method"] == "not_enough_years" and t["clear"] is False


def test_mann_kendall_matches_hand_computed_values():
    # [1,2,3,4,5]: S = 10, var = 5*4*15/18, z = 9/sqrt(var) = 2.2045, p = 0.0275
    assert mann_kendall_p([1, 2, 3, 4, 5]) == pytest.approx(0.0275, abs=0.0005)
    # ties [1,1,2,2]: S = 4, var = (156 - 36)/18, z = 3/sqrt(var) = 1.162, p = 0.245
    assert mann_kendall_p([1, 1, 2, 2]) == pytest.approx(0.245, abs=0.002)
    assert mann_kendall_p([5, 5, 5, 5]) == 1.0


def test_first_and_last_decade_averages():
    t = trend({y: (10 if y < 1991 else 30 if y > 2015 else 20) for y in YEARS})
    assert t["first_decade_avg"] == 10 and t["last_decade_avg"] == 30


# ---- the real Webberwood data (NASA POWER 1981-2025) ----

@pytest.fixture(scope="module")
def webberwood():
    return climate_trends.summarize(json.loads(POWER), 2025)


def by_id(summary):
    return {i["id"]: i for i in summary["indicators"]}


def test_webberwood_hot_days_rising_about_10_per_decade(webberwood):
    hot = by_id(webberwood)["hot_days"]
    assert hot["clear"] is True and hot["per_decade"] == pytest.approx(10, abs=1)
    assert hot["first_decade_avg"] == pytest.approx(64.4, abs=0.1)
    assert hot["last_decade_avg"] == pytest.approx(90.8, abs=0.1)


def test_webberwood_warm_nights_and_frost_clear_rain_not(webberwood):
    items = by_id(webberwood)
    assert items["warm_nights"]["clear"] and items["warm_nights"]["per_decade"] > 0
    assert items["frost_days"]["clear"] and items["frost_days"]["per_decade"] < 0
    assert items["rain_total"]["clear"] is False


def test_webberwood_summary_shape(webberwood):
    assert webberwood["period"] == "1981-2025" and webberwood["recent_period"] == "2016-2025"
    assert webberwood["source"] == "NASA POWER" and webberwood["resolution_m"] == 50000
    assert set(by_id(webberwood)) == set(climate_trends.ind.INDICATORS)
    assert 20 <= webberwood["heavy_rain_threshold_mm"] <= 80
    assert "over" in by_id(webberwood)["heavy_rain_days"]["label"]
    assert len(webberwood["monthly"]["avg_high_c"]) == 12
    hot = by_id(webberwood)["hot_days"]
    assert hot["recent_avg"] == pytest.approx(90.8, abs=0.1)
    assert hot["baseline_avg"] == pytest.approx(70.2, abs=0.1)


# ---- the service ----

def client_for(body=POWER, status=200, error=None, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        if error:
            raise error
        return httpx.Response(status, text=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(client, tmp_path):
    cache = DiskCache(tmp_path)

    async def go():
        async with client:
            return await climate_trends.fetch(client, 30.233589, -97.496006, cache, today=TODAY)
    return asyncio.run(go())


def test_service_requests_1981_to_last_complete_year(tmp_path):
    calls = []
    s = run(client_for(calls=calls), tmp_path)
    params = calls[0].url.params
    assert params["start"] == "19810101" and params["end"] == "20251231"
    assert params["parameters"] == "T2M_MIN,T2M_MAX,PRECTOTCORR,GWETROOT,EVLAND"
    assert s["live_or_cached"] == "live"


def test_service_caches_the_summary_by_year(tmp_path):
    run(client_for(), tmp_path)
    assert (tmp_path / "climate_trends_2025_30.23_-97.50.json").exists()
    calls = []
    s = run(client_for(calls=calls), tmp_path)
    assert calls == [] and s["live_or_cached"] == "cached"


def test_service_timeout_http_error_and_malformed(tmp_path):
    with pytest.raises(httpx.TimeoutException):
        run(client_for(error=httpx.ReadTimeout("slow")), tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(body="boom", status=500), tmp_path)
    with pytest.raises(SourceUnavailable, match="could not read"):
        run(client_for(body='{"nope": 1}'), tmp_path)
    with pytest.raises(SourceUnavailable, match="no daily climate data"):
        run(client_for(body='{"properties": {"parameter": {"T2M_MAX": {}}}}'), tmp_path)
    assert not list(tmp_path.glob("*.json"))
