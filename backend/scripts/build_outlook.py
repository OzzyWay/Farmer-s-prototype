"""Precompute the 2030-2049 climate outlook for every demo farm (task 5.4, Req 18.1).

The outlook costs about 3,900 of Open-Meteo's 10,000 free daily calls per location, so the
demo farms are done once, ahead of time, and saved to config/outlooks/<farm_id>.json. The
demo then shows the outlook instantly and works without the network.

Usage, from the backend folder:
    .venv\\Scripts\\python.exe scripts\\build_outlook.py              # fetch live (about 70 s per farm)
    .venv\\Scripts\\python.exe scripts\\build_outlook.py --farm webberwood \\
        --recent tests\\fixtures\\openmeteo_recent_webberwood.json \\
        --future tests\\fixtures\\openmeteo_future_webberwood.json --fetched-on 2026-11-15
        # build from responses already saved (no new Open-Meteo calls)
"""
import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.services import openmeteo  # noqa: E402
from app.services.base import make_client  # noqa: E402

ROOT = HERE.parents[1]
FARMS_FILE = ROOT / "config" / "demo_farms.json"
OUT_DIR = ROOT / "config" / "outlooks"


def save(farm: dict, doc: dict, how: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = dict(doc, farm_id=farm["id"], farm_name=farm["name"], built_by="backend/scripts/build_outlook.py", built_from=how)
    path = OUT_DIR / f"{farm['id']}.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path


async def build_live(farms: list[dict]) -> None:
    async with make_client() as client:
        for i, farm in enumerate(farms):
            if i:
                await asyncio.sleep(openmeteo.GAP_SECONDS)
            doc = await openmeteo.fetch_outlook(client, farm["lat"], farm["lon"])
            print(f"{farm['id']}: saved {save(farm, doc, 'live Open-Meteo requests')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--farm", help="only this farm id")
    parser.add_argument("--recent", help="saved 1991-2020 Open-Meteo response (skips the network)")
    parser.add_argument("--future", help="saved 2030-2049 Open-Meteo response (skips the network)")
    parser.add_argument("--fetched-on", help="date the saved responses were fetched, YYYY-MM-DD")
    args = parser.parse_args()

    farms = json.loads(FARMS_FILE.read_text(encoding="utf-8"))["farms"]
    if args.farm:
        farms = [f for f in farms if f["id"] == args.farm]
        if not farms:
            sys.exit(f"no demo farm with id {args.farm!r} in {FARMS_FILE}")

    if args.recent or args.future:
        if not (args.recent and args.future and args.farm):
            sys.exit("--recent and --future need each other and --farm")
        recent = json.loads(Path(args.recent).read_text(encoding="utf-8"))
        future = json.loads(Path(args.future).read_text(encoding="utf-8"))
        farm = farms[0]
        fetched_on = args.fetched_on or date.today().isoformat()
        doc = openmeteo.build_outlook(recent, future, fetched_on, farm["lat"], farm["lon"])
        print(f"{farm['id']}: saved {save(farm, doc, f'saved Open-Meteo responses fetched {fetched_on}')}")
        return
    asyncio.run(build_live(farms))


if __name__ == "__main__":
    main()
