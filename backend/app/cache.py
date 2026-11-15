"""Disk cache for upstream results, so repeat lookups are fast and work offline.

One JSON file per source and per location, named like
"nasa_power_30.28_-98.87.json". Latitude and longitude are rounded to 2 decimals
(about 1 km), so nearby points share an entry. The 30 m crop map uses 4 decimals (KEY_DECIMALS).

Rules:
- Only successful live results are written. Failures are never cached.
- A missing, unreadable or malformed file counts as a miss. It is not deleted.
- Records are stored as "live" and returned as "cached" when read back.
"""
import json
import logging
import os
import tempfile
from pathlib import Path

from app.records import is_valid_record

log = logging.getLogger("farm_data")

# backend/cache/ (git-ignored)
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"

# Sources finer than about 1 km need a finer key. The crop map (CDL) labels 30 m squares, so
# two points 500 m apart can be a pasture and a road; 4 decimals is about 11 m.
KEY_DECIMALS = {"cdl": 4}


class DiskCache:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else DEFAULT_CACHE_DIR

    def path_for(self, source: str, lat: float, lon: float) -> Path:
        d = KEY_DECIMALS.get(source, 2)
        return self.directory / f"{source}_{lat:.{d}f}_{lon:.{d}f}.json"

    def read(self, source: str, lat: float, lon: float) -> list | None:
        """Return cached records marked 'cached', or None on any kind of miss."""
        path = self.path_for(source, lat, lon)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # missing, unreadable, or not JSON
        if not isinstance(data, list) or not data or not all(is_valid_record(r) for r in data):
            return None  # wrong shape: ignore it and fetch live
        return [dict(r, live_or_cached="cached") for r in data]

    def write(self, source: str, lat: float, lon: float, records: list) -> None:
        """Save records. Never raises: a cache problem must not break the response."""
        if not records:
            return  # do not cache empty results
        self._write_json(source, self.path_for(source, lat, lon),
                         [dict(r, live_or_cached="live") for r in records])

    # ----- whole documents (for results that are not lists of Feature_Records) -----

    def read_doc(self, source: str, lat: float, lon: float, is_valid) -> dict | None:
        """Return a cached dict marked live_or_cached='cached', or None on any kind of miss.

        is_valid(doc) -> bool checks the shape; a file that fails it is ignored, not deleted.
        """
        path = self.path_for(source, lat, lon)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        try:
            ok = bool(is_valid(data))
        except Exception:  # noqa: BLE001 - a shape check must never break a request
            ok = False
        return dict(data, live_or_cached="cached") if ok else None

    def write_doc(self, source: str, lat: float, lon: float, doc: dict) -> None:
        """Save a successful live result as one JSON document. Never raises."""
        if not doc:
            return
        self._write_json(source, self.path_for(source, lat, lon), dict(doc, live_or_cached="live"))

    def _write_json(self, source: str, path: Path, payload) -> None:
        tmp_name = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Write to a temp file first, then rename, so a crash cannot leave half a file.
            fd, tmp_name = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_name, path)
            tmp_name = None
        except OSError as e:
            log.warning("farm_data cache_write source=%s error=%s", source, type(e).__name__)
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
