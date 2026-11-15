"""Disk cache tests. Uses pytest's tmp_path so the real cache folder is untouched."""
import json

from app.cache import DiskCache
from app.records import make_record


def recs():
    return [make_record("temperature_mean", "NASA POWER", 50000, "01", 4.2, "°C")]


def test_key_rounds_to_two_decimals(tmp_path):
    c = DiskCache(tmp_path)
    assert c.path_for("nasa_power", 30.2752, -98.872).name == "nasa_power_30.28_-98.87.json"


def test_crop_map_key_is_finer_than_its_30_m_squares(tmp_path):
    c = DiskCache(tmp_path)
    assert c.path_for("cdl", 30.233589, -97.496006).name == "cdl_30.2336_-97.4960.json"
    # 500 m apart: same climate cell, different crop map entries
    assert c.path_for("cdl", 30.2336, -97.4960) != c.path_for("cdl", 30.2336, -97.4908)


def test_write_then_read_marks_cached(tmp_path):
    c = DiskCache(tmp_path)
    c.write("nasa_power", 30.2752, -98.872, recs())
    got = c.read("nasa_power", 30.28, -98.87)  # nearby point, same rounded cell
    assert got and got[0]["live_or_cached"] == "cached"
    assert got[0]["value"] == 4.2
    # stored on disk as live
    stored = json.loads(c.path_for("nasa_power", 30.28, -98.87).read_text(encoding="utf-8"))
    assert stored[0]["live_or_cached"] == "live"


def test_miss_returns_none(tmp_path):
    assert DiskCache(tmp_path).read("cdl", 30.0, -98.0) is None


def test_malformed_file_ignored_and_kept(tmp_path):
    c = DiskCache(tmp_path)
    p = c.path_for("cdl", 30.0, -98.0)
    p.write_text("{not json", encoding="utf-8")
    assert c.read("cdl", 30.0, -98.0) is None
    assert p.exists()
    p.write_text(json.dumps([{"variable": "x"}]), encoding="utf-8")  # wrong shape
    assert c.read("cdl", 30.0, -98.0) is None


def test_empty_results_not_written(tmp_path):
    c = DiskCache(tmp_path)
    c.write("cdl", 30.0, -98.0, [])
    assert not c.path_for("cdl", 30.0, -98.0).exists()


def test_existing_entry_untouched_when_nothing_new_is_written(tmp_path):
    c = DiskCache(tmp_path)
    c.write("ssurgo", 30.0, -98.0, recs())
    before = c.path_for("ssurgo", 30.0, -98.0).read_bytes()
    c.write("ssurgo", 30.0, -98.0, [])  # a failed/empty fetch must not overwrite
    assert c.path_for("ssurgo", 30.0, -98.0).read_bytes() == before


def test_write_error_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    DiskCache(blocker / "sub").write("cdl", 30.0, -98.0, recs())  # directory cannot be created


# ---- whole-document entries (soil profile, trends, outlook) ----

def test_doc_round_trip_marks_cached(tmp_path):
    c = DiskCache(tmp_path)
    c.write_doc("soil_profile", 30.0, -98.0, {"status": "ok", "layers": [1]})
    got = c.read_doc("soil_profile", 30.0, -98.0, lambda d: d.get("status") == "ok")
    assert got == {"status": "ok", "layers": [1], "live_or_cached": "cached"}


def test_doc_failing_shape_check_is_ignored(tmp_path):
    c = DiskCache(tmp_path)
    c.write_doc("soil_profile", 30.0, -98.0, {"status": "bad"})
    assert c.read_doc("soil_profile", 30.0, -98.0, lambda d: d.get("status") == "ok") is None
    assert c.read_doc("soil_profile", 30.0, -98.0, lambda d: 1 / 0) is None  # a crashing check is a miss


def test_empty_doc_not_written(tmp_path):
    c = DiskCache(tmp_path)
    c.write_doc("soil_profile", 30.0, -98.0, {})
    assert not list(tmp_path.glob("*.json"))
