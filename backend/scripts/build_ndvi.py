"""Prepare MODIS NDVI (how green the field looks from space) for every demo farm (task 10).

The ORNL DAAC MODIS service is slow (20-37 s per request, at most 10 dates each), so the last
3 complete years are fetched once, ahead of time, and saved to config/ndvi/<farm_id>.json.
The page then shows them instantly. It takes a few minutes per farm.

Usage, from the backend folder:
    .venv\\Scripts\\python.exe scripts\\build_ndvi.py                    # every demo farm
    .venv\\Scripts\\python.exe scripts\\build_ndvi.py --farm webberwood
Progress and the result are also written to scripts/build_ndvi_log.txt.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import httpx  # noqa: E402

from app.services import ndvi  # noqa: E402

ROOT = HERE.parents[1]
FARMS_FILE = ROOT / "config" / "demo_farms.json"
OUT_DIR = ROOT / "config" / "ndvi"
LOG = HERE / "build_ndvi_log.txt"


def log(line: str) -> None:
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def build(farms: list[dict]) -> None:
    timeout = httpx.Timeout(ndvi.REQUEST_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for farm in farms:
            start = time.perf_counter()
            log(f"{farm['id']}: fetching NDVI for the last {ndvi.YEARS} complete years…")
            done = []

            def progress(band, first, last):
                done.append(1)
                log(f"  {len(done)} requests done ({band} {first}-{last}, {time.perf_counter() - start:.0f}s)")

            doc = await ndvi.fetch(client, farm["lat"], farm["lon"], progress=progress)
            doc = dict(doc, farm_id=farm["id"], farm_name=farm["name"], built_by="backend/scripts/build_ndvi.py")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            path = OUT_DIR / f"{farm['id']}.json"
            path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            log(f"{farm['id']}: {len(doc['series'])} good values, bare months {doc['bare_months'] or 'none'}, "
                f"saved {path} in {time.perf_counter() - start:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--farm", help="only this farm id")
    args = parser.parse_args()
    farms = json.loads(FARMS_FILE.read_text(encoding="utf-8"))["farms"]
    if args.farm:
        farms = [f for f in farms if f["id"] == args.farm]
        if not farms:
            sys.exit(f"no demo farm with id {args.farm!r} in {FARMS_FILE}")
    LOG.write_text("", encoding="utf-8")
    try:
        asyncio.run(build(farms))
    except Exception as e:  # noqa: BLE001 - say what failed, then stop
        log(f"FAILED: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
