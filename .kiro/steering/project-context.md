# Field Shift: Rotation Explorer - project context

Hackathon project for the challenge "Field Shift: Adapting Farms with NASA Data". A web decision-support tool that helps US farmers compare crop rotations using NASA Earth observations plus USDA soil, crop and climate data. It supports farmer judgment and never replaces local expertise.

## Team and constraints
- 3-4 people, little web coding experience, about 48 hours to the deadline. Goal: a working demo first, then improve.
- Keep code simple, commented, few dependencies (no new backend or frontend packages without asking). Ask the user before anything ambiguous.
- US data only.

## Stack and how to run (Windows / PowerShell)
- `backend/`: Python FastAPI on **port 8010** (chosen to avoid the old Farmers-Helpers server on 8000; kept so nothing else has to change). Venv at `backend/.venv`.
  - Run: `cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload` (always with `--reload`, or code changes are not picked up).
  - Tests: `backend\run_tests.py`. Everything at once: `backend\verify.py` (writes `verify_report.txt`). Server health: `backend\diagnose.py`.
- `frontend/`: React 18 + Vite 5 + MapLibre GL 5 + Recharts. Run: `cd frontend; npm.cmd run dev` (http://localhost:5173). Vite proxies `/api` and `/health` to 127.0.0.1:8010.
- Node is at `C:\Program Files\nodejs` but not on PATH; prepend it and use `npm.cmd` (PowerShell blocks `npm.ps1`).
- Agent terminal output capture is unreliable; write results to report files and read them. Background processes (`control_pwsh_process`) are more reliable than the foreground shell for Python scripts.
- MCP tools are configured in `.kiro/settings/mcp.json`: Playwright (real browser checks, screenshots) and Context7 (library docs).
- Some tamu.edu pages answer 403 to scripts but load in a real browser; check them with Playwright.

## Rules
- The old `Farmers-Helpers/` clone was deleted from this workspace on 2026-11-15 at the user's request. The team's version lives on GitHub (github.com/OzzyWay/Farmers-Helpers); this project never depended on it.
- Secrets live in repo-root `.env` (saved as UTF-16; backend detects the encoding). Never read, print or copy secret values, never send them to the browser. Variable names: `EARTHDATA_TOKEN` (NASA Earthdata Login bearer token, needed for IMERG, GRACE and SMAP), `NASS_QUICKSTATS_API_KEY`, `SERPAPI_API_KEY` (unused). Remind the user to revoke and regenerate the Earthdata token after the hackathon, because it was pasted in chat.
- Demo farm: Webberwood Ranch, Webberville TX, 30.233589, -97.496006 in `config/demo_farms.json` (a pasture pixel near 20326 FM 969; the listing pin itself is a wooded pixel). Fredericksburg (30.2752, -98.872) is a useful second test point with a layered soil.
- Git repo in the project root since 2026-11-15, branch `main`, remote `origin` = github.com/rowitus/Farmer-s-prototype (first commit 307d657). Commit or push only when the user asks; never commit `.env`.
- Free-tier limits: Open-Meteo about 3,900 weighted calls per new outlook location (600/min, 5,000/h, 10,000/day), so outlooks are precomputed for demo farms. CropScape requests sometimes hang; the CDL service retries once.

## Done
- Map, location search (Census geocoder, Nominatim fallback, lat/lon, map click, demo-farm button), 1 km "estimated field area" box.
- Spec `farm-data-panel` (all 10 tasks): `/api/farm-data` with NASA POWER climate normals, USDA SSURGO soil, USDA CDL crop history; disk cache; partial failure never 500s; Apple-style frosted panel with Climate / Soil / Crop history, chart, source tags, light/dark, accessibility.

## In progress: spec `rotation-explorer`
Requirements, design and tasks in `.kiro/specs/rotation-explorer/`. Rules-based (no black-box model): sourced 15-crop table for Central Texas (`config/crops.json`), exclusion rules, rotation templates, six 0-100 scores with formulas shown, findings, explanations with evidence, risks, gaps and confidence.
- Done: tasks 1-6 (fixtures, crop table + validator, full soil profile, 1981+ climate indicators and Theil-Sen / Mann-Kendall trends from NASA POWER daily incl. root-zone soil wetness and evaporation, Open-Meteo 2030-2049 outlook with budget guard and precomputed Webberwood file, current rotation from CDL).
- Order agreed with the user: task 7 (engine) and 8 (`/api/rotation`, wiring trends, soil profile and outlook), then MODIS NDVI (ORNL DAAC, no login), then NASA water data (IMERG rain and GRACE-DA soil moisture / groundwater via the GES DISC Giovanni Time Series API; SMAP via AppEEARS if the token works), then the frontend summary below the map (3D CSS soil block, trends charts, strategy cards, calendar strip), then Playwright checks.
- Phase 2 (after the deadline): NASA NEX-GDDP-CMIP6 projection for demo farms, advanced soil-test form, USDA Quick Stats prices, terrain slope with the K factor, NLCD land cover.
Honest 3D rule: terrain, slope, erosion and NDVI can be shown spatially; SMAP, IMERG, GRACE, POWER and PRISM only as time series or location-level values, never as fake fine-resolution maps.
