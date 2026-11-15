# Requirements Document

## Introduction

The Farm Data Panel is Task 3 of the Field Shift Rotation Explorer hackathon demo. When a farmer picks a US location, the backend gathers climate normals from NASA POWER, dominant soil facts from USDA SSURGO (Soil Data Access), and recent crop history from USDA NASS CDL (CropScape). The frontend shows these facts in a frosted, Apple-style panel floating over the full-screen 3D map.

Every fact is a feature record that names its variable, source, resolution, date, value, units, and whether it came live or from cache. The panel shows the resolution of each fact so coarse data (NASA POWER at about 50 km, SSURGO map-unit averages) is not mistaken for field-level measurement. The tool supports farmer judgment and does not replace it.

Scope: the backend FastAPI app in `backend/app/` (port 8010) and the React 18 + Vite + MapLibre + Recharts frontend in `frontend/src/`. The `Farmers-Helpers/` folder and the contents of `.env` are out of scope and remain untouched.

## Glossary

- **Backend**: The Python FastAPI application in `backend/app/`, served on port 8010.
- **Frontend**: The React 18 + Vite application in `frontend/src/`.
- **Farm_Data_API**: The Backend endpoint that returns all facts for one location.
- **Geocoder**: The existing module `app/geocode.py`, which provides coordinate parsing and the `is_in_us` check.
- **Location**: A latitude and longitude pair chosen by the user through search, a demo farm, or a map click.
- **NASA_POWER_Service**: The Backend service that retrieves monthly climate normals from NASA POWER.
- **SSURGO_Service**: The Backend service that retrieves soil facts from USDA SSURGO through Soil Data Access.
- **CDL_Service**: The Backend service that retrieves crop type by year from USDA NASS CDL (CropScape).
- **Source_Service**: Any one of NASA_POWER_Service, SSURGO_Service, or CDL_Service.
- **Feature_Record**: A single fact with the fields variable, source, resolution_m, date, value, units, and live_or_cached.
- **Unavailable_Entry**: A per-source result that states the source name and a short reason, returned in place of Feature_Records when a Source_Service fails.
- **Disk_Cache**: JSON files stored in `backend/cache/`, keyed by latitude and longitude rounded to a fixed number of decimal places.
- **Cache_Key**: The rounded latitude and longitude, plus the source name, that identifies one Disk_Cache entry.
- **Farm_Data_Panel**: The Frontend floating frosted panel that displays facts for the selected Location.
- **Segmented_Control**: The pill-shaped control in the Farm_Data_Panel that switches between Climate, Soil, and Crop history views.
- **Climate_Chart**: The Recharts chart of monthly temperature and monthly rain in the Climate view.
- **Source_Tag**: A small label on a displayed fact that shows its source, resolution, and live-or-cached status.
- **Top_Bar**: The existing Frontend header containing the title, location search, and demo-farm button.
- **Bottom_Sheet**: The Farm_Data_Panel layout used on narrow screens, anchored to the bottom of the viewport.
- **Narrow_Screen**: A viewport width below 768 px.
- **Test_Suite**: The Backend unit tests in `backend/tests/`.
- **Verify_Script**: The existing `backend/verify.py` live check script.

## Requirements

### Requirement 1: Climate normals

**User Story:** As a farmer, I want climate normals for my location, so that I can see typical temperature, rain, frost, and heat patterns.

#### Acceptance Criteria

1. WHEN the Farm_Data_API receives a valid US Location, THE NASA_POWER_Service SHALL return Feature_Records for monthly average temperature, monthly minimum temperature, monthly maximum temperature, and monthly precipitation for all 12 months.
2. WHEN the NASA_POWER_Service returns climate data, THE NASA_POWER_Service SHALL include Feature_Records for estimated frost days per year, estimated last spring frost date, estimated first fall frost date, and heat days per year above 35 Â°C.
3. WHERE solar radiation is available in the same NASA POWER response, THE NASA_POWER_Service SHALL include Feature_Records for monthly solar radiation.
4. THE NASA_POWER_Service SHALL set resolution_m to 50000 on every NASA POWER Feature_Record.
5. THE NASA_POWER_Service SHALL express temperature in Â°C, precipitation in mm, and solar radiation in kWh/mÂ²/day in the units field.
6. IF the NASA POWER response lacks the data needed to estimate a frost or heat value, THEN THE NASA_POWER_Service SHALL omit that Feature_Record and keep the remaining Feature_Records.

### Requirement 2: Soil facts

**User Story:** As a farmer, I want the main soil facts at my location, so that I can understand drainage, water holding, and erosion risk.

#### Acceptance Criteria

1. WHEN the Farm_Data_API receives a valid US Location, THE SSURGO_Service SHALL query Soil Data Access for the dominant map unit at that Location.
2. WHEN the SSURGO_Service finds a dominant map unit, THE SSURGO_Service SHALL return Feature_Records for map unit name, organic matter percent, texture, drainage class, hydrologic soil group, available water capacity, erodibility K factor, and slope range.
3. THE SSURGO_Service SHALL mark every SSURGO Feature_Record with a resolution_m value that identifies the data as a map-unit average and not a point measurement.
4. IF Soil Data Access returns no map unit for the Location, THEN THE SSURGO_Service SHALL return an Unavailable_Entry with the reason "no soil survey data for this location".
5. IF a soil property is missing for the dominant map unit, THEN THE SSURGO_Service SHALL omit that Feature_Record and keep the remaining Feature_Records.

### Requirement 3: Crop history

**User Story:** As a farmer, I want to see which crops grew at my location in recent years, so that I can plan a rotation that builds on the field history.

#### Acceptance Criteria

1. WHEN the Farm_Data_API receives a valid US Location, THE CDL_Service SHALL return one Feature_Record per year for the crop type at that Location for each of the most recent available years, up to 8 years.
2. THE CDL_Service SHALL return at least 5 years of crop history WHEN the CDL source provides at least 5 years of data.
3. THE CDL_Service SHALL set the date field of each crop Feature_Record to the CDL year.
4. THE CDL_Service SHALL set resolution_m to 30 on every CDL Feature_Record.
5. IF the CDL source returns no crop value for a year, THEN THE CDL_Service SHALL omit that year and keep the remaining years.

### Requirement 4: Feature record shape

**User Story:** As a developer, I want every fact in one consistent shape, so that the Frontend can display any fact and its provenance without special cases.

#### Acceptance Criteria

1. THE Backend SHALL represent every fact as a Feature_Record containing the fields variable, source, resolution_m, date, value, units, and live_or_cached.
2. THE Backend SHALL set live_or_cached to either "live" or "cached" on every Feature_Record.
3. WHEN a Feature_Record is served from the Disk_Cache, THE Backend SHALL set live_or_cached to "cached".
4. WHEN a Feature_Record is fetched from the upstream source during the current request, THE Backend SHALL set live_or_cached to "live".
5. THE Farm_Data_API SHALL return the results grouped by source, with each group containing either a list of Feature_Records or an Unavailable_Entry.

### Requirement 5: Partial failure tolerance

**User Story:** As a farmer, I want the app to keep working when one data source is down, so that I still see the facts that are available.

#### Acceptance Criteria

1. IF a Source_Service times out, returns an HTTP error, or returns an unparseable response, THEN THE Farm_Data_API SHALL return an Unavailable_Entry for that source and return the results of the other sources.
2. IF every Source_Service fails, THEN THE Farm_Data_API SHALL respond with HTTP status 200 and an Unavailable_Entry for each source.
3. THE Backend SHALL apply a timeout of no more than 10 seconds to each upstream request.
4. WHEN a Source_Service fails, THE Backend SHALL log the source name and error type without logging secrets.
5. WHEN the Farm_Data_API receives a request, THE Backend SHALL query the three Source_Services concurrently so that one slow source does not delay the others beyond its own timeout.

### Requirement 6: Disk cache

**User Story:** As a developer, I want repeated lookups served from disk, so that the demo stays fast and works when the network is slow.

#### Acceptance Criteria

1. WHEN a Source_Service obtains a successful live result, THE Backend SHALL write the result to the Disk_Cache under its Cache_Key.
2. THE Backend SHALL round latitude and longitude to 2 decimal places when building a Cache_Key.
3. WHEN a Disk_Cache entry exists for the Cache_Key, THE Backend SHALL return the cached entry without calling the upstream source.
4. IF a Disk_Cache file is unreadable or malformed, THEN THE Backend SHALL ignore the file and fetch the data live.
5. IF a Source_Service returns a failure, THEN THE Backend SHALL leave existing Disk_Cache entries unchanged and avoid caching the failure.
6. THE Backend SHALL store Disk_Cache files in `backend/cache/` and the repository SHALL exclude that folder from version control.

### Requirement 7: Location validation

**User Story:** As a farmer, I want clear errors for bad locations, so that I know when the tool cannot help me.

#### Acceptance Criteria

1. IF the latitude is outside -90 to 90 or the longitude is outside -180 to 180, THEN THE Farm_Data_API SHALL respond with HTTP status 400 and a plain-language message.
2. IF the Location is outside the US according to the Geocoder `is_in_us` function, THEN THE Farm_Data_API SHALL respond with HTTP status 400 and the message that the tool covers only US farms.
3. IF the latitude or longitude is missing or not a number, THEN THE Farm_Data_API SHALL respond with an HTTP 4xx status and a plain-language message.
4. THE Farm_Data_API SHALL reuse the coordinate validation and US check from the Geocoder and not duplicate them.

### Requirement 8: Offline tests and live check

**User Story:** As a developer, I want automated tests that run without the network, so that the team can trust the services and run them anywhere.

#### Acceptance Criteria

1. THE Test_Suite SHALL test the NASA_POWER_Service, SSURGO_Service, CDL_Service, Disk_Cache, and Farm_Data_API using saved fixture responses.
2. THE Test_Suite SHALL replace network calls with `httpx.MockTransport` and make no real network requests.
3. THE Test_Suite SHALL include a test for each of these cases: successful result, timeout, HTTP error, malformed response, empty result, cache hit, and partial failure across sources.
4. THE Test_Suite SHALL include a test that confirms the Farm_Data_API never responds with HTTP status 500 when upstream sources fail.
5. THE Test_Suite SHALL include a test that confirms every Feature_Record contains all seven required fields.
6. THE Verify_Script SHALL include a live check that requests the Farm_Data_API for a known demo farm and reports the status of each source.

### Requirement 9: Frosted data panel

**User Story:** As a farmer, I want the facts in a clear panel over the map, so that I can read them without losing sight of my field.

#### Acceptance Criteria

1. THE Farm_Data_Panel SHALL render as a translucent, blurred (frosted) panel on the right side of the full-screen 3D map.
2. WHILE the viewport is a Narrow_Screen, THE Farm_Data_Panel SHALL render as a Bottom_Sheet.
3. WHILE the Farm_Data_Panel is open, THE Frontend SHALL keep the 3D map visible and interactive in the area not covered by the panel.
4. THE Farm_Data_Panel SHALL use rounded corners between 12 px and 16 px and a subtle shadow.
5. THE Farm_Data_Panel SHALL contain a Segmented_Control with the three options Climate, Soil, and Crop history.
6. WHEN the user selects an option in the Segmented_Control, THE Farm_Data_Panel SHALL show only the view for that option.
7. THE Farm_Data_Panel SHALL show key facts as large numbers with their units and a text label.

### Requirement 10: Monthly climate chart

**User Story:** As a farmer, I want a monthly temperature and rain chart, so that I can see the seasonal pattern at a glance.

#### Acceptance Criteria

1. WHEN the Climate view is shown with climate data, THE Climate_Chart SHALL display monthly average temperature as a line and monthly precipitation as bars for months January to December.
2. THE Climate_Chart SHALL label its axes with units (Â°C and mm).
3. WHEN the user hovers or focuses a month on the Climate_Chart, THE Climate_Chart SHALL show that month's temperature and precipitation values.
4. THE Climate_Chart SHALL provide a text alternative that lists the monthly values for screen reader users.
5. WHERE the user prefers reduced motion, THE Climate_Chart SHALL render without animation.

### Requirement 11: Source and resolution honesty

**User Story:** As a farmer, I want to see where each number came from and how coarse it is, so that I do not mistake regional data for a field measurement.

#### Acceptance Criteria

1. THE Farm_Data_Panel SHALL show a Source_Tag with source name, resolution, and live-or-cached status next to every displayed fact or group of facts.
2. WHEN a Feature_Record has resolution_m of 1000 m or more, THE Source_Tag SHALL show the resolution in kilometres.
3. WHEN a Feature_Record has resolution_m below 1000 m, THE Source_Tag SHALL show the resolution in metres.
4. THE Climate view SHALL display a note that NASA POWER data has a resolution of about 50 km and describes the regional climate, not the field.
5. THE Soil view SHALL display a note that SSURGO values are map-unit averages and not measurements of the field.
6. THE Farm_Data_Panel SHALL display a statement that the tool supports farmer judgment and does not replace it.

### Requirement 12: Loading, empty, and error states

**User Story:** As a farmer, I want the panel to tell me what is happening, so that I am never looking at a blank or frozen screen.

#### Acceptance Criteria

1. WHILE the Farm_Data_API request is in progress, THE Farm_Data_Panel SHALL show a loading state in the active view.
2. IF a source returns an Unavailable_Entry, THEN THE Farm_Data_Panel SHALL show an error state for that source's view with the reason and a retry button, and keep the other views usable.
3. IF a source returns an empty list of Feature_Records, THEN THE Farm_Data_Panel SHALL show an empty state that explains no data exists for that location.
4. IF the Farm_Data_API request fails at the network level, THEN THE Farm_Data_Panel SHALL show an error state with a retry button.
5. WHEN the user selects a new Location through search, a demo farm, or a map click, THE Frontend SHALL request new data and refresh the Farm_Data_Panel.
6. WHEN a new Location is selected while an earlier request is still in progress, THE Frontend SHALL discard the earlier response and show data for the new Location only.
7. WHEN the user activates the retry button, THE Frontend SHALL request the data again for the current Location.

### Requirement 13: Apple-style visual language

**User Story:** As a user, I want a consistent Apple-style look across the whole app, so that the app feels polished and easy to use.

#### Acceptance Criteria

1. THE Frontend SHALL use the system font stack `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`.
2. THE Frontend SHALL use the accent colour #0071e3 for primary actions, selected states, and focus indicators.
3. THE Frontend SHALL restyle the Top_Bar, location search, and demo-farm button with the same frosted surfaces, 12 px to 16 px corners, subtle shadows, and pill-shaped controls as the Farm_Data_Panel.
4. THE Frontend SHALL contain only the map, Top_Bar, and Farm_Data_Panel and no marketing or landing-page sections.
5. THE Frontend SHALL present each text input with a visible, programmatically associated label.

### Requirement 14: Light and dark themes

**User Story:** As a user, I want light and dark themes that are readable, so that I can use the app in any lighting.

#### Acceptance Criteria

1. WHILE the operating system prefers a light colour scheme, THE Frontend SHALL apply the light theme.
2. WHILE the operating system prefers a dark colour scheme, THE Frontend SHALL apply the dark theme.
3. THE Frontend SHALL provide a text contrast ratio of at least 4.5:1 for normal text and at least 3:1 for large text and interface component boundaries in both themes.
4. THE Frontend SHALL keep text on frosted surfaces at the required contrast ratio against the surface colour over both light and dark map areas.

### Requirement 15: Keyboard and screen reader access

**User Story:** As a keyboard or screen reader user, I want to operate the whole app without a mouse, so that the tool is usable by everyone on the team and in the community.

#### Acceptance Criteria

1. THE Frontend SHALL show a visible focus indicator of at least 2 px in the accent colour on every interactive element.
2. THE Segmented_Control SHALL be operable with the Tab, Left Arrow, and Right Arrow keys and expose the selected option to assistive technology.
3. WHEN the Farm_Data_Panel changes between loading, loaded, and error states, THE Frontend SHALL announce the change through an ARIA live region.
4. WHERE the user prefers reduced motion, THE Frontend SHALL disable non-essential transitions and animations, including panel slide-in and chart animation.
5. THE Frontend SHALL give every interactive element an accessible name.

### Requirement 16: Responsive bottom sheet

**User Story:** As a farmer on a phone, I want the panel to fit my screen, so that I can read the facts in the field.

#### Acceptance Criteria

1. WHILE the viewport is a Narrow_Screen, THE Bottom_Sheet SHALL span the full viewport width and occupy no more than 60% of the viewport height.
2. WHILE the viewport is a Narrow_Screen, THE Bottom_Sheet SHALL scroll its content vertically within its own bounds.
3. WHILE the viewport is a Narrow_Screen, THE Bottom_Sheet SHALL provide a control to collapse and expand the sheet.
4. WHILE the viewport is a Narrow_Screen, THE Top_Bar SHALL fit within the viewport width without horizontal scrolling.

### Requirement 17: Secrets and simplicity

**User Story:** As a team lead, I want the project to protect secrets and stay simple, so that the demo is safe and a novice team can maintain it.

#### Acceptance Criteria

1. THE Backend SHALL keep all values from `.env` out of API responses, logs, and Frontend code.
2. THE Frontend SHALL request data only from the Backend and make no direct requests to NASA, USDA, or other upstream data services. Map tiles (the OpenFreeMap basemap and the AWS Terrarium terrain tiles) are the exception: they load directly in the browser from their public tile servers, which need no key, and they are listed with their credits in `README.md`.
3. THE Backend and Frontend source files SHALL include plain-language comments that explain the purpose of each module and each non-obvious step.
4. THE project SHALL leave all files under `Farmers-Helpers/` unchanged. (Met while this feature was built. The local clone was deleted on 2026-11-15 at the user's request; the team's copy is on GitHub.)
5. THE Frontend SHALL use only React 18, Vite, MapLibre, and Recharts for this feature, plus the packages already in `frontend/package.json`.
