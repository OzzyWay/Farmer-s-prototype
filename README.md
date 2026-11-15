# Field Shift: Rotation Explorer

A decision-support tool that helps farmers compare crop rotations using NASA Earth observations plus USDA soil, crop and climate data. It supports farmer judgment; it does not replace local agricultural expertise.

## Folder layout

```
backend/     Python FastAPI API (data services, scoring engine)
frontend/    React + Vite + MapLibre GL JS (3D terrain map, UI)
config/      demo_farms.json  (exact demo farm coordinates)
config/      crops.json (sourced crop table), outlooks/ (precomputed climate outlooks)
.kiro/specs/ requirements, design and task lists for each feature
.env         secrets (NOT committed). Copy .env.example to start.
```

## One-time setup (Windows PowerShell)

Requirements: Python 3.11+ and Node.js 20+.

```powershell
# Secrets
Copy-Item .env.example .env   # only if you don't already have a .env
# then edit .env and set EARTHDATA_TOKEN=...

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm.cmd install
cd ..
```

If `npm` says "running scripts is disabled", use `npm.cmd` instead of `npm`.
If `node` isn't found, add `C:\Program Files\nodejs` to your PATH or reopen the terminal.

## Run (two terminals)

```powershell
# Terminal 1 - backend on http://127.0.0.1:8010
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload

# Terminal 2 - frontend on http://localhost:5173
cd frontend
npm.cmd run dev
```

Open http://localhost:5173. You should see a tilted 3D terrain map of the demo farm, Webberwood Ranch in Webberville, Texas, with the frosted farm data panel on the right.

**Troubleshooting**
- Start each server only once. Close old terminals first, or several copies will fight over the same port.
- The backend uses port **8010**. If http://127.0.0.1:8010/health doesn't show `{"status":"ok"}`, the backend isn't running.
- Quick health check of both servers: `cd backend; .\.venv\Scripts\python.exe diagnose.py`
- If `npm.cmd run dev` says `"node" no se reconoce`, run `$env:Path = "C:\Program Files\nodejs;" + $env:Path` in that terminal first, or restart your computer so the Node installer's PATH change takes effect.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe backend\run_tests.py   # backend
cd frontend; npm.cmd run build                              # frontend build check
```

Or run everything at once (tests, frontend build, live geocoder check). The results go to `backend/verify_report.txt`:

```powershell
cd backend; .\.venv\Scripts\python.exe verify.py
```

## Picking a location

- Click a demo farm button.
- Or type a US street address (US Census Geocoder, with OpenStreetMap Nominatim as fallback).
- Or type coordinates as `lat, lon`, e.g. `30.2752, -98.872`.
- Or click anywhere on the map.

The yellow square is an **estimated field area** (a 1 km box around the point). Real parcel boundaries aren't in the datasets we use.

## Changing the demo farm location

Edit `config/demo_farms.json`. The current demo farm is Webberwood Ranch (30.233589, -97.496006), a pasture spot near 20326 FM 969, Webberville, TX. If you add or move a demo farm, rebuild its climate outlook with `backend\scripts\build_outlook.py` (it uses about 3,900 of Open-Meteo's 10,000 free daily calls per farm).

## Data sources

All farm data is requested by the Python backend, never by the browser. The map tiles below are the one exception: they load directly in the browser from public tile servers that need no key.

- Climate: [NASA POWER](https://power.larc.nasa.gov) (about 50 km, regional, modelled from MERRA-2 and CERES).
- Soil: [USDA NRCS SSURGO](https://sdmdataaccess.sc.egov.usda.gov) via Soil Data Access (map-unit averages, not field measurements).
- Crop history: [USDA NASS Cropland Data Layer](https://nassgeodata.gmu.edu/CropScape/) via CropScape (one 30 m pixel per year).
- Climate outlook 2030-2049: [Open-Meteo Climate API](https://open-meteo.com/en/docs/climate-api), CMIP6 HighResMIP models. Data: Open-Meteo.com, CC BY 4.0.
- Crop facts: `config/crops.json`, written for Central Texas from SARE, USDA NRCS and Texas A&M AgriLife publications (each crop lists its sources).

## Map tiles

- Basemap: OpenStreetMap data via [OpenFreeMap](https://openfreemap.org) (free, no key). © OpenStreetMap contributors.
- 3D terrain: Mapzen Terrarium elevation tiles on AWS Open Data (free, no key).

## Secrets

- `.env` is in `.gitignore`. Never commit it, and never put tokens in frontend code.
- Only the Python backend reads `EARTHDATA_TOKEN` and `NASS_QUICKSTATS_API_KEY`.
- The Earthdata token was shared in chat during planning. Revoke it and generate a new one at https://urs.earthdata.nasa.gov after the hackathon.
