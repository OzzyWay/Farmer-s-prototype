"""MODIS NDVI tests: parsing, quality filtering, monthly summary, the bare-month rule,
fetching in 10-date chunks, failures, the demo-farm lookup and the rotation wiring.

The fixtures in fixtures/raw_ndvi/ are real ORNL DAAC responses for Webberwood (2026-11-15).
No test touches the network.
"""
import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app import ndvi_store
from app.rotation_data import apply_ndvi
from app.services import ndvi
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures" / "raw_ndvi"
NDVI_DOC = json.loads((FX / f"subset_{ndvi.NDVI_BAND}.json").read_text(encoding="utf-8"))
QA_DOC = json.loads((FX / f"subset_{ndvi.QA_BAND}.json").read_text(encoding="utf-8"))
DATES = json.loads((FX / "dates.json").read_text(encoding="utf-8"))["dates"]
LAT, LON = 30.233589, -97.496006


# ---- parsing and quality ----

def test_parse_real_subset():
    values = ndvi.parse_subset(NDVI_DOC)
    assert len(values) == 10
    assert values["2026-05-25"] == 6960


def test_parse_rejects_junk():
    with pytest.raises(SourceUnavailable, match="could not read"):
        ndvi.parse_subset({"oops": True})


def test_combine_scales_and_keeps_good_and_marginal():
    series = ndvi.combine(ndvi.parse_subset(NDVI_DOC), ndvi.parse_subset(QA_DOC))
    assert len(series) == 10
    assert series[0] == {"date": "2026-05-25", "ndvi": 0.696, "quality": "good"}
    assert series[1]["quality"] == "marginal"


def test_combine_drops_cloud_snow_and_fill():
    raw = {"2024-01-01": 5000, "2024-01-17": 5000, "2024-02-02": 5000, "2024-02-18": -3000, "2024-03-05": 5000}
    qa = {"2024-01-01": 3, "2024-01-17": 2, "2024-02-02": -1, "2024-02-18": 0}  # 03-05 has no QA at all
    assert ndvi.combine(raw, qa) == []


# ---- monthly summary and the bare rule ----

def point(day, value):
    return {"date": day, "ndvi": value, "quality": "good"}


def test_bare_month_uses_the_highest_value_in_the_month():
    # January 2023: one hazy low value and one green value -> not bare.
    # January 2024 and 2025: all low -> bare. So 2 of 3 years bare.
    series = [point("2023-01-01", 0.12), point("2023-01-17", 0.45),
              point("2024-01-01", 0.15), point("2024-01-17", 0.20),
              point("2025-01-01", 0.18)]
    jan = ndvi.monthly_summary(series)[0]
    assert jan == {"month": 1, "typical_ndvi": 0.18, "years_seen": 3, "bare_years": 2, "bare_share": 0.67}


def test_threshold_edge_is_not_bare():
    jan = ndvi.monthly_summary([point("2024-01-01", ndvi.BARE_NDVI)])[0]
    assert jan["bare_years"] == 0


def test_month_with_no_good_values():
    months = ndvi.monthly_summary([point("2024-06-10", 0.7)])
    assert months[0] == {"month": 1, "typical_ndvi": None, "years_seen": 0, "bare_years": 0, "bare_share": None}
    assert months[5]["typical_ndvi"] == 0.7


def test_build_doc_lists_months_bare_in_at_least_half_the_years():
    series = [point(f"{y}-08-01", 0.2) for y in (2023, 2024)] + [point("2025-08-01", 0.6), point("2024-05-01", 0.7)]
    doc = ndvi.build_doc(series, "2023-01-01", "2025-12-31", LAT, LON, "2026-11-15")
    assert doc["bare_months"] == [8]
    assert doc["period"] == "2023-2025" and doc["resolution_m"] == 250 and doc["status"] == "ok"
    assert "0.25" in doc["method"]


def test_build_doc_without_good_values_is_unavailable():
    with pytest.raises(SourceUnavailable, match="no good-quality"):
        ndvi.build_doc([], "2023-01-01", "2025-12-31", LAT, LON, "2026-11-15")


# ---- chunks and fetching ----

def test_period_is_the_last_three_complete_years():
    assert ndvi.period_for(date(2026, 11, 15)) == ("2023-01-01", "2025-12-31")


def test_chunks_respect_the_10_date_limit():
    chunks = ndvi.date_chunks(DATES, "2023-01-01", "2025-12-31")
    inside = [d for d in DATES if "2023-01-01" <= d["calendar_date"] <= "2025-12-31"]
    assert len(inside) == 69
    assert len(chunks) == 7
    assert chunks[0][0] == inside[0]["modis_date"] and chunks[-1][1] == inside[-1]["modis_date"]


class FakeModis:
    """Answers like the real service, with the probe's values repeated for every date."""

    def __init__(self, fail_band=None):
        self.calls = []
        self.fail_band = fail_band

    def handler(self, request: httpx.Request):
        if request.url.path.endswith("/dates"):
            return httpx.Response(200, json={"dates": DATES})
        band = request.url.params["band"]
        self.calls.append(band)
        if band == self.fail_band:
            return httpx.Response(503, text="busy")
        first, last = request.url.params["startDate"], request.url.params["endDate"]
        wanted = [d for d in DATES if first <= d["modis_date"] <= last]
        assert len(wanted) <= ndvi.MAX_DATES
        green = band == ndvi.NDVI_BAND
        rows = [{"modis_date": d["modis_date"], "calendar_date": d["calendar_date"],
                 "data": [1500 if green and d["calendar_date"][5:7] == "08" else (6000 if green else 0)]} for d in wanted]
        return httpx.Response(200, json={"subset": rows})


def run_fetch(fake, waits=None):
    async def no_sleep(s):
        if waits is not None:
            waits.append(s)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as c:
            return await ndvi.fetch(c, LAT, LON, today=date(2026, 11, 15), sleep=no_sleep)
    return asyncio.run(go())


def test_computed_dates_match_the_service_date_list():
    real = [d for d in DATES if "2023" <= d["calendar_date"][:4] <= "2025"]
    assert ndvi.modis_dates(2023, 2025) == [{"modis_date": d["modis_date"], "calendar_date": d["calendar_date"]} for d in real]


def test_a_502_is_retried_then_succeeds():
    fake = FakeModis()
    fail_once = {"left": 1}
    original = fake.handler

    def flaky(request):
        if fail_once["left"] and not request.url.path.endswith("/dates"):
            fail_once["left"] -= 1
            return httpx.Response(502, text="Proxy Error")
        return original(request)
    fake.handler = flaky
    waits = []
    doc = run_fetch(fake, waits)
    assert waits == [ndvi.RETRY_WAIT_S]
    assert len(doc["series"]) == 69


def test_fetch_requests_both_bands_in_chunks_and_summarises():
    fake = FakeModis()
    doc = run_fetch(fake)
    assert fake.calls.count(ndvi.NDVI_BAND) == 7 and fake.calls.count(ndvi.QA_BAND) == 7
    assert len(doc["series"]) == 69
    assert doc["bare_months"] == [8]  # the fake makes every August bare


def test_fetch_failure_is_raised_after_the_retries():
    fake = FakeModis(fail_band=ndvi.QA_BAND)
    with pytest.raises(httpx.HTTPStatusError):
        run_fetch(fake)
    assert fake.calls.count(ndvi.QA_BAND) >= ndvi.ATTEMPTS


# ---- demo-farm lookup ----

def write_farm(tmp_path, doc=None):
    farms = tmp_path / "farms.json"
    farms.write_text(json.dumps({"farms": [{"id": "webberwood", "name": "W", "lat": LAT, "lon": LON}]}), encoding="utf-8")
    folder = tmp_path / "ndvi"
    folder.mkdir()
    if doc:
        (folder / "webberwood.json").write_text(json.dumps(doc), encoding="utf-8")
    return folder, farms


def test_lookup_uses_the_prepared_file_inside_the_farm_box(tmp_path):
    doc = ndvi.build_doc([point("2024-05-01", 0.7)], "2023-01-01", "2025-12-31", LAT, LON, "2026-11-15")
    folder, farms = write_farm(tmp_path, doc)
    got = ndvi_store.get(LAT + 0.001, LON, folder, farms)
    assert got["status"] == "ok" and got["origin"] == "precomputed"
    away = ndvi_store.get(LAT + 0.05, LON, folder, farms)
    assert away["status"] == "not_prepared" and "demo farms" in away["reason"]


def test_lookup_without_file_or_with_bad_file(tmp_path):
    folder, farms = write_farm(tmp_path)
    got = ndvi_store.get(LAT, LON, folder, farms)
    assert got["status"] == "not_prepared" and got["demo_farm"] is True and "yet" in got["reason"]
    (folder / "webberwood.json").write_text("{broken", encoding="utf-8")
    assert ndvi_store.get(LAT, LON, folder, farms)["status"] == "not_prepared"


# ---- wiring into the rotation answer ----

def test_apply_ndvi_marks_the_current_rotation_and_replaces_the_bare_finding():
    result = {"strategies": [{"id": "current", "is_current": True}, {"id": "x", "is_current": False}],
              "findings": [{"id": "rising_heat"}, {"id": "bare_soil"}]}
    doc = {"status": "ok", "bare_months": [7, 8], "period": "2023-2025", "bare_threshold": 0.25,
           "source": ndvi.SOURCE, "resolution_m": 250}
    apply_ndvi(result, doc)
    assert result["strategies"][0]["satellite_bare_months"] == [7, 8]
    assert "satellite_bare_months" not in result["strategies"][1]
    ids = [f["id"] for f in result["findings"]]
    assert ids == ["rising_heat", "bare_soil_satellite"]
    assert "July, August" in result["findings"][-1]["text"]


def test_apply_ndvi_with_no_bare_months_keeps_findings():
    result = {"strategies": [{"id": "current", "is_current": True}], "findings": [{"id": "bare_soil"}]}
    apply_ndvi(result, {"status": "ok", "bare_months": [], "period": "2023-2025"})
    assert result["strategies"][0]["satellite_bare_months"] == []
    assert [f["id"] for f in result["findings"]] == ["bare_soil"]


def test_apply_ndvi_ignores_missing_data():
    result = {"strategies": [{"id": "current", "is_current": True}], "findings": []}
    apply_ndvi(result, {"status": "not_prepared", "reason": "x"})
    assert "satellite_bare_months" not in result["strategies"][0]
