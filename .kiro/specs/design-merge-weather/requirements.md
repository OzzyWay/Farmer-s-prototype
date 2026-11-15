# Requirements Document

## Introduction

This feature merges the visual design and the weather features of the colleague's Farmers-Helpers project into the Field Shift: Rotation Explorer app. It has three parts: (1) a warm earth restyle of the React/Vite frontend, in light and dark themes; (2) a landing section placed above the map on the same page; (3) a new National Weather Service (NWS) backend service and route, with a "Next 7 days" forecast card and pop-up alert toasts in the frontend. The target users are rural US farmers, including small and independent farmers who may have no crop consultant, agronomist or nearby extension office visit; the Landing copy and the practical fit of the app address them. All existing features and backend behaviour stay unchanged. The sample Texas region panel, the scripted chat assistant, Leaflet, Chart.js and SerpApi are not part of this feature. Data is US only. The tool supports farmer judgment and does not replace local expertise.

## Glossary

- **Frontend**: The React 18 + Vite 5 single-page app in `frontend/`.
- **Backend**: The FastAPI app in `backend/` serving on port 8010.
- **Theme**: The light or dark colour scheme of the Frontend, selected through CSS variables.
- **Palette_Light**: The light Theme colours: --bg #f3f1e9, --card #fffefa, --ink #22231f, --muted #6a675d, --line #d9d4c8, --green #385943, --green-soft #e1e9df, --leaf #688752, --soil #76533a, --soil-soft #eee3d7, --sun #b89556, --warn #93583c, --warn-soft #f0e2d8, --info #536f5d, --info-soft #e3e9e1, with a corner radius of 14px.
- **Palette_Dark**: A warm dark earth set of the same variable names, defined in `frontend/src/index.css`.
- **Landing**: The sections above the map: Hero, Depth_Story, How_It_Works and Rural_Benefits_Section.
- **Rural_Benefits_Section**: The short "Built for rural farms" Landing section after How_It_Works and before the Map_Section, holding 3 to 4 Benefit_Cards.
- **Benefit_Card**: One card in the Rural_Benefits_Section with a short title and one or two plain-language sentences.
- **Rural_Copy**: All new Landing text written for this requirement set: the Hero kicker and lede, the Depth_Story text, the How_It_Works text, the Rural_Benefits_Section text and the Closing_CTA text.
- **Copy_File**: `frontend/src/landing/copy.js`, the single file that holds the Rural_Copy so that tests can read it.
- **Unsourced_Digit**: A digit character in the Rural_Copy that is not part of a number with a cited source in the same Benefit_Card or paragraph.
- **Extension_Link**: A static link to the USDA NIFA land-grant university extension directory, for finding the county extension office.
- **NRCS_Link**: A static link to the USDA Natural Resources Conservation Service, for conservation and soil help.
- **External_Link**: A plain anchor that opens in a new tab with rel="noopener noreferrer", is labelled as external, and loads no third-party script.
- **Touch_Target**: A tappable control whose rendered height and width are each at least 44 px.
- **Hero**: The first Landing section with the photo, kicker, lede and two buttons.
- **Depth_Story**: The "Below the grass line" scroll story with a sticky Depth_Scene and five steps.
- **Depth_Scene**: The sticky SVG scene with bands for the grass line, topsoil, subsoil, parent material and bedrock, and SVG roots.
- **How_It_Works**: The Landing section with three steps.
- **Map_Section**: The existing 100vh map section followed by the FieldSummary.
- **Closing_CTA**: The "Your field is next" call-to-action section after the FieldSummary.
- **Self_Hosted_Assets**: The Fraunces (weights 600 and 700) and Inter (weights 400 to 700) font files and the Hero photo, stored in `frontend/public/`.
- **NWS_Service**: The new Backend module that reads api.weather.gov.
- **Weather_Route**: The Backend endpoint `GET /api/weather` with query parameters `lat` and `lon`.
- **Forecast_Day**: One calendar day of the NWS forecast, built from its day period and night period, with day name, high, low, wind, precipitation chance and short text.
- **Official_Alert**: An active NWS alert for the location.
- **Farm_Alert**: An alert derived by the Backend from the first 6 NWS 12-hour periods, of kind frost_freeze, extreme_heat, heavy_rain_storm or wind_spray, with a level, a title, a reason and an action to take.
- **Forecast_Card**: The Frontend card titled "Next 7 days".
- **Alert_Toast**: A pop-up notification in the Frontend that shows one Official_Alert or Farm_Alert.
- **Dismissed_Store**: Browser storage that remembers dismissed Alert_Toasts per location and calendar day.
- **Location_Key**: The latitude and longitude rounded to 2 decimals.
- **Disk_Cache**: The existing `DiskCache` in `backend/app/cache.py`.
- **Source_Helpers**: The existing `backend/app/services/base.py` functions `get_json`, `SourceUnavailable` and `describe_failure`, with a 10 s timeout.

## Requirements

### Requirement 1: Warm earth restyle

**User Story:** As a farmer, I want the app to use a warm earth look, so that it feels like one consistent product.

#### Acceptance Criteria

1. THE Frontend SHALL define the Palette_Light values as CSS variables on the root element in `frontend/src/index.css`.
2. THE Frontend SHALL render display headings in Fraunces and body text in Inter.
3. THE Frontend SHALL render cards with a 1px border in --line, the fill --card and a corner radius of 14px.
4. THE Frontend SHALL render eyebrow labels in uppercase using the colour --soil.
5. THE Frontend SHALL render primary buttons as green pills using --green.
6. THE Frontend SHALL render tip boxes and tabs in the styles taken from the colleague's `style.css`.
7. THE Frontend SHALL keep every feature present before this change, including the map, location search, FieldSummary, charts and the rotation views.
8. THE Frontend SHALL keep the `.frosted` map panels and the Recharts colours working through CSS variables in both Themes.

### Requirement 2: Dark mode

**User Story:** As a farmer, I want a dark mode with the same warm feel, so that I can read the app comfortably at night.

#### Acceptance Criteria

1. WHEN the user selects the dark Theme, THE Frontend SHALL apply Palette_Dark to all Frontend surfaces, text, borders and charts.
2. THE Frontend SHALL give body text a contrast ratio of at least 4.5:1 against its background in both Themes.
3. THE Frontend SHALL give UI component boundaries, icons and focus rings a contrast ratio of at least 3:1 against adjacent colours in both Themes.
4. THE Frontend SHALL list the measured contrast ratios of the colour pairs in a comment in `frontend/src/index.css`.
5. WHEN the user changes the Theme, THE Frontend SHALL keep the Theme choice behaviour that existed before this change.

### Requirement 3: Self-hosted fonts and photo

**User Story:** As a site operator, I want fonts and the hero photo served from our own app, so that the browser makes no third-party requests for them.

#### Acceptance Criteria

1. THE Frontend SHALL serve Self_Hosted_Assets from `frontend/public/` at same-origin paths.
2. THE Frontend SHALL declare Fraunces 600 and 700 and Inter 400, 500, 600 and 700 with `@font-face` rules that use local paths.
3. WHEN the Frontend loads in a browser, THE Frontend SHALL make no request to Google Fonts or Unsplash hosts.
4. THE Hero SHALL show a photo credit line naming the photographer and source of the Hero photo.
5. IF the Hero photo fails to load, THEN THE Hero SHALL show a plain colour background from --green with readable text.

### Requirement 4: Landing before the map

**User Story:** As a visitor, I want a landing page before the map, so that I understand what the tool does before I use it.

#### Acceptance Criteria

1. THE Frontend SHALL render the Hero, then the Depth_Story, then the How_It_Works, then the Rural_Benefits_Section, then the Map_Section, then the FieldSummary, then the Closing_CTA on the same page in this order.
2. THE Hero SHALL show the photo, a kicker, a lede, a button labelled "Go below the grass ↓" and a button labelled "Open the field desk ↗".
3. WHEN the user activates "Go below the grass ↓", THE Frontend SHALL scroll to the Depth_Story.
4. WHEN the user activates "Open the field desk ↗", THE Frontend SHALL scroll to the Map_Section.
5. THE How_It_Works SHALL show three steps.
6. THE Closing_CTA SHALL show the heading "Your field is next" and a button that scrolls to the Map_Section.
7. THE Map_Section SHALL keep a height of 100vh.
8. THE Frontend SHALL provide a skip link as the first focusable element that moves focus to the Map_Section.

### Requirement 5: Below the grass line story

**User Story:** As a visitor, I want a scroll story about what lies below the grass, so that I see why soil data matters for rotation choices.

#### Acceptance Criteria

1. THE Depth_Scene SHALL stay sticky while the five Depth_Story steps scroll.
2. THE Depth_Scene SHALL show bands labelled grass line, topsoil, subsoil, parent material and bedrock, and SVG roots.
3. WHEN a Depth_Story step is the one in view, THE Frontend SHALL highlight that step and its matching band of the Depth_Scene.
4. THE Depth_Story text SHALL name only data sources that the app uses: NASA POWER, USDA SSURGO, USDA CDL, Open-Meteo outlook, MODIS NDVI and National Weather Service.
5. THE Depth_Story text SHALL contain no reference to SerpApi.
6. THE Depth_Story text SHALL state no numeric value as a measured fact about a real farm.

### Requirement 6: Reduced motion

**User Story:** As a user who is sensitive to motion, I want the page to respect my system setting, so that nothing animates or glides.

#### Acceptance Criteria

1. WHILE the user's system setting prefers-reduced-motion is reduce, THE Frontend SHALL use instant jumps instead of smooth scrolling for all scroll buttons.
2. WHILE the user's system setting prefers-reduced-motion is reduce, THE Frontend SHALL play no CSS or script animation in the Landing, the Depth_Scene and the Alert_Toasts.
3. WHILE the user's system setting prefers-reduced-motion is reduce, THE Depth_Story SHALL still highlight the step in view.

### Requirement 7: Keyboard and small screens

**User Story:** As a keyboard user, I want to reach every control, so that I can use the page without a mouse.

#### Acceptance Criteria

1. THE Frontend SHALL make every Landing button, link, the skip link, forecast controls and Alert_Toast controls reachable and operable with the keyboard.
2. THE Frontend SHALL show a visible focus ring on each focusable element in both Themes.
3. WHEN the viewport is 375 px wide, THE Frontend SHALL render the Landing, the Forecast_Card and the Alert_Toasts in a single column without horizontal scrolling.

### Requirement 8: NWS forecast and alerts service

**User Story:** As a farmer, I want the app to fetch the National Weather Service forecast and alerts for my field, so that I can plan work for the coming week.

#### Acceptance Criteria

1. WHEN the Weather_Route receives valid `lat` and `lon`, THE NWS_Service SHALL return the NWS forecast periods (up to 14 twelve-hour periods, about 7 days), which the Frontend groups into at most 7 Forecast_Days.
2. WHEN the Weather_Route receives valid `lat` and `lon`, THE NWS_Service SHALL return the active Official_Alerts for that point.
3. THE NWS_Service SHALL send a User-Agent header on every request to api.weather.gov and no API key.
4. THE NWS_Service SHALL make requests through the Source_Helpers with a 10 s timeout.
5. THE Weather_Route SHALL return the source name "National Weather Service" and the URL of the NWS forecast page for the location.
6. IF the location is outside NWS coverage, THEN THE Weather_Route SHALL return HTTP 200 with the forecast and alerts marked unavailable and a plain-language reason.
7. IF api.weather.gov fails or times out, THEN THE Weather_Route SHALL return HTTP 200 with the failed part marked unavailable and a plain-language reason from `describe_failure`.
8. IF the forecast part fails and the alerts part succeeds, THEN THE Weather_Route SHALL return the alerts and mark only the forecast unavailable, and the same rule applies in the opposite case.
9. THE NWS_Service SHALL write no request URL and no response body to logs.

### Requirement 9: Derived farm alerts

**User Story:** As a farmer, I want clear farm alerts with an action to take, so that I can protect crops and work safely.

#### Acceptance Criteria

1. THE NWS_Service SHALL look for Farm_Alerts only in the first ALERT_WINDOW_PERIODS (6) NWS 12-hour forecast periods, about 3 days, and SHALL create at most one Farm_Alert per kind, built from the most serious period of that kind.
2. WHEN the coldest night period in the window has a temperature at or below FROST_DANGER_F (28 °F), THE NWS_Service SHALL create a frost_freeze Farm_Alert of level "danger" titled "Hard freeze".
3. WHEN the coldest night period in the window has a temperature above FROST_DANGER_F and at or below FROST_WARN_F (32 °F), THE NWS_Service SHALL create a frost_freeze Farm_Alert of level "warn" titled "Freeze".
4. WHEN the coldest night period in the window has a temperature above FROST_WARN_F and at or below FROST_INFO_F (36 °F), THE NWS_Service SHALL create a frost_freeze Farm_Alert of level "info" titled "Frost possible".
5. WHEN the coldest night period in the window has a temperature above FROST_INFO_F, or the window has no night period, THE NWS_Service SHALL create no frost_freeze Farm_Alert.
6. WHEN the hottest day period in the window has a temperature at or above HEAT_DANGER_F (100 °F), THE NWS_Service SHALL create an extreme_heat Farm_Alert of level "danger" titled "Extreme heat".
7. WHEN the hottest day period in the window has a temperature at or above HEAT_WARN_F (95 °F) and below HEAT_DANGER_F, THE NWS_Service SHALL create an extreme_heat Farm_Alert of level "warn" titled "Heat".
8. WHEN the period with the highest precipitation chance in the window has a chance at or above RAIN_PCT (70 percent), THE NWS_Service SHALL create a heavy_rain_storm Farm_Alert.
9. WHEN that period's short or detailed forecast text matches heavy, thunderstorm or storm, THE NWS_Service SHALL give the heavy_rain_storm Farm_Alert the level "warn" and the title "Storms likely"; otherwise THE NWS_Service SHALL give it the level "info" and the title "Rain likely".
10. THE NWS_Service SHALL take wind_max_mph of a period as the largest number in its windSpeed text, and SHALL use 0 when the text has no number.
11. WHEN the period with the highest wind_max_mph in the window has a value at or above WIND_INFO_MPH (20 mph), THE NWS_Service SHALL create a wind_spray Farm_Alert of level "info"; WHEN that value is at or above WIND_WARN_MPH (30 mph), THE NWS_Service SHALL give the Farm_Alert the level "warn". The action text SHALL say it is too windy to spray.
12. THE NWS_Service SHALL define ALERT_WINDOW_PERIODS, FROST_DANGER_F, FROST_WARN_F, FROST_INFO_F, HEAT_WARN_F, HEAT_DANGER_F, RAIN_PCT, WIND_INFO_MPH and WIND_WARN_MPH as named constants, each used in one place only.
13. THE Farm_Alert SHALL carry the fields id, source, level, title, reason, action and until, where source is "Based on NWS forecast", action is the plain-language action text copied from the colleague's `farmhelper/weather.py` for its kind and level, and until is the start time of the period it was built from.
14. WHEN no threshold is met, THE NWS_Service SHALL return an empty list of Farm_Alerts.
15. THE NWS_Service SHALL read Official_Alerts from `GET /alerts/active?point=lat,lon` and SHALL give each the fields id, title (the NWS event), text (the headline), detail (the description and instruction joined), until (ends, or expires when ends is empty), level and source "National Weather Service", where level is "danger" for NWS severity extreme or severe and "warn" otherwise.
16. THE NWS_Service SHALL read the forecast by calling `GET /points/{lat:.4f},{lon:.4f}`, then the `properties.forecast` URL it returns, and SHALL give each period the fields name, start, is_day, temp_f (converted from °C when the unit is C), rain_pct, wind, wind_max_mph, short and detail.
17. IF `GET /points/...` answers HTTP 404, THEN THE NWS_Service SHALL treat the location as outside NWS coverage.
18. THE Weather_Route SHALL return the forecast page link `https://forecast.weather.gov/MapClick.php?lat={lat:.4f}&lon={lon:.4f}`.
### Requirement 10: Weather route validation and caching

**User Story:** As a developer, I want the weather route to validate input and cache results, so that it behaves like the existing farm-data route and stays within free limits.

#### Acceptance Criteria

1. IF `lat` or `lon` is missing, not a number, or outside the valid range, THEN THE Weather_Route SHALL return HTTP 400 with a message that names the bad value.
2. THE Weather_Route SHALL apply the same location validation as `/api/farm-data`.
3. THE NWS_Service SHALL store each successful result in the Disk_Cache with a freshness of 1 hour.
4. WHEN a cached result is fresh, THE Weather_Route SHALL return it without calling api.weather.gov.
5. THE Weather_Route SHALL not store a failed part in the Disk_Cache.
6. THE Weather_Route SHALL not return HTTP 500 for any upstream failure.
7. THE Backend SHALL add no new pip package for this feature.

### Requirement 11: Next 7 days forecast card

**User Story:** As a farmer, I want a "Next 7 days" card, so that I can see the forecast beside my field data.

#### Acceptance Criteria

1. WHEN the Frontend has a selected location, THE Frontend SHALL request the Weather_Route through the Backend only.
2. THE Forecast_Card SHALL show each Forecast_Day with the day name, temperature, wind, precipitation chance and short text.
3. THE Forecast_Card SHALL show the source "National Weather Service" and a link to the NWS forecast page.
4. WHILE the Weather_Route request is pending, THE Forecast_Card SHALL show a loading state announced to assistive technology.
5. IF the forecast is unavailable, THEN THE Forecast_Card SHALL show the plain-language reason and no forecast numbers.
6. THE Frontend SHALL show no sample or placeholder weather numbers as real data.

### Requirement 12: Alert toasts

**User Story:** As a farmer, I want alert pop-ups when the forecast loads, so that I see urgent weather without searching for it.

#### Acceptance Criteria

1. WHEN the forecast loads with at least one alert, THE Frontend SHALL show one Alert_Toast per alert at the top right of the viewport, or, while the map is on screen, at the top right of the part of the map that the data panel does not cover.
2. THE Frontend SHALL order Alert_Toasts with Official_Alerts first and Farm_Alerts after them, and SHALL order the alerts within each of those two groups by level: danger, then warn, then info.
3. THE Alert_Toast SHALL show the alert title, the reason or description, the action to take for a Farm_Alert, and the source.
4. THE Alert_Toast container SHALL use aria-live polite.
5. THE Frontend SHALL keep each Alert_Toast visible until the user closes it.
6. WHEN the user activates the close button of an Alert_Toast or presses Escape while focus is inside it, THE Frontend SHALL close that Alert_Toast.
7. WHEN the user closes an Alert_Toast, THE Frontend SHALL record it in the Dismissed_Store under the Location_Key and the current calendar day.
8. WHEN the forecast loads again for the same Location_Key on the same calendar day, THE Frontend SHALL not show Alert_Toasts recorded in the Dismissed_Store.
9. WHERE at least one alert for the current location is dismissed, THE Forecast_Card SHALL show a button that shows the dismissed alerts again.
10. WHEN the user activates that button, THE Frontend SHALL show the dismissed Alert_Toasts again and remove them from the Dismissed_Store.
11. IF browser storage is unavailable, THEN THE Frontend SHALL still show and close Alert_Toasts without error.

### Requirement 13: Verification and constraints

**User Story:** As a maintainer, I want the work verified and constrained, so that the demo stays stable and honest.

#### Acceptance Criteria

1. THE Backend SHALL include unit and API tests for the NWS_Service and the Weather_Route that use `httpx.MockTransport` fixtures and make no real network call.
2. THE Frontend SHALL add no new npm package, and `npm.cmd run build` SHALL complete with no error.
3. THE Frontend SHALL call only the Backend for data, with map tiles as the only documented exception, and same-origin requests for Self_Hosted_Assets.
4. THE Frontend SHALL show the source next to every data value on the Forecast_Card and the Alert_Toasts.
5. THE Frontend SHALL exclude the sample Texas region panel, the scripted chat assistant, Leaflet, Chart.js and SerpApi.
6. THE feature work SHALL leave the git repository without a new commit or push.
7. WHEN verifying the Frontend, THE verifier SHALL run Playwright checks for the landing scroll, reduced motion, both Themes, a 375 px viewport, Alert_Toast open, close and remember behaviour, and an empty browser console error log.
8. WHEN verifying Requirement 14, THE verifier SHALL run a copy test that reads the Copy_File and reports any Unsourced_Digit in the Rural_Copy and any occurrence of "SerpApi" in the Rural_Copy.
9. WHEN verifying Requirement 14, THE verifier SHALL measure the file size of the Hero photo in `frontend/public/` and report whether the size is at most about 300 KB.
10. WHEN verifying Requirement 14, THE verifier SHALL run a Playwright check at a 375 px viewport that measures every Landing button, Forecast_Card control and Alert_Toast control and reports any Touch_Target smaller than 44 px.
11. WHEN verifying Requirement 14, THE verifier SHALL check that the Closing_CTA and the DataLimitations or footer each contain the Extension_Link and the NRCS_Link as External_Links.
12. WHEN verifying Requirement 14, THE verifier SHALL check that the Rural_Copy contains no use of the word "underserved" without a cited source.

### Requirement 14: Rural farmer focus

**User Story:** As a rural or small independent farmer without a nearby crop consultant, agronomist or extension office visit, I want the page to speak to my situation and work on my connection and phone, so that I can use free field data to prepare my own decisions.

#### Acceptance Criteria

1. THE Rural_Copy SHALL address rural and small or independent farmers who may have no crop consultant, agronomist or nearby extension office visit.
2. THE Hero kicker and lede, the Depth_Story text, the How_It_Works text and the Closing_CTA text SHALL each carry the rural farmer message in the Copy_File.
3. THE Rural_Copy SHALL state that the app is free and needs no account and no sign-up.
4. THE Rural_Copy SHALL state that any US address gives soil, crop history, climate history and trends, rotation options, and the week's weather and alerts; that the 2030–2049 outlook can be loaded on request; and that satellite greenness is shown for the demo farm. THE Rural_Copy SHALL NOT claim that every address gets the outlook or satellite greenness. *(Corrected 2026-11-15: the outlook is precomputed only for the demo farm and loads on request elsewhere, about one new place per hour; MODIS greenness is prepared for demo farms only.)*
5. THE Rural_Copy SHALL state that the app shows rotation options for water, soil health, forage and income, with the reasons shown.
6. THE Rural_Copy SHALL state that farm alerts come with an action to take for frost, heat, storms and wind too strong to spray.
7. THE Rural_Copy SHALL tie the app to the challenge themes of shifting temperatures, changing rainfall, water shortages, extreme weather and declining soil health.
8. THE Rural_Copy SHALL describe the app output as a starting point to take to the county extension agent.
9. THE Rural_Copy SHALL contain no Unsourced_Digit, and a number SHALL appear only with a cited source next to it.
10. THE Rural_Copy SHALL contain no statistic about rural farmers without a cited source, no promise of yield or income, and no claim that the app replaces local expertise.
11. THE Rural_Copy SHALL contain no use of the word "underserved" without a cited source.
12. THE Copy_File SHALL hold the Rural_Copy so that a test can read the text without rendering the page.
13. THE Frontend SHALL render the Rural_Benefits_Section after the How_It_Works and before the Map_Section, with the heading "Built for rural farms" and 3 to 4 Benefit_Cards.
14. THE Rural_Benefits_Section SHALL take its text from the Copy_File and follow the honesty rules of acceptance criteria 9 to 11.
15. THE Frontend SHALL serve the fonts and the Hero photo from `frontend/public/` so that slow or patchy connections make no third-party font or photo request.
16. THE Hero photo SHALL be compressed to a target file size of at most about 300 KB, and IF the Hero photo fails to load, THEN THE Hero SHALL show the plain --green background of Requirement 3.
17. THE Frontend SHALL render the Landing text and the core FieldSummary text before the map tiles and charts finish loading.
18. WHEN a lookup for a field is repeated, THE Backend SHALL answer from the Disk_Cache while the cached result is fresh.
19. WHILE a first lookup for a field is pending, THE Frontend SHALL show a loading message that says a first lookup can take up to a minute.
20. WHEN the viewport is 375 px wide, THE Frontend SHALL render every Landing button and link, every Forecast_Card control and every Alert_Toast control as a Touch_Target.
21. THE Rural_Copy SHALL be written at about an 8th-grade reading level and SHALL explain each technical term in plain words, and the Frontend MAY reuse the existing TermInfo explanations for that purpose.
22. WHILE the rotation answer is pending or has failed, THE Forecast_Card and the Alert_Toasts SHALL stay usable, because the Forecast_Card does not depend on the rotation answer.
23. THE Frontend SHALL need no account, no payment and no key entered by the farmer for any feature.
24. THE Closing_CTA SHALL contain the Extension_Link and the NRCS_Link as External_Links.
25. THE DataLimitations section or the page footer SHALL contain the Extension_Link and the NRCS_Link as External_Links.
26. THE Extension_Link and the NRCS_Link SHALL be static anchors that load no third-party script.
27. THE Rural_Copy SHALL state that the crop list is written for Central Texas, so rotation options elsewhere are rough ideas.
