"""Dev helper: check the backend (8010) directly and through the Vite dev server (5173).
Usage (from backend/): .venv\\Scripts\\python.exe diagnose.py   -> prints and writes diagnose_report.txt"""
from pathlib import Path

import httpx

URLS = [
    "http://127.0.0.1:8010/health",
    "http://127.0.0.1:8010/api/demo-farms",
    "http://localhost:5173/",
    "http://localhost:5173/api/demo-farms",
    "http://localhost:5173/api/geocode?q=100 W Main St, Fredericksburg, TX 78624",
]
lines = []
for u in URLS:
    try:
        r = httpx.get(u, timeout=15)
        lines.append(f"{u} -> {r.status_code} {r.text[:200]!r}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"{u} -> ERROR {type(e).__name__}: {e}")
report = "\n".join(lines)
print(report)
(Path(__file__).parent / "diagnose_report.txt").write_text(report, encoding="utf-8")
