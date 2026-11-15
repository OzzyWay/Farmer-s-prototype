"""Crop table tests: the real file is complete and sourced, and bad edits are caught."""
import copy
import json

import pytest

from app.rotation import crops as crop_table
from app.rotation.crops import CROPS_FILE, CropTableError, load, validate

EXPECTED_IDS = {
    "bermudagrass", "native_grass_mix", "sorghum_sudangrass", "forage_oats", "annual_ryegrass",
    "crimson_clover", "hairy_vetch", "cowpea", "sunn_hemp", "winter_wheat_cover",
    "corn", "grain_sorghum", "cotton", "soybean", "winter_wheat_grain",
}


@pytest.fixture(scope="module")
def raw():
    return json.loads(CROPS_FILE.read_text(encoding="utf-8"))


def test_real_table_has_the_15_crops(raw):
    assert set(load()) == EXPECTED_IDS


def test_every_crop_has_all_attributes_and_a_source(raw):
    required = set(crop_table.ALLOWED) | set(crop_table.OTHER_REQUIRED) | set(crop_table.MONTH_FIELDS)
    for crop in raw["crops"]:
        assert required <= set(crop), crop["id"]
        assert crop["sources"], crop["id"]
        for src in crop["sources"]:
            assert src["title"].strip() and src["url"].startswith("https://"), crop["id"]


def test_table_states_the_region(raw):
    assert "Central Texas" in raw["_comment"]


def _broken(raw, crop_id, change):
    data = copy.deepcopy(raw)
    crop = next(c for c in data["crops"] if c["id"] == crop_id)
    change(crop)
    return data


def test_missing_attribute_names_crop_and_field(raw):
    data = _broken(raw, "cowpea", lambda c: c.pop("wet_soil_tolerance"))
    with pytest.raises(CropTableError, match=r"crop 'cowpea', field 'wet_soil_tolerance': missing"):
        validate(data)


def test_missing_source_is_rejected(raw):
    data = _broken(raw, "corn", lambda c: c.update(sources=[]))
    with pytest.raises(CropTableError, match=r"crop 'corn', field 'sources'"):
        validate(data)


def test_bad_source_url_is_rejected(raw):
    data = _broken(raw, "corn", lambda c: c["sources"][0].update(url="see the extension office"))
    with pytest.raises(CropTableError, match=r"sources\[0\]\.url"):
        validate(data)


def test_bad_enum_is_rejected(raw):
    data = _broken(raw, "hairy_vetch", lambda c: c.update(heat_tolerance="very high"))
    with pytest.raises(CropTableError, match=r"'very high' is not one of low, medium, high"):
        validate(data)


def test_bad_month_is_rejected(raw):
    data = _broken(raw, "soybean", lambda c: c.update(in_ground_months=[5, 6, 13]))
    with pytest.raises(CropTableError, match=r"in_ground_months"):
        validate(data)


def test_growing_months_must_be_inside_in_ground_months(raw):
    data = _broken(raw, "soybean", lambda c: c.update(growing_months=[4, 5]))
    with pytest.raises(CropTableError, match=r"growing_months"):
        validate(data)


def test_duplicate_id_is_rejected(raw):
    data = copy.deepcopy(raw)
    data["crops"].append(copy.deepcopy(data["crops"][0]))
    with pytest.raises(CropTableError, match="used twice"):
        validate(data)


def test_invalid_json_file(tmp_path):
    bad = tmp_path / "crops.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CropTableError, match="not valid JSON"):
        load(bad)
