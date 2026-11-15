# Implementation Plan

Tasks build on each other: backend foundations, then each source, then the endpoint, then the frontend. Do not edit anything under `Farmers-Helpers/` and do not read `.env` in new code.

- [x] 1. Backend foundations
  - [x] 1.1 Create `backend/app/records.py` with the `FeatureRecord` and `Unavailable_Entry` shapes and a `make_record(...)` constructor that fills all seven fields
    - Add plain-language comments explaining each field
    - _Requirements: 4.1, 4.2, 17.3_
  - [x] 1.2 Create `backend/app/services/__init__.py` and `services/base.py` with `SourceUnavailable`, `get_json` and `post_json`
    - Wrap each call in `asyncio.wait_for(..., 10)`, set `httpx.Timeout(10)`, call `raise_for_status()`, and parse JSON
    - _Requirements: 5.3, 5.1_
  - [x] 1.3 Create `backend/app/cache.py` (Disk_Cache) with `read` and `write`
    - File name `<source>_<lat:.2f>_<lon:.2f>.json` in a constructor-supplied folder (default `backend/cache/`)
    - `read` returns records marked `cached`, or `None` for a missing, unreadable or malformed file; never deletes bad files
    - `write` uses a temp file then rename, ignores and logs write errors, and is never called for failures or empty results
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 4.3, 4.4_
  - [x] 1.4 Add `check_location(lat_text, lon_text)` to `backend/app/geocode.py`
    - Reuse `parse_coordinates` and `is_in_us`; share the "outside the US" message as a constant so existing behaviour and tests stay the same
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 1.5 Write `test_records.py`, `test_cache.py` and a `check_location` test
    - Cover key rounding, atomic write, malformed file ignored, failure not cached, existing entry untouched, and all seven fields present
    - _Requirements: 6, 7, 8.5_

- [x] 2. NASA POWER service
  - [x] 2.1 Save fixture responses in `backend/tests/fixtures/` for the climatology call and the daily call (real responses if the network works, otherwise hand-built from the documented format, including `-999` fill values)
    - _Requirements: 8.1_
  - [x] 2.2 Implement `backend/app/services/nasa_power.py`
    - Fetch climatology and the last 10 complete years of daily data concurrently
    - Build the 12-month records for mean, min and max temperature and precipitation (mm/day times days in month), and solar radiation only when present
    - Set `resolution_m = 50000` and the units from the design
    - Implement `estimate_frost_heat(daily_min, daily_max)` as a pure function for frost days, last spring frost, first fall frost and heat days above 35 °C
    - Omit the estimate records if the daily call fails or lacks data; raise `SourceUnavailable` if the monthly data is missing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 2.3 Write `test_nasa_power.py` with `httpx.MockTransport`
    - Cases: success, timeout, HTTP error, malformed response, empty result, cache hit, daily call failing while monthly records remain, and direct tests of `estimate_frost_heat`
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 3. SSURGO service
  - [x] 3.1 Save fixture responses for a found map unit, a missing property, and an empty table
    - _Requirements: 8.1_
  - [x] 3.2 Implement `backend/app/services/ssurgo.py`
    - POST the Soil Data Access query for the dominant component, built only from validated floats
    - Produce records for map unit name, organic matter, texture, drainage class, hydrologic group, available water capacity, erodibility K and slope range
    - Use `resolution_m = 250` and `source = "USDA SSURGO (map-unit average)"`
    - Omit missing properties; raise `SourceUnavailable("no soil survey data for this location")` for an empty table
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 3.3 Write `test_ssurgo.py` with `httpx.MockTransport`
    - Cases: success, timeout, HTTP error, malformed response, empty result, cache hit, missing property omitted
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 4. CDL service
  - [x] 4.1 Implement `backend/app/projection.py` with `to_albers(lat, lon)` for EPSG:5070
    - Test it against one known point
    - _Requirements: 3.1_
  - [x] 4.2 Save a real CropScape `GetCDLValue` response as a fixture (hand-build one only if the network is unavailable, and say so in a code comment), then implement `backend/app/services/cdl.py`
    - Query up to 8 years concurrently, newest first, with a CDL code and crop name mapping
    - Set `date` to the year, `resolution_m = 30`; omit years with no value or a failed call
    - Raise `SourceUnavailable` only if every year failed; cache only when all years answered
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 4.3 Write `test_cdl.py` with `httpx.MockTransport`
    - Cases: success (at least 5 years), timeout, HTTP error, malformed response, empty result, cache hit, a year with no value dropped, partial year failure not cached
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 5. Orchestrator and endpoint
  - [x] 5.1 Implement `backend/app/farm_data.py` with `gather_farm_data`
    - Run the three services with `asyncio.gather(..., return_exceptions=True)`
    - Turn failures into unavailable entries with plain reasons and log `source=<name> error=<ExceptionClass>` only
    - _Requirements: 4.5, 5.1, 5.2, 5.4, 5.5, 17.1_
  - [x] 5.2 Add the `get_http_client` dependency and the `GET /api/farm-data` route in `backend/app/main.py`
    - Take `lat` and `lon` as optional strings, call `check_location`, return 400 with a plain message on `GeocodeError`
    - Return `{location, sources}` with status 200 otherwise
    - _Requirements: 4.5, 7.1, 7.2, 7.3_
  - [x] 5.3 Write `test_farm_data_api.py`
    - Cases: grouped response shape, partial failure, all sources down still 200, never 500 across failure modes, each invalid input returns 400 with no upstream call, concurrency (total time below the sum), every record has all seven fields
    - _Requirements: 4, 5, 7, 8.3, 8.4, 8.5_
  - [x] 5.4 Checkpoint: run the backend tests with `backend/run_tests.py` and fix failures before continuing

- [x] 6. Verify script
  - [x] 6.1 Extend `backend/verify.py` with a live farm-data check
    - Use the first farm in `config/demo_farms.json`, a temporary cache folder and `TestClient`; write one line per source (status, record count, or the reason) to `verify_report.txt`
    - _Requirements: 8.6_

- [x] 7. Frontend foundations and theme
  - [x] 7.1 Replace `frontend/src/index.css` with theme tokens, the system font stack, frosted surfaces, pill controls, focus rings, light and dark themes, reduced-motion rules and the narrow-screen bottom sheet rules
    - Check the text and boundary contrast ratios from the design for both themes
    - _Requirements: 9.1, 9.2, 9.4, 13.1, 13.2, 13.3, 14, 15.1, 15.4, 16_
  - [x] 7.2 Create `frontend/src/farmData/format.js` (`formatResolution`, value helpers) and `usePrefersReducedMotion.js`
    - _Requirements: 11.2, 11.3, 10.5, 15.4_
  - [x] 7.3 Create `frontend/src/farmData/useFarmData.js`
    - Abort the previous request on location change, ignore stale responses, expose `status`, `data`, `error` and `retry`; call only `/api/farm-data`
    - _Requirements: 12.4, 12.5, 12.6, 12.7, 17.2_

- [x] 8. Frontend panel
  - [x] 8.1 Create `SourceTag.jsx` and `ViewState.jsx` (loading, empty, error with retry button)
    - _Requirements: 11.1, 12.1, 12.2, 12.3, 12.4_
  - [x] 8.2 Create `SegmentedControl.jsx` using the ARIA tabs pattern (roving tabindex, Left/Right/Home/End keys, `aria-selected`)
    - _Requirements: 9.5, 15.2, 15.5_
  - [x] 8.3 Create `ClimateChart.jsx` and `ClimateView.jsx`
    - Line for mean temperature, bars for precipitation, labelled axes with units, tooltip on hover and focus, visually hidden text table, animation off for reduced motion
    - Large numbers with units and labels, the 50 km note, and a Source_Tag
    - Check that the installed Recharts version supports `accessibilityLayer`; if not, add focusable month controls
    - _Requirements: 9.7, 10.1, 10.2, 10.3, 10.4, 10.5, 11.4_
  - [x] 8.4 Create `SoilView.jsx` and `CropHistoryView.jsx`
    - Soil: large numbers and labelled rows, the map-unit-average note, Source_Tag
    - Crops: year and crop list, newest first, Source_Tag
    - _Requirements: 9.7, 11.1, 11.5_
  - [x] 8.5 Create `FarmDataPanel.jsx`
    - Segmented control, active view only, `aria-live` status messages for loading, loaded and error, the "supports farmer judgment" statement, collapse and expand button for narrow screens
    - _Requirements: 9.1, 9.3, 9.6, 11.6, 15.3, 16.1, 16.2, 16.3_

- [x] 9. App integration
  - [x] 9.1 Update `App.jsx`, `TerrainMap.jsx` and `LocationSearch.jsx`
    - Full-screen map, restyled Top_Bar with a short selected-place line, panel mounted and fed by `useFarmData`
    - `TerrainMap` accepts a `padding` prop used by `flyTo` so the marker is not under the panel
    - `LocationSearch` gets a visible associated label and CSS-based width; every control has an accessible name
    - Search, demo farm and map click all refresh the panel
    - _Requirements: 9.3, 12.5, 13.3, 13.4, 13.5, 15.5, 16.4_
  - [x] 9.2 Run `npm run build` in `frontend/` and fix any errors
    - _Requirements: 17.5_

- [x] 10. Final checks
  - [x] 10.1 Run the full backend test suite and `verify.py`; report each source's live status honestly, including any that failed
  - [x] 10.2 Confirm `Farmers-Helpers/` is unchanged (`git status` inside it), `backend/cache/` is ignored, and no `.env` values appear in code or logs
    - _Requirements: 6.6, 17.1, 17.4_
  - [x] 10.3 Give the user the manual frontend checklist from the design (keyboard, light and dark, reduced motion, screen reader, 375 px width, backend stopped)
