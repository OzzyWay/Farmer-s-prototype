"""Current rotation from the CDL crop history (Req 6)."""
import pytest

from app.rotation.crops import load
from app.rotation.current import infer

CROPS = load()


def cdl(*categories, start=2018):
    """CDL Feature_Records like the farm-data CDL service returns, oldest year first."""
    return [{"variable": "crop_type", "date": str(start + i), "value": c, "source": "USDA NASS CDL",
             "resolution_m": 30, "units": "", "live_or_cached": "live"} for i, c in enumerate(categories)]


def test_webberwood_pasture_7_of_8_years():
    history = cdl(*["Grass/Pasture"] * 5, "Evergreen Forest", "Grass/Pasture", "Grass/Pasture")
    cur = infer(history, CROPS)
    assert cur["status"] == "inferred" and cur["inferred"] is True
    assert cur["crop_ids"] == ["bermudagrass"] and cur["sequence"] == [["bermudagrass"]]
    assert cur["evidence"] == "Grass/Pasture in 7 of 8 years (2018-2025)"
    assert "Pasture" in cur["label"]


def test_records_in_any_order_are_sorted_by_year():
    history = list(reversed(cdl(*["Grass/Pasture"] * 8)))
    assert [row["year"] for row in infer(history, CROPS)["history"]] == list(range(2018, 2026))


def test_corn_soybean_alternation():
    cur = infer(cdl("Corn", "Soybeans", "Corn", "Soybeans", "Corn", "Soybeans", "Corn", "Soybeans"), CROPS)
    assert cur["sequence"] == [["corn"], ["soybean"]]   # soybean was last, so corn comes first
    assert cur["label"] == "Corn then Soybean"
    assert cur["evidence"] == "Corn in 4, Soybeans in 4 of 8 years (2018-2025)"


def test_three_crop_rotation_keeps_the_order_they_last_occurred():
    cur = infer(cdl("Cotton", "Sorghum", "Winter Wheat", "Cotton", "Sorghum", "Winter Wheat", "Cotton", "Sorghum"), CROPS)
    assert cur["sequence"] == [["winter_wheat_grain"], ["cotton"], ["grain_sorghum"]]


def test_double_crop_maps_to_two_crops_in_one_year():
    cur = infer(cdl(*["Dbl Crop WinWht/Soybeans"] * 7, "Soybeans"), CROPS)
    assert cur["crop_ids"] == ["winter_wheat_grain", "soybean"]
    assert cur["sequence"] == [["winter_wheat_grain", "soybean"]]


def test_short_history_can_still_be_continuous():
    cur = infer(cdl("Corn", "Corn", "Corn", start=2023), CROPS)
    assert cur["crop_ids"] == ["corn"] and cur["evidence"] == "Corn in 3 of 3 years (2023-2025)"


def test_mostly_forest_is_unknown_with_a_reason():
    cur = infer(cdl(*["Deciduous Forest"] * 5, "Grass/Pasture", "Grass/Pasture", "Mixed Forest"), CROPS)
    assert cur["status"] == "unknown" and cur["crop_ids"] == [] and cur["inferred"] is False
    assert "mostly Deciduous Forest" in cur["reason"] and "Choose what you grow now" in cur["reason"]


def test_empty_history_is_unknown():
    cur = infer([], CROPS)
    assert cur["status"] == "unknown" and "No crop map history" in cur["reason"]


def test_farmland_outside_the_crop_table_is_unknown():
    cur = infer(cdl(*["Rice"] * 8), CROPS)
    assert cur["status"] == "unknown" and "not crops in the crop table" in cur["reason"]


def test_mixed_history_uses_the_most_recent_crop_and_says_so():
    cur = infer(cdl("Corn", "Cotton", "Sorghum", "Soybeans", "Fallow/Idle Cropland", "Winter Wheat"), CROPS)
    assert cur["crop_ids"] == ["winter_wheat_grain"]
    assert cur["evidence"].startswith("Mixed history")


def test_farmer_choice_wins_over_the_crop_map():
    cur = infer(cdl(*["Grass/Pasture"] * 8), CROPS, override="grain_sorghum")
    assert cur["status"] == "farmer_choice" and cur["crop_ids"] == ["grain_sorghum"]
    assert cur["inferred"] is False and cur["evidence"] == "Chosen by you"


def test_unknown_override_is_rejected():
    with pytest.raises(ValueError, match="unknown crop id 'alfalfa'"):
        infer([], CROPS, override="alfalfa")


def test_non_crop_records_are_ignored():
    records = cdl(*["Corn"] * 6) + [{"variable": "soil_texture", "date": "2024", "value": "Clay"}]
    assert infer(records, CROPS)["evidence"] == "Corn in 6 of 6 years (2018-2023)"
