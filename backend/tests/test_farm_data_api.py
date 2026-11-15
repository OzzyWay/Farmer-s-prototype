"""/api/farm-data endpoint tests. All upstream calls go to httpx.MockTransport; no real network."""
import asyncio
import logging
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.cache import DiskCache
from app.records import RECORD_FIELDS
from app.services import base, cdl

FX = Path(__file__).parent / "fixtures"
BODIES = {
    "nasa_clim": (FX / "nasa_climatology.json").read_text(encoding="utf-8"),
    "nasa_daily": (FX / "nasa_daily.json").read_text(encoding="utf-8"),
    "ssurgo": (FX / "ssurgo_found.json").read_text(encoding="utf-8"),
    "cdl": (FX / "cdl_soybeans.xml").read_text(encoding="utf-8"),
}
FARM = {"lat": "30.233589", "lon": "-97.496006"}


def source_of(request: httpx.Request) -> str:
    host = request.url.host
    if "power.larc.nasa.gov" in host:
        return "nasa_power"
    if "sdmdataaccess" in host:
        return "ssurgo"
    if "nassgeodata" in host:
        return "cdl"
    raise AssertionError(f"unexpected host {host}")


def good_response(request: httpx.Request) -> httpx.Response:
    src = source_of(request)
    if src == "nasa_power":
        key = "nasa_clim" if "climatology" in request.url.path else "nasa_daily"
        return httpx.Response(200, text=BODIES[key])
    return httpx.Response(200, text=BODIES[src])


class Upstream:
    """Mock upstream. `broken` maps a source name to a failure mode; `delay` adds latency."""

    def __init__(self, broken=None, delay=0.0):
        self.broken = broken or {}
        self.delay = delay
        self.calls = []

    async def handler(self, request: httpx.Request):
        src = source_of(request)
        self.calls.append(src)
        if self.delay:
            await asyncio.sleep(self.delay)
        mode = self.broken.get(src)
        if mode == "timeout":
            raise httpx.ReadTimeout("slow")
        if mode == "connect":
            raise httpx.ConnectError("down")
        if mode == "http500":
            return httpx.Response(500, text="Internal Server Error")
        if mode == "junk":
            return httpx.Response(200, text="<html>maintenance</html>")
        if mode == "wrong_json":
            return httpx.Response(200, text='{"surprise": true}')
        if mode == "crash":
            raise RuntimeError("unexpected bug in transport")
        if mode == "hang":
            await asyncio.sleep(5)
        return good_response(request)


@pytest.fixture
def api(tmp_path):
    """Returns a function that builds a TestClient wired to a given Upstream and a temp cache."""
    def build(upstream: Upstream):
        async def client_override():
            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as c:
                yield c
        main.app.dependency_overrides[main.get_http_client] = client_override
        main.app.dependency_overrides[main.get_cache] = lambda: DiskCache(tmp_path)
        return TestClient(main.app, raise_server_exceptions=False)
    yield build
    main.app.dependency_overrides.clear()


def all_records(body):
    return [r for s in body["sources"].values() if s["status"] == "ok" for r in s["records"]]


# ---- success and shape ----

def test_success_grouped_by_source(api):
    r = api(Upstream()).get("/api/farm-data", params=FARM)
    assert r.status_code == 200
    body = r.json()
    assert body["location"] == {"lat": 30.233589, "lon": -97.496006}
    assert set(body["sources"]) == {"nasa_power", "ssurgo", "cdl"}
    for key, group in body["sources"].items():
        assert group["status"] == "ok", key
        assert group["records"], key
    assert {r["source"] for r in body["sources"]["cdl"]["records"]} == {"USDA NASS CDL"}
    assert len(body["sources"]["cdl"]["records"]) == 8


def test_every_record_has_all_seven_fields(api):
    body = api(Upstream()).get("/api/farm-data", params=FARM).json()
    records = all_records(body)
    assert len(records) > 50
    for rec in records:
        assert set(rec) == set(RECORD_FIELDS)
        assert rec["live_or_cached"] in ("live", "cached")


def test_second_request_is_served_from_cache(api):
    up = Upstream()
    client = api(up)
    first = client.get("/api/farm-data", params=FARM).json()
    assert {r["live_or_cached"] for r in all_records(first)} == {"live"}
    up.calls.clear()
    # Same point again: everything from the cache.
    same = client.get("/api/farm-data", params=FARM).json()
    assert up.calls == []
    assert {r["live_or_cached"] for r in all_records(same)} == {"cached"}
    assert [r["value"] for r in all_records(same)] == [r["value"] for r in all_records(first)]
    # A point about 60 m away: climate and soil share the 1 km cache cell, but the 30 m crop
    # map is asked again, because a neighbouring square can be a different crop.
    second = client.get("/api/farm-data", params={"lat": "30.2331", "lon": "-97.4959"}).json()
    assert set(up.calls) == {"cdl"}
    assert {r["live_or_cached"] for r in second["sources"]["nasa_power"]["records"]} == {"cached"}
    assert {r["live_or_cached"] for r in second["sources"]["cdl"]["records"]} == {"live"}


# ---- partial and total failure ----

def test_one_source_down_others_still_returned(api):
    body = api(Upstream(broken={"ssurgo": "http500"})).get("/api/farm-data", params=FARM).json()
    assert body["sources"]["ssurgo"] == {
        "status": "unavailable", "source": "USDA SSURGO", "reason": "USDA SSURGO returned an error (500)"}
    assert body["sources"]["nasa_power"]["status"] == "ok"
    assert body["sources"]["cdl"]["status"] == "ok"


def test_all_sources_down_still_200(api):
    up = Upstream(broken={"nasa_power": "timeout", "ssurgo": "timeout", "cdl": "timeout"})
    r = api(up).get("/api/farm-data", params=FARM)
    assert r.status_code == 200
    for key, group in r.json()["sources"].items():
        assert group["status"] == "unavailable", key
        assert "did not respond in time" in group["reason"]


@pytest.mark.parametrize("mode", ["timeout", "connect", "http500", "junk", "wrong_json", "crash"])
def test_never_500_whatever_upstream_does(api, mode):
    up = Upstream(broken={"nasa_power": mode, "ssurgo": mode, "cdl": mode})
    r = api(up).get("/api/farm-data", params=FARM)
    assert r.status_code == 200, r.text
    for group in r.json()["sources"].values():
        assert group["status"] in ("ok", "unavailable")
        if group["status"] == "unavailable":
            assert group["reason"] and "http" not in group["reason"].lower()


def test_failures_are_not_cached(api, tmp_path):
    api(Upstream(broken={"ssurgo": "junk"})).get("/api/farm-data", params=FARM)
    names = sorted(p.name.split("_")[0] for p in tmp_path.glob("*.json"))
    assert "ssurgo" not in names and "cdl" in names and "nasa" in names


def test_failure_is_logged_with_source_and_error_type_only(api, caplog):
    caplog.set_level(logging.WARNING, logger="farm_data")
    api(Upstream(broken={"ssurgo": "http500"})).get("/api/farm-data", params=FARM)
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "farm_data"]
    assert "farm_data source=ssurgo error=HTTPStatusError" in lines
    assert not any("sdmdataaccess" in line or "http://" in line or "https://" in line for line in lines)


# ---- timing ----

def test_sources_run_concurrently(api):
    delay = 0.5
    up = Upstream(delay=delay)
    start = time.perf_counter()
    r = api(up).get("/api/farm-data", params=FARM)
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    # Run one after another, the three sources would take at least 3 x delay.
    assert elapsed < 2 * delay, f"took {elapsed:.2f}s"


def test_hanging_source_is_cut_off_by_the_upstream_timeout(api, monkeypatch):
    monkeypatch.setattr(base, "UPSTREAM_TIMEOUT", 0.3)
    monkeypatch.setattr(cdl, "ATTEMPT_TIMEOUT", 0.15)
    up = Upstream(broken={"ssurgo": "hang"})
    start = time.perf_counter()
    body = api(up).get("/api/farm-data", params=FARM).json()
    assert time.perf_counter() - start < 3
    assert body["sources"]["ssurgo"]["status"] == "unavailable"
    assert "did not respond in time" in body["sources"]["ssurgo"]["reason"]
    assert body["sources"]["cdl"]["status"] == "ok"


# ---- validation ----

@pytest.mark.parametrize("params,fragment", [
    ({}, "required"),
    ({"lat": "30.2"}, "required"),
    ({"lat": "abc", "lon": "-97.5"}, "numbers"),
    ({"lat": "95", "lon": "-97.5"}, "out of range"),
    ({"lat": "30.2", "lon": "-190"}, "out of range"),
    ({"lat": "48.8566", "lon": "2.3522"}, "only covers US farms"),
])
def test_invalid_location_is_400_and_makes_no_upstream_call(api, params, fragment):
    up = Upstream()
    r = api(up).get("/api/farm-data", params=params)
    assert r.status_code == 400
    assert fragment in r.json()["detail"]
    assert up.calls == []
