"""CDL (CropScape) service and Albers projection tests. Network calls use httpx.MockTransport.

Fixtures are real CropScape responses saved on 2026-11-14.
"""
import asyncio
import math
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.projection import make_albers, to_albers
from app.records import RECORD_FIELDS
from app.services import cdl

FX = Path(__file__).parent / "fixtures"
SOY = (FX / "cdl_soybeans.xml").read_text(encoding="utf-8")
WHEAT = (FX / "cdl_winter_wheat.xml").read_text(encoding="utf-8")
NO_DATA = (FX / "cdl_no_data.xml").read_text(encoding="utf-8")
FAULT_YEAR = (FX / "cdl_fault_year.xml").read_text(encoding="utf-8")
FAULT_OUTSIDE = (FX / "cdl_fault_outside.xml").read_text(encoding="utf-8")
TODAY = date(2026, 11, 14)  # so 2026 is "not published yet", 2025..2018 are available


def client_for(per_year, calls=None):
    """per_year(year) returns a body string, an (status, body) tuple, or raises an exception."""
    def handler(request: httpx.Request):
        year = int(request.url.params["year"])
        if calls is not None:
            calls.append(year)
        out = per_year(year)
        if isinstance(out, Exception):
            raise out
        status, body = out if isinstance(out, tuple) else (200, out)
        return httpx.Response(status, text=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def rotation(year):
    """Typical data: 2026 not published, then soybeans and wheat alternating."""
    if year == 2026:
        return (500, FAULT_YEAR)
    return SOY if year % 2 else WHEAT


def run(client, tmp_path):
    cache = DiskCache(tmp_path)

    async def go():
        async with client:
            return await cdl.fetch(client, 40.1, -88.5, cache, today=TODAY)
    return asyncio.run(go())


# ---- projection ----

def test_albers_origin_is_zero():
    x, y = to_albers(23.0, -96.0)
    assert abs(x) < 1e-6 and abs(y) < 1e-6


def test_albers_is_symmetric_about_central_meridian():
    xe, ye = to_albers(40.0, -90.0)
    xw, yw = to_albers(40.0, -102.0)
    assert xe == pytest.approx(-xw) and ye == pytest.approx(yw)
    assert xe > 0 and ye > 0


def test_albers_formula_matches_snyder_worked_example():
    # Snyder (1987) numerical example for the ellipsoidal Albers projection: Clarke 1866
    # ellipsoid, same parallels and origin as EPSG:5070, point 35 N 75 W.
    clarke = make_albers(6378206.4, 0.00676866)
    x, y = clarke(35.0, -75.0)
    assert x == pytest.approx(1885472.7, abs=1.0)
    assert y == pytest.approx(1535925.0, abs=1.0)


# ---- parser ----

def test_parse_value_reads_category():
    assert cdl.parse_value(SOY) == "Soybeans"
    assert cdl.parse_value(WHEAT) == "Winter Wheat"


def test_parse_value_no_data_and_faults():
    assert cdl.parse_value(NO_DATA) is cdl.NO_VALUE
    assert cdl.parse_value(FAULT_YEAR) is cdl.NO_VALUE
    assert cdl.parse_value(FAULT_OUTSIDE) is cdl.NO_VALUE


def test_parse_value_rejects_junk():
    with pytest.raises(ValueError):
        cdl.parse_value("<html>maintenance</html>")
    with pytest.raises(ValueError):
        cdl.parse_value("<Result>{x: 1, y: 2}</Result>")


# ---- service ----

def test_success_returns_eight_years_newest_first(tmp_path):
    records = run(client_for(rotation), tmp_path)
    assert [r["date"] for r in records] == [str(y) for y in range(2025, 2017, -1)]
    assert records[0]["value"] == "Soybeans" and records[1]["value"] == "Winter Wheat"
    for r in records:
        assert set(r) == set(RECORD_FIELDS)
        assert r["variable"] == "crop_type" and r["resolution_m"] == 30
        assert r["source"] == "USDA NASS CDL" and r["live_or_cached"] == "live"


def test_at_least_five_years_when_available(tmp_path):
    # Only 2021..2025 exist.
    def five(year):
        return SOY if 2021 <= year <= 2025 else (500, FAULT_YEAR)
    records = run(client_for(five), tmp_path)
    assert len(records) == 5


def test_year_with_no_value_is_omitted(tmp_path):
    def gap(year):
        return NO_DATA if year == 2023 else rotation(year)
    dates = [r["date"] for r in run(client_for(gap), tmp_path)]
    assert "2023" not in dates and "2024" in dates and "2022" in dates


def test_outside_coverage_gives_empty_list_not_failure(tmp_path):
    records = run(client_for(lambda year: (500, FAULT_OUTSIDE)), tmp_path)
    assert records == []
    assert not list(tmp_path.glob("*.json"))  # empty results are not cached


def test_timeout_on_every_year_raises(tmp_path):
    with pytest.raises(httpx.TimeoutException):
        run(client_for(lambda year: httpx.ReadTimeout("slow")), tmp_path)


def test_timeouts_plus_unpublished_year_is_an_outage_not_empty_history(tmp_path):
    # Seen live: this year's map is a "not published" fault, every other year timed out.
    # That must be reported as unavailable, not as "no crop history here".
    def outage(year):
        return (500, FAULT_YEAR) if year == 2026 else httpx.ReadTimeout("slow")
    with pytest.raises(httpx.TimeoutException):
        run(client_for(outage), tmp_path)
    assert not list(tmp_path.glob("*.json"))


def test_http_error_on_every_year_raises(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(lambda year: (503, "Service Unavailable")), tmp_path)


def test_malformed_on_every_year_raises(tmp_path):
    with pytest.raises(ValueError):
        run(client_for(lambda year: "<html>maintenance</html>"), tmp_path)


def test_some_years_failing_keeps_others_and_is_not_cached(tmp_path):
    def flaky(year):
        return httpx.ReadTimeout("slow") if year in (2024, 2020) else rotation(year)
    dates = [r["date"] for r in run(client_for(flaky), tmp_path)]
    assert "2024" not in dates and "2020" not in dates and "2025" in dates
    assert not list(tmp_path.glob("*.json"))


def test_cache_hit_makes_no_upstream_call(tmp_path):
    first_calls = []
    first = run(client_for(rotation, first_calls), tmp_path)
    assert len(first_calls) == 9
    second_calls = []
    second = run(client_for(rotation, second_calls), tmp_path)
    assert second_calls == []
    assert all(r["live_or_cached"] == "cached" for r in second)
    assert [r["value"] for r in second] == [r["value"] for r in first]


def test_request_sends_albers_coordinates(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.params)
        return httpx.Response(200, text=SOY)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    run(client, tmp_path)
    x, y = to_albers(40.1, -88.5)
    assert math.isclose(float(seen[0]["x"]), x, abs_tol=0.01)
    assert math.isclose(float(seen[0]["y"]), y, abs_tol=0.01)


# ---- retry after a hung request (seen live: random CropScape requests never answer) ----

def test_hung_request_is_retried_once(tmp_path, monkeypatch):
    monkeypatch.setattr(cdl, "ATTEMPT_TIMEOUT", 0.2)
    attempts = {}

    async def handler(request):
        year = int(request.url.params["year"])
        attempts[year] = attempts.get(year, 0) + 1
        if year == 2024 and attempts[year] == 1:
            await asyncio.sleep(2)  # first attempt hangs
        return httpx.Response(200, text=SOY)
    records = run(httpx.AsyncClient(transport=httpx.MockTransport(handler)), tmp_path)
    assert attempts[2024] == 2
    assert "2024" in [r["date"] for r in records]
    assert list(tmp_path.glob("*.json"))  # complete answer after retry, so it is cached


def test_retry_gives_up_after_two_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(cdl, "ATTEMPT_TIMEOUT", 0.1)
    attempts = {}

    async def handler(request):
        year = int(request.url.params["year"])
        attempts[year] = attempts.get(year, 0) + 1
        if year == 2024:
            await asyncio.sleep(2)  # always hangs
        return httpx.Response(200, text=SOY)
    records = run(httpx.AsyncClient(transport=httpx.MockTransport(handler)), tmp_path)
    assert attempts[2024] == 2
    assert "2024" not in [r["date"] for r in records]


def test_worst_case_per_year_stays_within_upstream_limit():
    assert cdl.ATTEMPTS * cdl.ATTEMPT_TIMEOUT <= cdl.UPSTREAM_TIMEOUT
