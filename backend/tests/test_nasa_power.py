"""NASA POWER service tests. All network calls are replaced by httpx.MockTransport."""
import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.records import RECORD_FIELDS
from app.services import nasa_power
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures"
CLIM = json.loads((FX / "nasa_climatology.json").read_text(encoding="utf-8"))
DAILY = json.loads((FX / "nasa_daily.json").read_text(encoding="utf-8"))
TODAY = date(2026, 11, 14)


def client_for(clim=None, daily=None, clim_status=200, daily_status=200, calls=None):
    """Mock client: serves the fixtures (or the given overrides) and counts calls."""
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append(request.url.path)
        if "climatology" in request.url.path:
            if isinstance(clim, Exception):
                raise clim
            return httpx.Response(clim_status, content=clim if isinstance(clim, bytes) else json.dumps(clim or CLIM))
        if isinstance(daily, Exception):
            raise daily
        return httpx.Response(daily_status, content=daily if isinstance(daily, bytes) else json.dumps(daily or DAILY))
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(client, tmp_path):
    cache = DiskCache(tmp_path)

    async def go():
        async with client:
            return await nasa_power.fetch(client, 30.2752, -98.872, cache, today=TODAY)
    return asyncio.run(go())


def by_variable(records):
    out = {}
    for r in records:
        out.setdefault(r["variable"], []).append(r)
    return out


def test_success_has_all_expected_records(tmp_path):
    records = run(client_for(), tmp_path)
    v = by_variable(records)
    for name in ("temperature_mean", "temperature_min", "temperature_max", "precipitation", "solar_radiation"):
        assert len(v[name]) == 12, name
    for name in ("frost_days_per_year", "last_spring_frost", "first_fall_frost", "heat_days_per_year"):
        assert len(v[name]) == 1, name
    for r in records:
        assert set(r) == set(RECORD_FIELDS)
        assert r["resolution_m"] == 50000 and r["source"] == "NASA POWER"
        assert r["live_or_cached"] == "live"


def test_units_and_conversions(tmp_path):
    v = by_variable(run(client_for(), tmp_path))
    assert {r["units"] for r in v["temperature_mean"]} == {"°C"}
    assert v["precipitation"][0]["units"] == "mm"
    # January: 1.59 mm/day * 31 days
    assert v["precipitation"][0]["value"] == pytest.approx(49.3, abs=0.1)
    # January sun: 11.39 MJ/m2/day -> 3.16 kWh/m2/day
    assert v["solar_radiation"][0]["units"] == "kWh/m²/day"
    assert v["solar_radiation"][0]["value"] == pytest.approx(3.16, abs=0.01)
    assert v["frost_days_per_year"][0]["units"] == "days/year"
    assert v["frost_days_per_year"][0]["date"] == "2023-2025"
    # average daily low is warmer than the all-time extreme low in the climatology file
    assert v["temperature_min"][0]["value"] > -7.84
    assert v["temperature_min"][0]["value"] < v["temperature_mean"][0]["value"] < v["temperature_max"][0]["value"]


def test_months_are_numbered_01_to_12(tmp_path):
    v = by_variable(run(client_for(), tmp_path))
    assert [r["date"] for r in v["temperature_mean"]] == [f"{i:02d}" for i in range(1, 13)]


def test_solar_omitted_when_absent(tmp_path):
    clim = json.loads(json.dumps(CLIM))
    del clim["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
    assert "solar_radiation" not in by_variable(run(client_for(clim=clim), tmp_path))


def test_timeout(tmp_path):
    with pytest.raises(httpx.TimeoutException):
        run(client_for(clim=httpx.ReadTimeout("slow")), tmp_path)


def test_http_error(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(clim_status=500), tmp_path)


def test_malformed_response(tmp_path):
    with pytest.raises(ValueError):  # invalid JSON
        run(client_for(clim=b"<html>oops"), tmp_path)
    with pytest.raises(SourceUnavailable):  # JSON without the expected keys
        run(client_for(clim={"unexpected": True}), tmp_path)


def test_empty_result_when_all_values_are_fill(tmp_path):
    clim = json.loads(json.dumps(CLIM))
    for m in nasa_power.MONTHS:
        clim["properties"]["parameter"]["T2M"][m] = -999
    with pytest.raises(SourceUnavailable, match="no climate data"):
        run(client_for(clim=clim), tmp_path)


def test_daily_failure_keeps_monthly_records_and_is_not_cached(tmp_path):
    records = run(client_for(daily=httpx.ReadTimeout("slow")), tmp_path)
    v = by_variable(records)
    assert len(v["temperature_mean"]) == 12 and len(v["precipitation"]) == 12
    for name in ("temperature_min", "temperature_max", "frost_days_per_year", "heat_days_per_year"):
        assert name not in v
    assert not list(tmp_path.glob("*.json"))  # reduced result is not cached


def test_daily_malformed_keeps_monthly_records(tmp_path):
    v = by_variable(run(client_for(daily={"nope": 1}), tmp_path))
    assert len(v["temperature_mean"]) == 12 and "frost_days_per_year" not in v


def test_cache_hit_makes_no_upstream_call(tmp_path):
    first_calls = []
    first = run(client_for(calls=first_calls), tmp_path)
    assert len(first_calls) == 2
    second_calls = []
    second = run(client_for(calls=second_calls), tmp_path)
    assert second_calls == []
    assert all(r["live_or_cached"] == "cached" for r in second)
    assert [r["value"] for r in second] == [r["value"] for r in first]


def test_failure_does_not_touch_existing_cache(tmp_path):
    run(client_for(), tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    # cached entry is served, so a broken upstream is never even called; simulate a miss elsewhere
    other = DiskCache(tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_fetch_at(client_for(clim_status=500), other, 31.0, -97.0))
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.json")} == before


async def _fetch_at(client, cache, lat, lon):
    async with client:
        return await nasa_power.fetch(client, lat, lon, cache, today=TODAY)


# ---- estimate_frost_heat on small hand-made series ----

def year_series(year, tmin_fn, value_default=10.0):
    """Build a full year of daily values; tmin_fn(date) may override the default."""
    from datetime import timedelta
    d = date(year, 1, 1)
    out = {}
    while d.year == year:
        out[d.strftime("%Y%m%d")] = tmin_fn(d, value_default)
        d += timedelta(days=1)
    return out


def test_estimate_counts_frost_and_dates():
    def frosty(d, default):
        if d in (date(2020, 1, 10), date(2020, 3, 20), date(2020, 11, 5), date(2020, 12, 1)):
            return -2.0
        return default
    est = nasa_power.estimate_frost_heat(year_series(2020, frosty), year_series(2020, lambda d, x: 20.0))
    assert est["frost_days"] == 4
    assert est["last_spring_frost"] == "03-20"
    assert est["first_fall_frost"] == "11-05"
    assert est["heat_days"] == 0
    assert est["period"] == "2020-2020"


def test_estimate_no_frost_year_omits_dates():
    est = nasa_power.estimate_frost_heat(year_series(2021, lambda d, x: 8.0), year_series(2021, lambda d, x: 20.0))
    assert est["frost_days"] == 0
    assert est["last_spring_frost"] is None and est["first_fall_frost"] is None


def test_estimate_heat_days_use_threshold_above_35():
    def hot(d, default):
        return 36.0 if d.month == 7 and d.day <= 10 else (35.0 if d.month == 8 else 25.0)
    est = nasa_power.estimate_frost_heat(year_series(2022, lambda d, x: 8.0), year_series(2022, hot))
    assert est["heat_days"] == 10  # exactly 35.0 does not count


def test_estimate_ignores_fill_values_and_sparse_years():
    series = year_series(2020, lambda d, x: 8.0)
    sparse = {k: (-999 if int(k[4:6]) > 2 else v) for k, v in series.items()}  # most days missing
    est = nasa_power.estimate_frost_heat(sparse, sparse)
    assert est["frost_days"] is None and est["heat_days"] is None


def test_estimate_averages_across_years():
    def frost_n(n):
        def f(d, default):
            return -1.0 if d.month == 1 and d.day <= n else default
        return f
    mins = {**year_series(2020, frost_n(2)), **year_series(2021, frost_n(4))}
    est = nasa_power.estimate_frost_heat(mins, {})
    assert est["frost_days"] == 3.0
    assert est["heat_days"] is None
