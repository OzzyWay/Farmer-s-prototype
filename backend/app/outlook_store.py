"""Where the climate outlook comes from for a location, and the background loader.

Lookup order (Req 18.1, 18.8):
1. A precomputed file in config/outlooks/<farm_id>.json, when the location is inside a demo
   farm's 1 km field box. Instant, and works without the network.
2. A cached on-demand result for the location's 0.1° grid cell (about 10 km, the models'
   downscaled resolution), if it is less than 30 days old.
3. Otherwise "not_loaded": the page offers a "Load 2030-2049 outlook" button.

The loader runs one outlook at a time (the free Open-Meteo limits allow about one new
location an hour). Its status lives in memory, which is enough for one server process.
"""
import asyncio
import json
import logging
import math
import time
from datetime import date, timedelta
from pathlib import Path

from app.cache import DiskCache
from app.services import openmeteo
from app.services.base import describe_failure

log = logging.getLogger("farm_data")

ROOT = Path(__file__).resolve().parents[2]
PRECOMPUTED_DIR = ROOT / "config" / "outlooks"
DEMO_FARMS_FILE = ROOT / "config" / "demo_farms.json"
CACHE_KEY = "outlook"
MAX_AGE_DAYS = 30
FIELD_HALF_KM = 0.5          # same 1 km box as the map's "estimated field area"
ETA_SECONDS = 90             # two requests, 65 s apart
FAILURE_MEMORY_S = 15 * 60   # remember a failed load's reason for 15 minutes


def cell(lat: float, lon: float) -> tuple[float, float]:
    """The 0.1° grid cell used as the cache key."""
    return round(lat, 1), round(lon, 1)


def _inside_box(lat, lon, farm_lat, farm_lon) -> bool:
    dlat = FIELD_HALF_KM / 111.32
    dlon = FIELD_HALF_KM / (111.32 * math.cos(math.radians(farm_lat)))
    return abs(lat - farm_lat) <= dlat and abs(lon - farm_lon) <= dlon


def _is_fresh(doc: dict, today: date) -> bool:
    try:
        fetched = date.fromisoformat(doc["fetched_on"])
    except (KeyError, TypeError, ValueError):
        return False
    return doc.get("status") == "ok" and bool(doc.get("indicators")) and today - fetched <= timedelta(days=MAX_AGE_DAYS)


class OutlookStore:
    def __init__(self, cache: DiskCache, precomputed_dir: Path = PRECOMPUTED_DIR,
                 farms_file: Path = DEMO_FARMS_FILE, budget: "openmeteo.Budget | None" = None,
                 sleep=asyncio.sleep, clock=time.monotonic):
        self.cache = cache
        self.precomputed_dir = Path(precomputed_dir)
        self.farms_file = Path(farms_file)
        self.budget = budget
        self.sleep = sleep
        self.clock = clock
        self.loading: dict[tuple, float] = {}       # cell -> start time
        self.failures: dict[tuple, tuple] = {}      # cell -> (time, reason)
        self._lock = asyncio.Lock()

    # ----- lookup -----

    def precomputed(self, lat: float, lon: float) -> dict | None:
        try:
            farms = json.loads(self.farms_file.read_text(encoding="utf-8")).get("farms", [])
        except (OSError, ValueError):
            return None
        for farm in farms:
            if not _inside_box(lat, lon, farm["lat"], farm["lon"]):
                continue
            path = self.precomputed_dir / f"{farm['id']}.json"
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if doc.get("status") == "ok" and doc.get("indicators"):
                return dict(doc, origin="precomputed", farm_id=farm["id"])
        return None

    def cached(self, lat: float, lon: float, today: date | None = None) -> dict | None:
        today = today or date.today()
        doc = self.cache.read_doc(CACHE_KEY, *cell(lat, lon), lambda d: _is_fresh(d, today))
        return dict(doc, origin="cached") if doc else None

    def get(self, lat: float, lon: float, today: date | None = None) -> dict | None:
        """The outlook for this location if one is available, else None."""
        return self.precomputed(lat, lon) or self.cached(lat, lon, today)

    def status(self, lat: float, lon: float, today: date | None = None) -> dict:
        """{"status": ready | loading | not_loaded | unavailable, ...} for the page."""
        if self.get(lat, lon, today):
            return {"status": "ready"}
        key = cell(lat, lon)
        if key in self.loading:
            waited = self.clock() - self.loading[key]
            return {"status": "loading", "eta_s": max(5, int(ETA_SECONDS - waited))}
        failure = self.failures.get(key)
        if failure and self.clock() - failure[0] < FAILURE_MEMORY_S:
            return {"status": "unavailable", "reason": failure[1]}
        return {"status": "not_loaded", "eta_s": ETA_SECONDS}

    # ----- loading -----

    def can_start(self, lat: float, lon: float, today: date | None = None) -> dict:
        """Whether a load may start now. Returns a status dict ("loading" means OK to start)."""
        current = self.status(lat, lon, today)
        if current["status"] in ("ready", "loading"):
            return current
        if self.loading:
            return {"status": "unavailable",
                    "reason": "another climate outlook is loading; try again in about two minutes"}
        budget = self.budget or openmeteo.Budget()
        if not budget.can_spend(openmeteo.location_cost()):
            return {"status": "unavailable", "reason": openmeteo.LIMIT_REASON}
        return {"status": "loading", "eta_s": ETA_SECONDS}

    def reserve(self, lat: float, lon: float) -> None:
        """Mark a cell as loading straight away, so a status check made before the
        background task starts already says "loading". load() clears it when done."""
        self.loading.setdefault(cell(lat, lon), self.clock())

    async def load(self, client, lat: float, lon: float, today: date | None = None) -> dict:
        """Fetch and cache the outlook for this location's cell. Never raises."""
        key = cell(lat, lon)
        if self._lock.locked():
            return {"status": "unavailable", "reason": "another climate outlook is loading"}
        async with self._lock:
            self.loading[key] = self.clock()
            self.failures.pop(key, None)
            try:
                doc = await openmeteo.fetch_outlook(client, *key, budget=self.budget, sleep=self.sleep, today=today)
                self.cache.write_doc(CACHE_KEY, *key, doc)
                return {"status": "ready"}
            except Exception as e:  # noqa: BLE001 - a failed load must never break the server
                reason = describe_failure("Open-Meteo", e)
                log.warning("farm_data source=open_meteo error=%s", type(e).__name__)
                self.failures[key] = (self.clock(), reason)
                return {"status": "unavailable", "reason": reason}
            finally:
                self.loading.pop(key, None)
