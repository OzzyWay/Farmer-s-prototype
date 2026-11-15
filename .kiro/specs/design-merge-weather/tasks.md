# Implementation Plan: design-merge-weather

## Overview

Backend weather work comes first because it is independent and easy to test: `get_json` headers, `services/nws.py`, `weather_data.py`, `GET /api/weather`, tests and a live check. The frontend follows: warm earth restyle, landing, weather UI, build, Playwright checks. The backend is Python (FastAPI, pytest). The frontend is React 18 + Vite 5 (JavaScript, `node --test` for pure helpers).

## Constraints (apply to every task)

- No new npm or pip packages.
- No git commit and no push.
- Honest data: no sample or placeholder weather numbers shown as real data; every value shows its source; alert actions are suggestions.
- Do not read, print or copy values from `.env`. The NWS needs no key.
- Node is at `C:\Program Files\nodejs` and is not on PATH. Prepend it and use `npm.cmd`.
- Backend tests: `backend\run_tests.py`. They use `httpx.MockTransport` and make no real network call.
- Property tests use seeded `random` loops of at least 100 iterations (pytest or `node --test`), tagged `Feature: design-merge-weather, Property N: <title>`.
- Sub-tasks marked `*` (property tests and the helper `node --test` files) are optional. Backend unit and API tests are required. The copy test (task 6.4) is also required, because honest copy is a project rule.
- Every link to another site goes through `ExternalLink` and takes its URL from `LINKS` in `copy.js`. No component writes a URL by hand.

## Tasks

- [x] 1. NWS service (backend)
  - [~] 1.1 Add an optional `headers` parameter to `get_json`
    - In `backend/app/services/base.py`, add `headers=None` and pass it to both `client.get` calls. Existing callers stay unchanged.
    - _Requirements: 8.3, 8.4_

  - [~] 1.2 Create `backend/app/services/nws.py`
    - Named constants: `NWS`, `NWS_HEADERS` (User-Agent, no key), `FORECAST_TOTAL_TIMEOUT`, `ALERT_WINDOW_PERIODS`, `FROST_DANGER_F`, `FROST_WARN_F`, `FROST_INFO_F`, `HEAT_WARN_F`, `HEAT_DANGER_F`, `RAIN_PCT`, `WIND_INFO_MPH`, `WIND_WARN_MPH`, `HEAVY_WORDS`, source names, `SEVERITY_RANK`. Each threshold is used in one place only.
    - `OutsideCoverage(SourceUnavailable)`, `forecast_page_url`.
    - `parse_periods` (°C to °F, null rain to 0, `wind_max_mph` as largest integer or 0) and `parse_official_alerts` (level, `until` is ends else expires, `detail` joins description and instruction).
    - `farm_alerts(periods)`: pure, first 6 periods, one alert per kind from the most serious period, sorted by severity. Action texts copied from the colleague's `farmhelper/weather.py`; the wind action says it is too windy to spray.
    - `fetch_periods` (`/points/{lat:.4f},{lon:.4f}` then `properties.forecast`; a 404 from `/points` raises `OutsideCoverage`) and `fetch_official_alerts` (`/alerts/active?point=`), both through `get_json` with `NWS_HEADERS`. Log nothing here.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.9, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 9.15, 9.16, 9.17, 9.18, 10.7_

  - [~] 1.3 Add fixtures and unit tests for parsing and `farm_alerts`
    - Create `backend/tests/fixtures/nws_points.json`, `nws_forecast.json` (14 periods), `nws_forecast_celsius.json`, `nws_alerts.json`, `nws_alerts_empty.json`. Try a live probe for a Webberwood point first and save a trimmed real answer; if that is not possible, write them by hand from the documented shape and say so in the test docstring.
    - Create `backend/tests/test_nws.py`: full parse with every field of the first period; °C conversion; `farm_alerts` at each edge (night lows 28/29, 32/33, 36/37; day highs 94/95/99/100; rain 69/70 with and without heavy, thunderstorm, storm; wind 19/20/29/30); a threshold met only in period index 6 gives no alert; no night or no day period; empty result; official alert level and `until` rules; the `get_json` without `headers` case still works for an existing caller.
    - _Requirements: 13.1, 9.1 to 9.16, 8.1, 8.2_

  - [ ] 1.4 Write property tests for `farm_alerts` and parsing
    - Create `backend/tests/test_nws_properties.py` with seeded random generators of periods and NWS-shaped bodies.
    - **Property 1: Farm alerts are well formed and unique per kind**
    - **Property 2: Only the first six periods count**
    - **Property 3: Alerts match an independent threshold model** (include the boundary values 28, 32, 36, 95, 100, 70, 20, 30)
    - **Property 4: Worse weather never lowers an alert**
    - **Property 5: Period parsing keeps the facts and converts units**
    - **Property 6: Official alert parsing sets level and end time**
    - **Validates: Requirements 8.1, 8.2, 9.1 to 9.16**

- [x] 2. Weather route (backend)
  - [~] 2.1 Create `backend/app/weather_data.py`
    - `gather_weather(client, lat, lon, cache, clock=time.time)` runs the forecast and alerts parts with `asyncio.gather(..., return_exceptions=True)`.
    - Each part: try `cache.read_doc` with a freshness check (`CACHE_TTL_S = 3600`, shape check, non-empty periods), else fetch live and `write_doc` only on success. Empty official alerts are a success and are cached. Outside coverage and failures are not cached.
    - Build `{location, source, page_url, forecast, alerts}` following the combination table in the design; `farm` alerts are computed on every response; outside coverage makes both parts unavailable with the coverage reason. Reasons come from `describe_failure("National Weather Service", exc)`; a non-exception result of the wrong shape is "sent data we could not read".
    - Log one line per failed part: `log.warning("farm_data source=nws error=%s", type(exc).__name__)`. Nothing else is logged.
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8, 8.9, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [~] 2.2 Add `GET /api/weather` to `backend/app/main.py`
    - Query parameters `lat` and `lon`, validated with the same `check_location` as `/api/farm-data`; `GeocodeError` becomes HTTP 400 with the message. Uses `get_http_client` and `get_cache`. No other failure path.
    - _Requirements: 8.5, 10.1, 10.2, 10.6_

  - [~] 2.3 Add API tests to `backend/tests/test_nws.py`
    - With `httpx.MockTransport`: missing, text and out-of-range `lat`/`lon` give 400 naming the value; a valid call returns the documented shape, source name and `page_url`; `/points` 404 gives HTTP 200 with both parts unavailable; forecast chain down with alerts ok, and the reverse; `httpx.ReadTimeout` gives an unavailable part, not a 500; invalid JSON; cache hit makes no upstream call; an entry older than 3600 s (injected clock) refetches; a failed part leaves no cache file; every request carries a `User-Agent` and no API key; `/points` is requested before the forecast URL; `caplog` shows only `farm_data source=nws error=Type` with no URL or body text.
    - _Requirements: 13.1, 8.3, 8.5, 8.6, 8.7, 8.8, 8.9, 10.1, 10.3, 10.4, 10.5, 10.6_

  - [ ] 2.4 Write property tests for the route and cache
    - Append to `backend/tests/test_nws_properties.py`.
    - **Property 8: A failing part never breaks the other and never gives a 500**
    - **Property 9: Cache freshness is exactly one hour and failures are not stored**
    - **Property 10: Bad locations get a 400 that names the value**
    - **Validates: Requirements 8.6, 8.7, 8.8, 8.9, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6**

- [x] 3. Live backend check
  - [~] 3.1 Add a `/api/weather` check to `backend/verify.py`
    - Request Webberwood and check HTTP 200 and the documented keys. If the forecast part is "unavailable", report a warning with the reason, not a failure. Print no secret values.
    - _Requirements: 13.1, 8.5, 8.7_

- [~] 4. Backend checkpoint
  - Run `backend\run_tests.py` and confirm every test passes, including the existing farm-data, soil and rotation tests. Ask the user if questions arise.

- [x] 5. Warm earth restyle (frontend)
  - [~] 5.1 Create `frontend/scripts/fetch-assets.mjs`
    - Plain Node (built-in `fetch` and `fs`, no package). Steps are written in a comment at the top so they can be done by hand: request the Google Fonts CSS for Fraunces 600/700 and Inter 400/500/600/700 with a modern browser User-Agent, take the `latin` woff2 URLs, save one file per weight in `public/fonts/` (`fraunces-600.woff2`, `fraunces-700.woff2`, `inter-400.woff2`, `inter-500.woff2`, `inter-600.woff2`, `inter-700.woff2`), and download the Unsplash photo `photo-1500382017468-9049fed747ef` to `public/images/hero-field.jpg`. The photo is first requested as `https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1600&q=70&fm=jpg&fit=crop`.
    - Add a constant `HERO_MAX_BYTES = 300 * 1024` and check the saved file size against it. If the file is larger, retry in this order: `w=1400&q=70`, `w=1600&q=60`, `w=1400&q=60`. Keep the first result that fits. Print the final size and the parameters used. If none fits, keep the smallest and print a warning. No image library.
    - _Requirements: 3.1, 3.2, 14.15, 14.16_

  - [~] 5.2 Run the script and add the licence and credit files
    - Run `node scripts/fetch-assets.mjs` from `frontend/` (Node on PATH first). If it fails, follow the manual steps.
    - Add `frontend/public/fonts/OFL.txt` with the SIL OFL 1.1 text and the copyright lines of the Fraunces and Inter projects, copied from their repositories.
    - Read the photographer's name from the photo's Unsplash page and store it in a small `frontend/src/landing/credit.js` constant for the Hero credit line (not in `copy.js`, which task 6.3 creates later). Do not guess the name.
    - Add `frontend/public/images/CREDITS.txt` recording the photo's Unsplash page URL, the photographer, the date downloaded and a pointer to the Unsplash licence (https://unsplash.com/license). If the photo page does not show a free-to-use Unsplash licence, stop and ask the user before using it.
    - Report the final size of `hero-field.jpg` and the URL parameters that were used. The target is at most about 300 KB.
    - This download is a one-time dev step run by hand, not a browser request. It is the only network call outside our backend in this feature, and the app never repeats it at run time.
    - _Requirements: 3.1, 3.4, 14.15, 14.16_

  - [~] 5.3 Add colour tokens, the old-name mapping and fonts to `frontend/src/index.css`
    - Add the Palette_Light variables and `--radius: 14px`, then map every existing variable name (`--surface`, `--surface-solid`, `--surface-sunken`, `--text`, `--text-secondary`, `--accent`, `--on-accent`, `--accent-text`, `--control-border`, `--divider`, `--error`, `--chart-rain`, `--chart-temp`, plus `--accent-hover`) to the new palette with the light frosted alpha 0.92.
    - Add the `@font-face` rules (Fraunces 600/700, Inter 400/500/600/700, `font-display: swap`, local `/fonts/` paths), `--font` and `--font-display` fallback stacks, and the heading and display-number font rule.
    - Check that every variable `ClimateChart.jsx` reads through `useThemeColors` is still defined.
    - _Requirements: 1.1, 1.2, 1.7, 1.8, 3.1, 3.2_

  - [~] 5.4 Add the dark palette, re-measure contrast and write the header comment
    - Override the same names in the existing `@media (prefers-color-scheme: dark)` block with Palette_Dark (theme switching behaviour unchanged).
    - Compute the contrast ratios with the WCAG formula (a small throwaway script is fine; do not keep it as a dependency) for every pair in the design tables, including the worst case behind a frosted panel. Targets: 4.5:1 for text, 3:1 for control edges, icons, chart lines and focus rings.
    - If light `--muted` is still under 4.5:1 behind the panel, darken it to `#625f55` and re-measure. Keep `--sun` and `--line` decorative only.
    - Write the measured ratios in a comment at the top of `index.css`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 1.8_

  - [~] 5.5 Restyle cards, eyebrows, buttons, tip boxes, tabs and hard-coded colours
    - Cards: 1px `--line` border, `--card` fill, `--radius`. Eyebrow labels (`.section-heading`) uppercase in `--soil`. Primary buttons as green pills. Tip boxes (`.note`) and tabs (`.segmented`) take the styles of the colleague's `style.css` (read it from `C:\Users\juanc\Desktop\friend project\Farmers-Helpers\public\style.css`, the user's copy of the colleague's repo; read only, do not copy files from that folder into the workspace, do not add a dependency).
    - `.summary` background becomes `var(--bg)`; `.btn-primary:hover` uses `--accent-hover`; amber borders and tints in `.warn-note`, `.risks` and `.soil-flag` move to `--warn` and `--warn-soft`. `.frosted` keeps its structure.
    - Keep `:focus-visible` using `--accent`. Confirm no existing feature changed.
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 7.2_

  - [~] 5.6 Add the 44 px touch-target rules to `index.css`
    - New controls are 44 px at every width: `.landing-btn, .toast-close, .toast-more, .forecast-btn, .skip-link { min-height: 44px; min-width: 44px; }`. Links: `.help-links a, .closing-cta .ext-link, .forecast-card .nws-link { display: inline-flex; align-items: center; min-height: 44px; }`. These are new classes outside the map panel, so the desktop panel is not affected.
    - Existing controls grow on phones only: inside `@media (max-width: 767px)`, `.btn, .btn-small, .segmented button, .select, .term-btn { min-height: 44px; }` and `.btn, .btn-small { min-width: 44px; }`. The desktop panel keeps its compact look.
    - The toast close button is 44 by 44 px and draws a smaller "×" inside. Landing buttons use `.btn .landing-btn`.
    - Check that raising `.btn` at narrow widths does not break the top bar search row (the existing `flex-wrap` should handle it).
    - _Requirements: 14.20, 7.3_

- [x] 6. Landing (frontend)
  - [~] 6.1 Create `landing/scroll.js` and `landing/SkipLink.jsx`
    - `scrollToId(id, reducedMotion)` calls `scrollIntoView` with `behavior: reducedMotion ? "auto" : "smooth"` and then `focus({ preventScroll: true })`; it uses the existing `usePrefersReducedMotion` hook at the call sites.
    - `SkipLink`: first focusable element, hidden until focused, moves focus to `#map-section`. Add its styles to `index.css`.
    - _Requirements: 4.8, 6.1, 7.1, 7.2_

  - [~] 6.2 Create `landing/Hero.jsx`
    - Photo as a CSS `background-image` on `.hero` over `background-color: var(--green)` with a dark gradient overlay; kicker, lede, buttons "Go below the grass ↓" (scrolls to `#depth-story`) and "Open the field desk ↗" (scrolls to `#map-section`), and the plain-text credit line "Photo: {name} on Unsplash" using the name from `landing/credit.js` (task 5.2). The Hero holds the page `h1`. Kicker, title and lede come from `copy.hero`. Both buttons use `.btn .landing-btn`. Add styles to `index.css` (single column at 375 px). This task needs `copy.js` from task 6.3, so 6.3 runs first (see the dependency graph).
    - _Requirements: 3.4, 3.5, 4.2, 4.3, 4.4, 6.1, 7.1, 7.3, 14.2, 14.20_

  - [~] 6.3 Create `landing/copy.js` and `landing/DepthStory.jsx`
    - `copy.js` holds every Rural_Copy section as named exports plus a default export: `hero`, `depthStory`, `depthSteps` (five steps), `howItWorks`, `ruralBenefits` (`heading` "Built for rural farms" and 3 or 4 `cards` of `{title, text}`), `closingCta` (including `helpLead`) and `dataLimitations` (including `helpLead`). It also exports `allCopyStrings()`, which returns `{path, text}` for every string (and the `LINKS` labels) so tests can read the text without rendering.
    - `copy.js` also exports the `LINKS` constants with the verified URLs from the design: `extension` (`https://www.nifa.usda.gov/land-grant-colleges-and-universities-partner-website-directory`, label "Find your state extension service (USDA NIFA directory)"), `nrcs` (`https://www.nrcs.usda.gov/`, label "Natural Resources Conservation Service (NRCS)") and `serviceCenter` (`https://www.farmers.gov/working-with-us/service-center-locator`, label "Find a USDA Service Center near you"; shown in DataLimitations only). Do not use the old `offices.sc.egov.usda.gov` locator address.
    - The copy follows the draft rules in the design: plain words at about an 8th-grade reading level with sentences of at most 22 words; every technical term explained; no digits except "2030–2049" next to "Open-Meteo"; no statistic about farmers, no "underserved", no yield or income promise, no "replace" or "guarantee"; it states that the app is free with no account, that any US address gives soil, crop history, climate history and trends, rotation options and the week's weather and alerts (the 2030–2049 Open-Meteo outlook only on request and satellite greenness only for the demo farm, never claimed for every address), that the crop list is written for Central Texas, that farm alerts come with an action, the five challenge themes, and that the output is a starting point to take to the county extension agent. The hero, depthStory, howItWorks and closingCta groups each address rural or independent farmers. The five Depth_Story steps are written without digits, naming only NASA POWER, USDA SSURGO, USDA CDL, Open-Meteo outlook, MODIS NDVI and National Weather Service, with no mention of SerpApi. Check the soil wording against the fields the soil profile really holds.
    - `DepthStory`: two-column grid (one column at 375 px); sticky SVG `Depth_Scene` with five labelled bands and SVG roots; five `<article>` steps; `IntersectionObserver` with `rootMargin: "-45% 0px -45% 0px"` sets `data-active` on the step and its band (step 1 stays active when `IntersectionObserver` is missing). Highlight is a style change so it works under reduced motion; root growth transition only inside `prefers-reduced-motion: no-preference`. Section id `depth-story`, focusable with `tabIndex={-1}`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.2, 6.3, 7.3, 14.1 to 14.12, 14.21_

  - [~] 6.4 Write the copy test `frontend/tests/copy.test.mjs` (required)
    - Plain `node --test` file that imports `copy.js` and needs no rendering. This sub-task is required, not optional, because honest copy is a project rule. Seeded loops are not needed; the checks run over every string.
    - **Property 14: Depth story copy follows the honesty rules** (no digit, no "SerpApi", only named app sources).
    - **Property 15: All Rural_Copy strings are honest** (no unsourced digit, only "2030–2049" next to "Open-Meteo"; none of "SerpApi", "underserved", "guarantee", a yield or income promise, a statistic about farmers, or "replace").
    - **Property 16: The copy covers the required message** (five challenge themes, free and no account, extension agent, rural or independent farmers in hero, depthStory, howItWorks and closingCta, heading "Built for rural farms" with 3 or 4 cards).
    - **Property 17: Copy sentences stay short** (at most 22 words per sentence in every string from `allCopyStrings()`).
    - **Property 18 (data part): Every external link is safe and labelled.** Check every `LINKS` entry has an `https` href and a non-empty label, and that the three URLs equal the verified constants. The rendered anchor attributes and the presence of the links in the page are checked by Playwright in task 9.5.
    - Also fail if any string pairs "every" or "any address" with "satellite" or "outlook" (Requirement 14.4), and check that the Central Texas sentence is present (Requirement 14.27).
    - Also report the word "underserved" and any digit as separate failure messages so the verifier can report them.
    - **Validates: Requirements 5.4, 5.5, 5.6, 14.1, 14.2, 14.3, 14.7, 14.8, 14.9, 14.10, 14.11, 14.12, 14.13, 14.14, 14.21, 13.8, 13.12**

  - [~] 6.5 Create `landing/ExternalLink.jsx`
    - One component for every External_Link: `<a className="ext-link" href target="_blank" rel="noopener noreferrer">{children} <span className="ext-note">(opens in a new tab)</span></a>`. The note is visible and part of the accessible name. No icon font, no third-party script. Add its styles to `index.css` (`.ext-link`, `.ext-note`).
    - _Requirements: 14.24, 14.25, 14.26, 7.1, 7.2_

  - [~] 6.6 Create `landing/HowItWorks.jsx`
    - Three steps from `copy.howItWorks`, grid becomes one column below 768 px. Section id `how-it-works`. Add styles to `index.css`.
    - _Requirements: 4.5, 7.3, 14.2, 14.21_

  - [~] 6.7 Create `landing/RuralBenefits.jsx`
    - Placed after HowItWorks. `<section id="rural-benefits" aria-labelledby="rural-benefits-title">` with an `h2` from `copy.ruralBenefits.heading` ("Built for rural farms") and a `<ul className="benefit-grid">` with one `<li className="benefit-card">` per entry of `copy.ruralBenefits.cards` (3 to 4), each with an `h3` and the text. No props, no text of its own, no buttons, cards are not links. Add `.benefit-grid` and `.benefit-card` styles to `index.css` (one column at 375 px, card look from task 5.5).
    - _Requirements: 4.1, 14.13, 14.14, 7.3_

  - [~] 6.8 Create `landing/ClosingCta.jsx`
    - The section is `<section id="closing-cta" className="closing-cta">`. Heading "Your field is next", a lede sentence from `copy.closingCta`, a button (`.btn .landing-btn`) that calls `scrollToId("map-section", reducedMotion)`, and a "Need a person to talk to?" line from `copy.closingCta.helpLead` followed by the Extension_Link and the NRCS_Link, each rendered through `ExternalLink` with its URL and label from `LINKS`. Add styles to `index.css`.
    - _Requirements: 4.6, 6.1, 7.1, 7.3, 14.2, 14.8, 14.24, 14.26_

  - [~] 6.9 Add the links to `fieldSummary/DataLimitations.jsx`
    - Under `copy.dataLimitations.helpLead`, add a `<ul className="help-links">` with the Extension_Link, the NRCS_Link and the optional service center link, each through `ExternalLink` with URLs and labels from `LINKS`. Do not change the existing limitations text.
    - _Requirements: 14.25, 14.26, 14.8_

  - [~] 6.10 Reorder `App.jsx` and change the top-bar heading
    - Render `SkipLink`, Landing (Hero, DepthStory, HowItWorks, RuralBenefits, in this order), `#map-section` (existing `.app`, `tabIndex={-1}`, still 100vh), the FieldSummary inside its error boundary, then `ClosingCta`. The top-bar "Field Shift" `h1` becomes an `h2`-level element with unchanged look. Leave the map container untouched. The Landing renders from bundled text with no data call, so it paints before the map tiles and charts.
    - _Requirements: 4.1, 4.7, 4.8, 1.7, 7.1, 14.13, 14.17_

- [x] 7. Weather UI (frontend)
  - [x] 7.1 Create the pure helpers `weather/groupDays.js`, `weather/toasts.js` and `weather/dismissedStore.js`
    - `groupDays(periods)`: group by `start.slice(0, 10)`, at most 7 cards `{date, name, high, low, rain_pct, wind, short}`; high is the maximum day temperature and low the minimum night temperature (absent as "–" when missing); rain and wind are the larger of the two periods; text from the day period, else the night period; invent no number.
    - `orderToasts(official, farm, dismissedIds)`: official first, then farm, each group ordered danger, warn, info (a farm "danger" never goes above an official "info"); leaves out dismissed ids.
    - `loadDismissed`, `addDismissed`, `clearDismissed` on the key `fieldshift.alerts.dismissed.v1`, key format `${lat.toFixed(2)},${lon.toFixed(2)}|${YYYY-MM-DD}`; storage passed as an argument; every call in `try/catch`; earlier days dropped on write.
    - _Requirements: 11.2, 11.6, 12.2, 12.7, 12.8, 12.10, 12.11_

  - [ ] 7.2 Write `node --test` files for the helpers
    - Create `frontend/tests/groupDays.test.mjs`, `toasts.test.mjs`, `dismissedStore.test.mjs` (normal and throwing storage stubs), seeded random loops of at least 100 iterations.
    - **Property 7: Day cards use every period once and invent nothing**
    - **Property 11: Toasts are ordered, complete and respect dismissals**
    - **Property 12: Dismissed alerts round trip and stay per place and day**
    - **Property 13: Blocked storage never raises**
    - **Validates: Requirements 11.2, 11.6, 12.1, 12.2, 12.7, 12.8, 12.10, 12.11**

  - [~] 7.3 Create `weather/useWeather.js`
    - `useWeather(lat, lon)` returns `{status, data, error, retry}` with `status` of idle, loading, loaded or error. Follow `useFarmData`: request id plus `AbortController`, so a stale answer is ignored. A non-OK response or a body without `forecast` gives "error". Calls only `/api/weather`.
    - _Requirements: 11.1, 13.3_

  - [~] 7.4 Create `weather/ForecastCard.jsx` and render it in `FieldSummary`
    - Heading "Next 7 days", placed as the first section under the FieldSummary header, not gated on the rotation answer. Call `useWeather(location?.lat, location?.lon)` once in `App.jsx` and pass the result to `FieldSummary`.
    - Loading: skeleton inside `role="status"` with "Loading the forecast…" and the note "A first look at a new spot can take up to a minute on a slow connection." (the card is not behind the rotation message, so it carries its own note). The card root has class `forecast-card`. The retry button and the dismissed button use `.btn-small .forecast-btn`; the NWS page link has class `nws-link`. Unavailable or fetch error: plain reason plus a retry button, no numbers ("Could not reach the weather service" when our backend fails). Loaded: up to 7 day cards from `groupDays` (day name, high/low, rain chance, wind, short text), "Source: National Weather Service" with live or cached, and a link "Open the NWS forecast page" to `page_url` with `rel="noopener noreferrer"`. One column below 768 px. No sample numbers anywhere. Add styles to `index.css`.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 13.4, 7.1, 7.3, 14.19, 14.20, 14.22_

  - [~] 7.5 Create `weather/AlertToasts.jsx` with the dismissed hook and placement
    - Add a `useDismissed` hook (uses `dismissedStore` with in-memory state as a fallback when storage is blocked). `AlertToasts` renders a fixed container with `aria-live="polite"` and `aria-label="Weather alerts"`, one toast per alert from `orderToasts`: title, reason or text, `action` for a farm alert, expandable "More" (a button with class `toast-more`) for an official alert's `detail`, `until`, the source line, a level label ("Danger", "Warning", "Info") as well as colour, and a close button with `aria-label="Close alert: {title}"`.
    - Toasts stay until closed. Close button or Escape inside a toast closes it, records it in the store, and moves focus to the next toast's close button or to `#map-section`.
    - Placement: from 768 px, while the map section is on screen, `top: calc(var(--topbar-h) + 2 * var(--gap))` and `right: calc(var(--panel-w) + 2 * var(--gap))`; when it is scrolled out, `top: var(--gap); right: var(--gap)`. In `App.jsx`, set `--topbar-h` from the existing `useElementSize` and toggle a `map-visible` class with an `IntersectionObserver` on `#map-section`. Below 768 px the container spans the width under the top bar. `max-height: 50vh` with scroll. Fade-in only inside `prefers-reduced-motion: no-preference`. Render `AlertToasts` in `App.jsx` from the same `useWeather` result.
    - The close button uses `.toast-close` (44 by 44 px).
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.11, 6.2, 7.1, 7.2, 7.3, 13.4, 14.20, 14.22_

  - [x] 7.6 Add the dismissed restore button to `ForecastCard`
    - When one or more alerts in the current response have ids in the dismissed list, show a button "Show N dismissed alerts" (singular for 1). Activating it calls `clearDismissed` and the toasts reappear.
    - _Requirements: 12.9, 12.10, 7.1, 14.20_

- [x] 8. Frontend build
  - [~] 8.1 Run the production build
    - With `C:\Program Files\nodejs` prepended to PATH, run `npm.cmd run build` from `frontend/` and fix every error. Run `node --test tests/copy.test.mjs` (required) and, if the optional helper tests were written, `node --test tests/` as well. Confirm `package.json` and the lock file gained no new package.
    - _Requirements: 13.2, 13.5, 13.8, 13.12_

- [x] 9. Playwright checks
  - [~] 9.1 Check the landing scroll, skip link and reduced motion
    - With the backend on 8010 and Vite on 5173 started by the user or as background processes. Check both Hero buttons reach the Depth_Story and the Map_Section, the skip link moves focus to the map section, the Depth_Story highlights the step in view, and with `emulate_media` reduced motion scrolling is instant, nothing animates and the highlight still works. Mock `/api/weather` with fixtures for these runs.
    - _Requirements: 4.3, 4.4, 4.8, 5.1, 5.3, 6.1, 6.2, 6.3, 13.7_

  - [~] 9.2 Check both themes and the 375 px viewport
    - Emulate light and dark colour schemes and take a screenshot of each (landing, map section, summary). At 375 px check there is no horizontal scroll and that the Landing (including "Built for rural farms"), ForecastCard and toasts are single column. Check focus rings are visible by keyboard.
    - Touch targets at 375 px: with `browser_evaluate`, measure `getBoundingClientRect()` of every button, link and control in the Landing (Hero buttons, skip link when focused, ExternalLinks, Closing_CTA button), in the ForecastCard (retry and "Show N dismissed alerts" buttons) and in the Alert_Toasts (close buttons). Use mocked `/api/weather` answers so the controls exist. Report every element whose width or height is under 44 px, with its text, as a failure.
    - _Requirements: 2.1, 2.5, 7.2, 7.3, 13.7, 13.10, 14.20_

  - [~] 9.3 Check the toasts: open, close, remember, restore
    - With mocked `/api/weather` answers holding official and farm alerts: toasts show in the right order and place; the close button and Escape close one; after reload on the same day and place they stay closed; "Show N dismissed alerts" brings them back; blocked `localStorage` still opens and closes toasts; a forecast-unavailable answer shows the reason and no numbers. Finish with one pass against the live backend.
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 11.5, 13.7_

  - [~] 9.4 Check network requests and the console
    - Confirm no request to Google Fonts or Unsplash hosts (only same-origin assets, `/api/*` and map tiles), the fonts and photo load from `/fonts/` and `/images/`, the console error log is empty, and with the photo blocked the Hero shows the green background with readable text.
    - _Requirements: 3.3, 3.5, 13.3, 13.7_

  - [~] 9.5 Check the extension and NRCS links
    - Open the page at 1280 px and at 375 px. In the Closing_CTA and in the DataLimitations section of the FieldSummary (open it with a mocked farm answer), find the Extension_Link and the NRCS_Link and confirm each one has the exact `LINKS` href (https), `target="_blank"`, a `rel` containing `noopener` and `noreferrer`, and visible text containing "(opens in a new tab)". Confirm "Built for rural farms" shows 3 or 4 cards after "How it works" and before the map. Confirm no `<script>`, `<iframe>` or request to nifa.usda.gov, nrcs.usda.gov or farmers.gov is made until a link is clicked (check `browser_network_requests`). Do not click through.
    - _Requirements: 13.11, 14.13, 14.24, 14.25, 14.26, 4.1_

  - [~] 9.6 Check the hero image size
    - Measure `frontend/public/images/hero-field.jpg` with a PowerShell `(Get-Item ...).Length` or a short `node -e "console.log(require('fs').statSync(...).size)"`. Report the size in KB and whether it is at most about 300 KB (307200 bytes). A size above the target is reported as a warning with the size and the parameters used by `fetch-assets.mjs`, not hidden. Also confirm in Playwright that `/images/hero-field.jpg` loads from the same origin with HTTP 200.
    - _Requirements: 13.9, 14.15, 14.16, 3.1_

- [~] 10. Final checkpoint
  - Re-run `backend\run_tests.py`, `npm.cmd run build`, `node --test tests/copy.test.mjs` (required) and the optional `node --test` files if they were written. Confirm no commit or push was made and no `.env` value was read. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (property tests and the helper `node --test` files). Backend unit and API tests (1.3, 2.3) and the copy test (6.4) are required.
- Numbering change: the old tasks 6.5 and 6.6 are now 6.6 (HowItWorks), 6.8 (ClosingCta) and 6.10 (App.jsx reorder). New tasks are 5.6, 6.5, 6.7, 6.9, 9.5 and 9.6. Task 6.2 (Hero) needs `copy.js` from 6.3, so 6.3 runs first.
- Each task references requirement numbers for traceability. Property numbers refer to the Correctness Properties in `design.md`.
- Checkpoints 4 and 10 ensure incremental validation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1", "7.1"] },
    { "id": 1, "tasks": ["1.2", "5.2", "7.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1", "5.3"] },
    { "id": 3, "tasks": ["2.2", "5.4"] },
    { "id": 4, "tasks": ["2.3", "2.4", "3.1", "5.5"] },
    { "id": 5, "tasks": ["5.6", "7.3"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["6.3"] },
    { "id": 8, "tasks": ["6.2", "6.4"] },
    { "id": 9, "tasks": ["6.5"] },
    { "id": 10, "tasks": ["6.6"] },
    { "id": 11, "tasks": ["6.7"] },
    { "id": 12, "tasks": ["6.8"] },
    { "id": 13, "tasks": ["6.9"] },
    { "id": 14, "tasks": ["6.10"] },
    { "id": 15, "tasks": ["7.4"] },
    { "id": 16, "tasks": ["7.5"] },
    { "id": 17, "tasks": ["7.6"] },
    { "id": 18, "tasks": ["8.1", "9.6"] },
    { "id": 19, "tasks": ["9.1"] },
    { "id": 20, "tasks": ["9.2"] },
    { "id": 21, "tasks": ["9.3"] },
    { "id": 22, "tasks": ["9.4"] },
    { "id": 23, "tasks": ["9.5"] }
  ]
}
```
