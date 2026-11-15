"""Soil profile service tests. Network calls are replaced by httpx.MockTransport.

Fixtures are real Soil Data Access responses saved on 2026-11-15.
"""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.cache import DiskCache
from app.services import soil_profile
from app.services.base import SourceUnavailable

FX = Path(__file__).parent / "fixtures"
WEBBERWOOD = (FX / "soil_profile_webberwood.json").read_text(encoding="utf-8")
FREDERICKSBURG = (FX / "soil_profile_fredericksburg.json").read_text(encoding="utf-8")
NONE = (FX / "soil_profile_none.json").read_text(encoding="utf-8")


def client_for(body=WEBBERWOOD, status=200, error=None, calls=None):
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append(request)
        if error:
            raise error
        return httpx.Response(status, text=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(client, tmp_path, lat=30.233589, lon=-97.496006):
    cache = DiskCache(tmp_path)

    async def go():
        async with client:
            return await soil_profile.fetch(client, lat, lon, cache)
    return asyncio.run(go())


def table(header, *rows):
    return json.dumps({"Table": [header, *rows]})


HEADER = ["muname", "compname", "comppct_r", "hzname", "hzdept_r", "hzdepb_r", "om_r",
          "claytotal_r", "sandtotal_r", "awc_r", "texdesc", "flodfreqcl", "pondfreqcl"]


# ---- success ----

def test_webberwood_profile(tmp_path):
    p = run(client_for(), tmp_path)
    assert p["status"] == "ok" and p["component"] == "Tinn" and p["component_pct"] == 85
    assert p["map_unit"].startswith("Tinn clay")
    assert p["flooding"] == "occasional" and p["ponding"] == "none"
    assert [(layer["top_cm"], layer["bottom_cm"]) for layer in p["layers"]] == [(0, 70), (70, 152), (152, 203)]
    assert all(layer["texture_group"] == "clay" for layer in p["layers"])
    assert p["layers"][0]["om_pct"] == 2.5 and p["layers"][0]["awc"] == 0.18
    assert p["source"] == "USDA SSURGO (map-unit average)" and p["resolution_m"] == 250
    assert p["live_or_cached"] == "live"


def test_profile_with_several_textures(tmp_path):
    p = run(client_for(FREDERICKSBURG), tmp_path)
    assert [layer["texture_group"] for layer in p["layers"]] == ["sandy loam", "clay", "clay loam", "clay loam"]
    assert p["flooding"] == "none"


def test_layers_are_sorted_from_the_surface_down(tmp_path):
    body = table(HEADER,
                 ["Soil", "Comp", "90", "Bt", "30", "80", "1", "30", "40", "0.15", "Clay loam", "None", "None"],
                 ["Soil", "Comp", "90", "A", "0", "30", "2", "20", "40", "0.17", "Loam", "None", "None"])
    p = run(client_for(body), tmp_path)
    assert [layer["name"] for layer in p["layers"]] == ["A", "Bt"]


def test_query_is_a_post_with_only_numbers_in_it(tmp_path):
    calls = []
    run(client_for(calls=calls), tmp_path)
    body = json.loads(calls[0].content)
    assert calls[0].method == "POST" and body["format"] == "JSON+COLUMNNAME"
    assert "point(-97.496006 30.233589)" in body["query"]
    assert "comonth" in body["query"] and "chtexturegrp" in body["query"]
    with pytest.raises(ValueError):
        soil_profile.build_query("30); DROP TABLE mapunit; --", 1)


# ---- missing and empty ----

def test_missing_property_is_omitted_and_the_layer_kept(tmp_path):
    body = table(HEADER,
                 ["Soil", "Comp", "90", "A", "0", "25", None, "", "40", "0.12", None, None, None])
    p = run(client_for(body), tmp_path)
    layer = p["layers"][0]
    assert layer == {"top_cm": 0, "bottom_cm": 25, "name": "A", "sand_pct": 40, "awc": 0.12}
    assert "flooding" not in p and "ponding" not in p


def test_layer_without_depth_is_skipped_and_counted(tmp_path):
    body = table(HEADER,
                 ["Soil", "Comp", "90", "A", "0", "25", "2", "20", "40", "0.15", "Loam", "None", "None"],
                 ["Soil", "Comp", "90", "R", None, None, None, None, None, None, "Bedrock", "None", "None"])
    p = run(client_for(body), tmp_path)
    assert len(p["layers"]) == 1 and p["skipped_layers"] == 1


def test_empty_result_means_no_soil_survey_data(tmp_path):
    with pytest.raises(SourceUnavailable, match="no soil survey data for this location"):
        run(client_for(NONE), tmp_path)
    with pytest.raises(SourceUnavailable, match="no soil survey data"):
        run(client_for(table(HEADER)), tmp_path)


# ---- failures ----

def test_timeout(tmp_path):
    with pytest.raises(httpx.TimeoutException):
        run(client_for(error=httpx.ReadTimeout("slow")), tmp_path)


def test_http_error(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(body="boom", status=500), tmp_path)


def test_malformed_response(tmp_path):
    with pytest.raises(ValueError):
        run(client_for(body="<html>maintenance</html>"), tmp_path)
    with pytest.raises(SourceUnavailable, match="could not read"):
        run(client_for(body="[1, 2]"), tmp_path)
    with pytest.raises(SourceUnavailable, match="could not read"):
        run(client_for(body=json.dumps({"Table": [["muname"], ["x"]]})), tmp_path)


def test_failure_is_not_cached(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        run(client_for(body="boom", status=500), tmp_path)
    assert not list(tmp_path.glob("*.json"))


# ---- cache ----

def test_cache_hit_makes_no_upstream_call(tmp_path):
    first = run(client_for(), tmp_path)
    calls = []
    second = run(client_for(calls=calls), tmp_path)
    assert calls == []
    assert second["live_or_cached"] == "cached"
    assert second["layers"] == first["layers"]
    assert (tmp_path / "soil_profile_30.23_-97.50.json").exists()


def test_malformed_cache_file_is_ignored(tmp_path):
    (tmp_path / "soil_profile_30.23_-97.50.json").write_text('{"status": "ok", "layers": "x"}', encoding="utf-8")
    calls = []
    p = run(client_for(calls=calls), tmp_path)
    assert len(calls) == 1 and p["live_or_cached"] == "live"


# ---- texture groups ----

@pytest.mark.parametrize("texture,group", [
    ("Clay", "clay"), ("Silty clay", "clay"), ("Sandy clay", "clay"),
    ("Clay loam", "clay loam"), ("Silty clay loam", "clay loam"), ("Sandy clay loam", "clay loam"),
    ("Fine sandy loam", "sandy loam"), ("Gravelly sandy loam", "sandy loam"),
    ("Loamy fine sand", "sand"), ("Sand", "sand"), ("Loamy sand", "sand"),
    ("Silt loam", "silt"), ("Loam", "loam"), ("Very gravelly loam", "loam"),
    ("Unweathered bedrock", "bedrock"), ("Muck", "organic"), (None, None), ("Variable", None),
])
def test_texture_group(texture, group):
    assert soil_profile.texture_group(texture) == group
