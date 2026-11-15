"""SSURGO service tests. Network calls are replaced by httpx.MockTransport."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.records import RECORD_FIELDS
from app.services import ssurgo
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures"
FOUND = (FX / "ssurgo_found.json").read_text(encoding="utf-8")
NONE = (FX / "ssurgo_none.json").read_text(encoding="utf-8")


def client_for(body=FOUND, status=200, error=None, calls=None):
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append(request)
        if error:
            raise error
        return httpx.Response(status, content=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(client, tmp_path, lat=30.2752, lon=-98.872):
    cache = DiskCache(tmp_path)

    async def go():
        async with client:
            return await ssurgo.fetch(client, lat, lon, cache)
    return asyncio.run(go())


def as_dict(records):
    return {r["variable"]: r for r in records}


def test_success_returns_all_eight_facts(tmp_path):
    records = run(client_for(), tmp_path)
    d = as_dict(records)
    assert set(d) == {
        "soil_map_unit_name", "soil_organic_matter", "soil_texture", "soil_drainage_class",
        "soil_hydrologic_group", "soil_available_water_capacity", "soil_erodibility_k", "soil_slope_range"}
    assert d["soil_map_unit_name"]["value"].startswith("Pedernales fine sandy loam")
    assert d["soil_organic_matter"]["value"] == 0.75 and d["soil_organic_matter"]["units"] == "%"
    assert d["soil_texture"]["value"] == "Fine sandy loam"
    assert d["soil_drainage_class"]["value"] == "Well drained"
    assert d["soil_hydrologic_group"]["value"] == "C"
    assert d["soil_available_water_capacity"]["value"] == 0.13
    assert d["soil_erodibility_k"]["value"] == 0.24
    assert d["soil_slope_range"]["value"] == "1 to 3" and d["soil_slope_range"]["units"] == "%"


def test_every_record_is_marked_as_map_unit_average(tmp_path):
    for r in run(client_for(), tmp_path):
        assert set(r) == set(RECORD_FIELDS)
        assert r["resolution_m"] == 250
        assert "map-unit average" in r["source"]
        assert r["live_or_cached"] == "live"


def test_request_is_a_post_with_the_point_in_the_query(tmp_path):
    calls = []
    run(client_for(calls=calls), tmp_path, 30.2752, -98.872)
    assert len(calls) == 1 and calls[0].method == "POST"
    body = json.loads(calls[0].content)
    assert "point(-98.872000 30.275200)" in body["query"]
    assert body["format"] == "JSON+COLUMNNAME"


def test_timeout(tmp_path):
    with pytest.raises(httpx.TimeoutException):
        run(client_for(error=httpx.ReadTimeout("slow")), tmp_path)


def test_http_error(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(body="boom", status=500), tmp_path)


def test_malformed_response(tmp_path):
    with pytest.raises(ValueError):  # not JSON
        run(client_for(body="<html>oops</html>"), tmp_path)
    with pytest.raises(SourceUnavailable, match="could not read"):  # JSON, wrong shape
        run(client_for(body="[1, 2, 3]"), tmp_path)
    with pytest.raises(SourceUnavailable, match="could not read"):
        run(client_for(body='{"Table": "nope"}'), tmp_path)


def test_empty_result_means_no_soil_survey_data(tmp_path):
    with pytest.raises(SourceUnavailable, match="no soil survey data for this location"):
        run(client_for(body=NONE), tmp_path)
    with pytest.raises(SourceUnavailable, match="no soil survey data for this location"):
        run(client_for(body='{"Table": [["muname"]]}'), tmp_path)  # header only, no row


def test_missing_property_is_omitted_and_others_kept(tmp_path):
    body = json.dumps({"Table": [
        ["muname", "drainagecl", "hydgrp", "slope_l", "slope_h", "om_r", "awc_r", "kffact", "texdesc"],
        ["Some soil", "Well drained", None, "0", "2", None, "0.15", "", "Loam"]]})
    d = as_dict(run(client_for(body=body), tmp_path))
    assert "soil_organic_matter" not in d and "soil_hydrologic_group" not in d and "soil_erodibility_k" not in d
    assert d["soil_texture"]["value"] == "Loam" and d["soil_slope_range"]["value"] == "0 to 2"


def test_row_with_no_usable_values_is_unavailable(tmp_path):
    body = json.dumps({"Table": [["muname", "om_r"], [None, None]]})
    with pytest.raises(SourceUnavailable):
        run(client_for(body=body), tmp_path)


def test_cache_hit_makes_no_upstream_call(tmp_path):
    first_calls = []
    first = run(client_for(calls=first_calls), tmp_path)
    assert len(first_calls) == 1
    second_calls = []
    second = run(client_for(calls=second_calls), tmp_path)
    assert second_calls == []
    assert all(r["live_or_cached"] == "cached" for r in second)
    assert [r["value"] for r in second] == [r["value"] for r in first]


def test_failure_is_not_cached(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(body="boom", status=500), tmp_path)
    assert not list(tmp_path.glob("*.json"))
