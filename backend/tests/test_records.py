"""Feature_Record shape tests."""
import pytest

from app.records import RECORD_FIELDS, is_valid_record, make_record, unavailable_result


def test_make_record_has_all_seven_fields():
    r = make_record("temperature_mean", "NASA POWER", 50000, "01", 4.2, "°C")
    assert set(r) == set(RECORD_FIELDS) and len(RECORD_FIELDS) == 7
    assert r["live_or_cached"] == "live"
    assert is_valid_record(r)


def test_invalid_live_or_cached_rejected():
    with pytest.raises(ValueError):
        make_record("x", "s", 1, "d", 1, "u", "fresh")


def test_is_valid_record_rejects_missing_fields():
    r = make_record("x", "s", 1, "d", 1, "u")
    del r["units"]
    assert not is_valid_record(r)
    assert not is_valid_record("nope")


def test_unavailable_result_shape():
    assert unavailable_result("USDA SSURGO", "no soil survey data for this location") == {
        "status": "unavailable", "source": "USDA SSURGO", "reason": "no soil survey data for this location"}
