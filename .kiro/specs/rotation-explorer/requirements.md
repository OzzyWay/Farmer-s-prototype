# Requirements Document

## Introduction

The Rotation Explorer is the next feature of the Field Shift hackathon demo. It answers the challenge question: which crop rotations could protect this field, conserve water and build soil health under its climate?

Below the full-screen 3D map, the farmer scrolls into a "Your field at a glance" section. It shows:

1. A 3D soil block built from the real soil layers at the selected location.
2. Short plain-language findings drawn from the existing climate, soil and crop history data.
3. A set of farmer priorities and constraints the farmer can change.
4. At least three rotation strategies compared side by side, including the current rotation. Each one explains why it was suggested, the evidence, the benefits, the risks to review locally, and the information gaps.

Suggestions come from transparent rules applied to a small, sourced crop table. There is no black-box model, so every suggestion can be traced to a number and a source. The tool supports farmer judgment and local expertise and does not replace them.

The feature focuses on the pressures named in the challenge: shifting temperatures, changing rainfall, water shortage, extreme weather and declining soil health. It shows how these have changed at the field since 1981 (NASA POWER daily data) and what climate models project up to 2050 (Open-Meteo Climate API), and it scores each rotation against both today's conditions and the projected outlook. It does not forecast the weather of any single future year.

### Phases

The hackathon deadline is within 48 hours, so the requirements are split in two phases.

- **Phase 1 (deadline):** Requirements 1 to 18, 21 and 23. Field summary, 3D soil block, findings, crop table, current rotation, at least three strategies with explanations and scores, priorities, calendar strip, climate trends since 1981, the Open-Meteo outlook, MODIS NDVI bare-soil and crop-stress months, and NASA satellite water data (IMERG rain, GRACE-based soil moisture and groundwater, SMAP soil moisture where reachable).
- **Phase 2 (after the deadline):** Requirements 19, 20 and 22. NASA NEX-GDDP-CMIP6 projection precomputed for demo farms, the advanced soil-test form, and USDA Quick Stats county crops and prices.

Requirements 21 and 23 were moved into Phase 1 on 2026-11-15 after a review found that NASA POWER was the only NASA product in use, while the challenge is "Adapting Farms with NASA Data".

Phase 2 requirements are written now so the Phase 1 design leaves room for them, but they are not built before the deadline.

Scope: the backend FastAPI app in `backend/app/` and the React frontend in `frontend/src/`, building on the farm-data-panel feature (`/api/farm-data`, Feature_Records, Disk_Cache). The contents of `.env` are out of scope and remain untouched. (The old `Farmers-Helpers/` clone was deleted from the workspace on 2026-11-15 at the user's request; nothing here depends on it.)

## Glossary

- **Field_Summary**: The scrollable section below the map that contains the Soil_Block, Findings, Priority_Picker and Strategy_Cards.
- **Soil_Profile**: The list of soil layers (horizons) of the dominant soil component at a Location, each with top depth, bottom depth, texture and properties, from USDA SSURGO.
- **Soil_Block**: The interactive 3D cutaway of the Soil_Profile, drawn with CSS 3D transforms.
- **Finding**: A short plain-language statement about the field, such as "Heavy clay that soaks up water slowly", linked to the value and source it came from.
- **Crop_Table**: A data file in the repository that describes each candidate crop with sourced attributes.
- **Crop_Entry**: One crop in the Crop_Table.
- **Current_Rotation**: The rotation inferred from the CDL crop history at the Location.
- **Strategy**: A rotation option: a named sequence of crops placed on a 12-month calendar.
- **Strategy_Card**: The frontend card that presents one Strategy.
- **Rotation_Engine**: The backend module that infers the Current_Rotation, builds candidate Strategies, filters out unsuitable crops and scores the rest.
- **Rotation_API**: The backend endpoint that returns Findings, the Soil_Profile and Strategies for one Location and one set of Priorities.
- **Priority**: A farmer goal the farmer can switch on or off: save water, build soil, livestock forage, extra income, fewer field passes.
- **Constraint**: A farmer limit: irrigation available or not, livestock on the farm or not, no-till only or not.
- **Priority_Picker**: The frontend control for choosing Priorities and Constraints.
- **Site_Facts**: The values the Rotation_Engine uses, taken from the farm-data sources: frost days, last and first frost dates, heat days, monthly rain, wettest month, hydrologic group, drainage class, flooding frequency, slope, organic matter, available water capacity and erodibility K.
- **Calendar_Strip**: The 12-month bar on a Strategy_Card that shows what is in the ground each month, bare-soil months and heat-stress months.
- **Exclusion**: A crop the Rotation_Engine ruled out for this Location, with the reason.
- **Confidence**: A label of high, medium or low on a Strategy, based on how many of the Site_Facts it depends on were available.
- **Map_Scroll_Mode**: How the mouse wheel behaves over the map: with Ctrl held it zooms the map, without Ctrl it scrolls the page.
- **Climate_Indicator**: A yearly value computed from daily data that measures one challenge pressure, such as days above 35 °C or the longest dry spell.
- **Climate_Trend**: The change in a Climate_Indicator over the years 1981 to the last complete year, expressed per decade, with a statement of whether the change is clear or within normal year-to-year variation.
- **Outlook**: The projected value of a Climate_Indicator for a future period (2030–2049) from climate models, shown as a range across models.
- **Outlook_Source**: Which projection the Outlook comes from: "Open-Meteo" (default) or "NASA NEX-GDDP-CMIP6" (Phase 2, precomputed for demo farms).
- **Soil_Test**: Lab results the farmer enters in Phase 2: pH, organic matter percent, phosphorus, potassium, test date and sample depth.

## Requirements

### Requirement 1: Field summary below the map

**User Story:** As a farmer, I want to scroll down from the map to a summary of my field, so that I can read what the data means without losing the map.

#### Acceptance Criteria

1. THE Frontend SHALL place the Field_Summary below the full-screen map so the page scrolls vertically from the map to the Field_Summary.
2. THE Frontend SHALL show a "Your field summary" button over the map that scrolls to the Field_Summary when activated.
3. WHILE the pointer is over the map, THE Frontend SHALL scroll the page on a mouse wheel action without Ctrl and zoom the map on a mouse wheel action with Ctrl.
4. WHILE the pointer is over the map and the user turns the wheel without Ctrl, THE Frontend SHALL show a short hint that Ctrl plus scroll zooms the map.
5. WHEN the selected Location changes, THE Field_Summary SHALL update to the new Location.
6. THE Field_Summary SHALL name the selected Location at its top.
7. WHILE the user is on a touch screen, THE Frontend SHALL scroll the page with a one-finger drag over the map and SHALL pan and pinch-zoom the map with two fingers.

### Requirement 2: Soil profile data

**User Story:** As a farmer, I want to see every soil layer under my field, so that I understand what roots and water meet below the surface.

#### Acceptance Criteria

1. WHEN the Rotation_API receives a valid US Location, THE Backend SHALL query Soil Data Access for all layers of the dominant soil component at that Location.
2. THE Backend SHALL return, for each layer, the top depth and bottom depth in centimetres, and, where available, texture, organic matter percent, clay percent and available water capacity.
3. THE Backend SHALL order the layers from the surface downward.
4. THE Backend SHALL return the flooding frequency and ponding frequency of the dominant component where SSURGO provides them.
5. IF a layer property is missing, THEN THE Backend SHALL omit that property for that layer and keep the layer.
6. IF Soil Data Access returns no layers for the Location, THEN THE Backend SHALL return an Unavailable_Entry for the Soil_Profile with the reason "no soil survey data for this location" and still return the Strategies.
7. THE Backend SHALL cache the Soil_Profile in the Disk_Cache under its own Cache_Key, following the same rules as the farm-data sources.

### Requirement 3: 3D soil block

**User Story:** As a farmer, I want a 3D picture of my soil, so that I can see its layers, drainage and surface cover at a glance.

#### Acceptance Criteria

1. WHEN a Soil_Profile is available, THE Soil_Block SHALL render a 3D block whose layers match the Soil_Profile layers, with each layer's thickness proportional to its depth range.
2. THE Soil_Block SHALL colour each layer by its texture group and SHALL show a legend that names each colour.
3. THE Soil_Block SHALL show the surface as the most recent CDL land cover at the Location.
4. THE Soil_Block SHALL label the depth scale in centimetres and inches.
5. THE Soil_Block SHALL show a runoff indicator when the hydrologic group is C or D, and a slow-infiltration indicator when the drainage class is somewhat poorly drained or wetter.
6. WHEN the user drags the Soil_Block with a pointer, THE Soil_Block SHALL rotate around its vertical axis.
7. WHEN the Soil_Block has keyboard focus and the user presses Left Arrow or Right Arrow, THE Soil_Block SHALL rotate in steps of 15 degrees.
8. THE Soil_Block SHALL provide a text alternative listing every layer with its depth range, texture and key properties.
9. WHERE the user prefers reduced motion, THE Soil_Block SHALL skip its idle rotation and entry animation and SHALL change angle without animation.
10. THE Soil_Block SHALL be built with CSS 3D transforms and SHALL add no new frontend package.
11. IF the Soil_Profile is unavailable, THEN THE Soil_Block SHALL show an explanation of why in place of the block.

### Requirement 4: Findings

**User Story:** As a farmer, I want a few plain sentences about my field, so that I know what matters most without reading every number.

#### Acceptance Criteria

1. THE Rotation_Engine SHALL produce between 3 and 6 Findings for a Location when at least two farm-data sources are available.
2. THE Rotation_Engine SHALL generate each Finding from a written rule with a threshold, such as heat days above 60 per year or hydrologic group D.
3. THE Rotation_Engine SHALL attach to each Finding the values it used, with each value's source name and resolution.
4. THE Field_Summary SHALL show each Finding with a plain-language title, a one-sentence explanation and its source line.
5. THE Rotation_Engine SHALL include a Finding about bare-soil risk WHEN the Current_Rotation leaves the soil bare during the wettest month or during two or more consecutive months.
6. IF a source needed for a Finding rule is unavailable, THEN THE Rotation_Engine SHALL skip that Finding and SHALL keep the other Findings.
7. THE Field_Summary SHALL explain each scientific term it uses (for example hydrologic group, available water capacity, erodibility K factor, frost days) in plain language on request, through an info button or an expandable note.

### Requirement 5: Crop table

**User Story:** As a team member, I want crop facts in one sourced table, so that anyone can check and correct what the tool assumes about a crop.

#### Acceptance Criteria

1. THE Crop_Table SHALL contain these 15 crops: bermudagrass, native warm-season grass mix, sorghum-sudangrass, forage oats, annual ryegrass, crimson clover, hairy vetch, cowpea, sunn hemp, winter wheat as a cover crop, corn, grain sorghum, cotton, soybean and winter wheat for grain.
2. THE Crop_Table SHALL give each Crop_Entry these attributes: category, growing season months, perennial or annual, water need (low, medium or high), heat tolerance, frost tolerance, wet-soil tolerance, drought tolerance, nitrogen fixing (yes or no), rooting depth (shallow, medium or deep), forage value, residue or organic matter contribution, erosion protection, and the pest or disease families it shares with other crops.
3. THE Crop_Table SHALL give each Crop_Entry at least one source with a title and a URL from an extension service or government agency, such as Texas A&M AgriLife, USDA NRCS or SARE.
4. THE Crop_Table SHALL be stored as a JSON file in the repository with a comment field that states the region the values were written for (Central Texas).
5. THE Backend SHALL validate the Crop_Table at startup and SHALL refuse to start the Rotation_API with a clear error message if an entry is missing a required attribute or a source.
6. THE Field_Summary SHALL let the user open each crop's sources from the Strategy_Card.

### Requirement 6: Current rotation

**User Story:** As a farmer, I want the tool to start from what I actually grow, so that the comparison is fair to my current practice.

#### Acceptance Criteria

1. THE Rotation_Engine SHALL infer the Current_Rotation from the CDL crop history returned for the Location.
2. WHEN one land cover appears in at least 6 of the available years, THE Rotation_Engine SHALL treat the Current_Rotation as that cover grown continuously.
3. WHEN two or more crops alternate in the CDL history, THE Rotation_Engine SHALL describe the Current_Rotation as that sequence, for example "corn then soybean".
4. THE Rotation_Engine SHALL map CDL land-cover names to Crop_Entries where a match exists, such as "Grass/Pasture" to bermudagrass or native grass pasture.
5. IF the CDL history is unavailable, empty, or shows mostly non-farm cover such as forest, developed land or water, THEN THE Rotation_Engine SHALL say so and SHALL let the farmer choose the Current_Rotation from a list of the Crop_Table crops.
6. THE Strategy_Card for the Current_Rotation SHALL be labelled "Current" and SHALL show the CDL evidence, for example "Grass/Pasture in 7 of 8 years".

### Requirement 7: Strategy generation and suitability

**User Story:** As a farmer, I want alternative rotations that fit my climate and soil, so that I do not waste time on crops that cannot work here.

#### Acceptance Criteria

1. THE Rotation_Engine SHALL return the Current_Rotation plus at least two alternative Strategies for every valid US Location, for a total of at least three.
2. THE Rotation_Engine SHALL build alternative Strategies from a fixed set of rotation templates, such as adding a winter legume to the current cover, double-cropping a summer forage with a winter cover, or a three-year row-crop rotation.
3. THE Rotation_Engine SHALL exclude a crop WHEN a Site_Fact conflicts with its Crop_Entry, including at least these rules: a crop with low wet-soil tolerance on a soil in hydrologic group D or with occasional or frequent flooding; a crop with low heat tolerance where heat days exceed the crop's limit; a crop with low frost tolerance grown over winter where frost days exceed the crop's limit; a crop with high water need where irrigation is not available and yearly rain is below the crop's limit.
4. THE Rotation_Engine SHALL return every Exclusion with the crop name and the rule and value that caused it.
5. THE Field_Summary SHALL show the Exclusions in a "Ruled out for this field" list.
6. THE Rotation_Engine SHALL not place two crops from the same pest or disease family back to back in an alternative Strategy.
7. THE Rotation_Engine SHALL place each crop only in the months of its growing season.
8. WHEN the farmer has set the "no livestock" Constraint, THE Rotation_Engine SHALL not suggest Strategies whose main benefit is grazing or forage.

### Requirement 8: Strategy explanation

**User Story:** As a farmer, I want to know why each rotation was suggested and what could go wrong, so that I can judge it with my own experience.

#### Acceptance Criteria

1. THE Strategy_Card SHALL show the Strategy name, its crop sequence, and its Calendar_Strip.
2. THE Strategy_Card SHALL show a "Why" statement that cites at least one Site_Fact with its value and source.
3. THE Strategy_Card SHALL show at least one benefit and at least one risk to check locally.
4. THE Strategy_Card SHALL show at least one information gap, such as no soil test for pH or phosphorus, no data on markets, or no data on equipment.
5. THE Strategy_Card SHALL explain in one sentence how each nitrogen-fixing, cover, deep-rooting or drought-tolerant crop in the Strategy helps soil health.
6. THE Strategy_Card SHALL show a Confidence label, and SHALL list which Site_Facts were missing WHEN the Confidence is medium or low.
7. THE Strategy_Card SHALL link each crop name to its Crop_Entry sources.

### Requirement 9: Farmer priorities and constraints

**User Story:** As a farmer, I want to tell the tool what matters to me, so that the rotations are ranked by my goals and not someone else's.

#### Acceptance Criteria

1. THE Priority_Picker SHALL offer these Priorities as toggles: save water, build soil, livestock forage, extra income, fewer field passes.
2. THE Priority_Picker SHALL offer these Constraints: irrigation available (yes or no), livestock on the farm (yes or no), no-till only (yes or no).
3. WHEN the farmer changes a Priority or Constraint, THE Frontend SHALL request updated Strategies and SHALL re-order the Strategy_Cards by score.
4. THE Frontend SHALL keep the Current_Rotation card visible in the comparison whatever its score.
5. THE Frontend SHALL remember the farmer's Priorities and Constraints in the browser for the next visit.
6. THE Frontend SHALL start with no Priorities selected and with Constraints set to "irrigation: no", "livestock: unknown" and "no-till only: no".
7. THE Strategy_Card ranked first SHALL be labelled "Best fit for your priorities" and SHALL not be labelled as a recommendation.

### Requirement 10: Transparent scoring

**User Story:** As a farmer, I want to see how each rotation was scored, so that I can trust or question the ranking.

#### Acceptance Criteria

1. THE Rotation_Engine SHALL score each Strategy from 0 to 100 on each of these dimensions: water use, soil building, erosion protection, forage, income potential and field passes.
2. THE Rotation_Engine SHALL compute each dimension score from Crop_Table attributes and Site_Facts with a documented formula, and SHALL return the parts of the formula with each score.
3. THE Rotation_Engine SHALL compute the overall score as a weighted average in which the dimensions linked to the selected Priorities count double.
4. THE Strategy_Card SHALL show the dimension scores as labelled bars, and SHALL show how a score was computed when the user asks.
5. THE Rotation_Engine SHALL return the same scores for the same Location, Priorities and Constraints every time.
6. THE Field_Summary SHALL state that income potential is a rough guide without local market prices.

### Requirement 11: Calendar strip

**User Story:** As a farmer, I want to see each rotation across the year, so that I can spot bare soil and stress periods before they happen.

#### Acceptance Criteria

1. THE Calendar_Strip SHALL show 12 months, January to December, each coloured by the crop in the ground or as bare soil.
2. THE Calendar_Strip SHALL mark heat-stress months, defined as months whose average daily high is above 35 °C.
3. THE Calendar_Strip SHALL mark the wettest month.
4. THE Calendar_Strip SHALL mark frost months, defined as months between the typical first fall frost and last spring frost.
5. THE Calendar_Strip SHALL show a legend and SHALL give each month a text label for screen readers, such as "May: bare soil, wettest month".
6. THE Calendar_Strip SHALL not rely on colour alone and SHALL use a pattern or symbol for bare soil, heat stress and frost.

### Requirement 12: Uncertainty and human judgment

**User Story:** As a farmer, I want the tool to be honest about what it does not know, so that I check the right things with people I trust.

#### Acceptance Criteria

1. THE Field_Summary SHALL state that strategies are starting points to discuss with a county extension agent or agronomist.
2. THE Field_Summary SHALL state that climate data is regional (about 50 km), soil data is a map-unit average, and crop history comes from satellite classification that can be wrong for a single field.
3. THE Field_Summary SHALL state that satellite and model data differ from measurements taken in the field, and that a soil test and local records improve the picture.
4. THE Strategy_Card SHALL mark risks that need local review in a distinct style.
5. THE Field_Summary SHALL show the statement that the tool supports farmer judgment and does not replace it.

### Requirement 13: Rotation API and failure handling

**User Story:** As a developer, I want one endpoint for the rotation explorer that never breaks the page, so that the summary works even when a data source is down.

#### Acceptance Criteria

1. THE Rotation_API SHALL accept a Location and the Priorities and Constraints as query parameters.
2. THE Rotation_API SHALL reuse the farm-data services and the Disk_Cache and SHALL not call an upstream source a second time for data already cached.
3. THE Rotation_API SHALL apply the same Location validation as the Farm_Data_API and SHALL respond with HTTP status 400 and a plain message for invalid input.
4. IF one or more farm-data sources fail, THEN THE Rotation_API SHALL respond with HTTP status 200, still return Strategies, lower their Confidence, and list the missing sources.
5. IF the Priorities or Constraints contain an unknown value, THEN THE Rotation_API SHALL respond with HTTP status 400 and name the unknown value.
6. WHILE the Rotation_API request is in progress, THE Field_Summary SHALL show a loading state, and WHEN the request fails at the network level THE Field_Summary SHALL show an error with a retry button.

### Requirement 14: Tests

**User Story:** As a developer, I want the rotation rules tested offline, so that changes to rules or crop facts do not silently change advice.

#### Acceptance Criteria

1. THE Test_Suite SHALL test the Rotation_Engine with fixed Site_Facts and SHALL make no network requests.
2. THE Test_Suite SHALL include a test for each Exclusion rule that shows a crop is excluded when the rule applies and kept when it does not.
3. THE Test_Suite SHALL include a test that confirms the Rotation_API returns at least three Strategies, including the Current_Rotation, for the Webberwood fixtures.
4. THE Test_Suite SHALL include a test that confirms scores are identical across repeated calls with the same input.
5. THE Test_Suite SHALL include a test that confirms selecting a Priority can change the ranking and never removes the Current_Rotation.
6. THE Test_Suite SHALL include a test that confirms every Crop_Entry has all required attributes and at least one source.
7. THE Test_Suite SHALL include a test that confirms every Finding and Strategy "Why" statement cites at least one value with its source.
8. THE Verify_Script SHALL include a live check of the Rotation_API for the demo farm that reports the number of Findings, Strategies and Exclusions, and whether trends and the Outlook were available.
9. THE Test_Suite SHALL test the trend calculation on made-up series with a known slope, a series with no trend, a series with one extreme year, and a series with missing years.
10. THE Test_Suite SHALL test each Climate_Indicator calculation on small hand-made daily series.
11. THE Test_Suite SHALL include a test that confirms a crop that passes today but fails under the Outlook is reported as a future risk.

### Requirement 15: Accessibility and visual consistency

**User Story:** As a user, I want the summary to match the rest of the app and work for everyone, so that the experience feels like one tool.

#### Acceptance Criteria

1. THE Field_Summary SHALL use the same theme tokens, font stack, corner radius, accent colour and light and dark themes as the farm-data panel.
2. THE Field_Summary SHALL meet the same contrast rules as the farm-data panel: at least 4.5:1 for normal text and 3:1 for large text and component boundaries.
3. THE Field_Summary SHALL be operable with the keyboard alone, with a visible 2 px accent focus indicator on every interactive element.
4. THE Priority_Picker toggles SHALL expose their pressed or checked state to assistive technology.
5. WHEN the Strategies are re-ordered, THE Frontend SHALL announce the new top Strategy through an ARIA live region.
6. WHILE the viewport is a Narrow_Screen, THE Field_Summary SHALL stack its parts in one column and the Strategy_Cards SHALL be readable without horizontal scrolling.

### Requirement 16: Scope and simplicity

**User Story:** As a team lead, I want the feature to stay small and safe, so that a novice team can maintain it during the hackathon.

#### Acceptance Criteria

1. THE Frontend SHALL use only React 18, Vite, MapLibre and Recharts and the packages already in `frontend/package.json`.
2. THE Backend SHALL use only the packages already in `backend/requirements.txt`.
3. THE project SHALL keep all `.env` values out of code, logs and responses.
4. THE Backend and Frontend source files SHALL include plain-language comments that explain the purpose of each module and each rule.
5. THE Frontend SHALL request data only from the Backend and make no direct requests to NASA, USDA, Open-Meteo or other upstream data services. Map tiles are the exception, as in farm-data-panel Req 17.2.

### Requirement 17: Climate trends since 1981

**User Story:** As a farmer, I want to see how heat, frost, rain and dry spells have changed at my field over the last decades, so that I plan for the conditions that are actually arriving and not the ones my parents had.

#### Acceptance Criteria

1. WHEN the Rotation_API receives a valid US Location, THE Backend SHALL retrieve NASA POWER daily data from 1 January 1981 to the end of the last complete year for daily minimum temperature, daily maximum temperature, precipitation, land evapotranspiration (`EVLAND`, mm/day) and root-zone soil moisture.
2. THE Backend SHALL compute these yearly Climate_Indicators: days above 35 °C, nights above 24 °C, frost days, last spring frost date, first fall frost date, total rain, rain in the growing season (April to September), longest run of days with less than 1 mm of rain, heavy-rain days, rain minus evapotranspiration, and average growing-season root-zone soil moisture. A heavy-rain day SHALL be a day whose rain exceeds the local 95th percentile of wet days (1 mm or more) in 1981–2010.
3. THE Backend SHALL skip a year for an indicator WHEN more than 10% of that year's daily values are missing.
4. THE Backend SHALL compute a Climate_Trend for each indicator with a method that is not distorted by single extreme years, and SHALL report the change per decade in the indicator's units.
5. THE Backend SHALL label a Climate_Trend as a clear change only WHEN a statistical test shows less than a 5% chance that the trend is due to normal year-to-year variation, and SHALL label it "no clear change" otherwise.
6. THE Field_Summary SHALL show each Climate_Indicator as a yearly chart with its trend line, its change per decade in plain words (for example "about 6 more hot days per decade") and its clear-or-not label.
7. THE Field_Summary SHALL show the average of the first ten years and the last ten years side by side for each indicator.
8. THE Field_Summary SHALL explain that trends describe the past and are not a forecast of any single future year.
9. THE Rotation_Engine SHALL produce a Finding for each indicator with a clear change, citing the change per decade and the source.
10. THE Backend SHALL cache the daily data and the computed indicators in the Disk_Cache, and SHALL refresh them at most once per calendar year for a Cache_Key.
11. IF the daily data request fails, THEN THE Rotation_API SHALL return the Strategies without trends, mark the trends as unavailable with a reason, and lower the Confidence of trend-dependent Findings.
12. WHEN more than half of the years have a value of zero for an indicator, THE Backend SHALL report its change as the difference between the averages of the first 15 and the last 15 years, and SHALL state that method.

### Requirement 18: Climate outlook to 2050 (Open-Meteo)

**User Story:** As a farmer, I want to know what climate models expect for my area in the coming decades, so that the rotation I choose still works in 10 to 20 years.

#### Acceptance Criteria

1. THE Backend SHALL obtain daily maximum temperature, minimum temperature and precipitation from the Open-Meteo Climate API for 1991–2020 and 2030–2049 from at least three climate models, in one of two ways: precomputed by a script for each demo farm in `config/demo_farms.json`, or loaded in the background WHEN the farmer activates a "Load 2030–2049 outlook" control for another Location.
2. THE Backend SHALL compute the same Climate_Indicators as Requirement 17 that the Open-Meteo variables allow, for a recent period (1991–2020) and a future period (2030–2049), for each model.
3. THE Backend SHALL report the Outlook as the change from the recent period to the future period, giving the lowest, middle and highest value across models.
4. THE Field_Summary SHALL show the Outlook next to each matching Climate_Trend, as a range, for example "2030–2049: 8 to 21 more hot days a year than 1991–2020".
5. THE Field_Summary SHALL state the Outlook_Source, the number of models, the model resolution, that the models follow a high-emissions path, and that the values are model projections and not measurements or forecasts.
6. THE Rotation_Engine SHALL score each Strategy against both the recent conditions and the Outlook, and the Strategy_Card SHALL show both scores.
7. WHEN a crop in a Strategy passes the suitability rules today but fails them under the middle Outlook value, THE Strategy_Card SHALL show this as a future risk with the indicator and values that cause it.
8. THE Backend SHALL cache on-demand Open-Meteo results by the 0.1° Open-Meteo grid cell and SHALL not request the same cell again within 30 days.
9. THE Backend SHALL keep Open-Meteo use within the free non-commercial limits (600 calls a minute, 5,000 an hour and 10,000 a day, counted by Open-Meteo's weighting) by spacing requests at least 60 seconds apart and refusing new loads above 4,500 weighted calls an hour or 9,000 a day.
10. IF the Open-Meteo request fails or the daily limit is reached, THEN THE Rotation_API SHALL return the Strategies scored on recent conditions only and mark the Outlook as unavailable with a reason.
11. THE Field_Summary SHALL credit Open-Meteo and the CC BY 4.0 licence wherever Outlook values are shown.
12. WHILE an on-demand Outlook is loading, THE Field_Summary SHALL show the expected wait and SHALL update the Strategies when the Outlook is ready.

### Requirement 19: NASA climate projection for demo farms (Phase 2)

**User Story:** As a farmer, I want the option of NASA's climate projection, so that I can compare a second, more detailed set of models before I decide.

#### Acceptance Criteria

1. THE project SHALL include a script that downloads NASA NEX-GDDP-CMIP6 daily maximum temperature, minimum temperature and precipitation for each demo farm in `config/demo_farms.json`, for the historical period and at least one future emissions scenario, and saves the computed indicators to a file in the repository.
2. THE script SHALL run outside the web request and SHALL record the models, scenario, years and download date it used.
3. WHEN the selected Location is a demo farm with a precomputed NASA projection, THE Field_Summary SHALL offer a switch between "Open-Meteo" and "NASA NEX-GDDP-CMIP6" as the Outlook_Source.
4. WHEN the selected Location has no precomputed NASA projection, THE Field_Summary SHALL show Open-Meteo only and SHALL explain that the NASA projection is available for demo farms.
5. THE Field_Summary SHALL describe the NASA option as more models and a choice of emissions scenario, and SHALL not describe it as certain.

### Requirement 20: Advanced soil test entry (Phase 2)

**User Story:** As a farmer with a recent soil test, I want to enter my own results, so that the tool uses my field's real numbers instead of survey averages.

#### Acceptance Criteria

1. THE Field_Summary SHALL offer an "Advanced soil" form with these fields: pH, organic matter percent, phosphorus (ppm), potassium (ppm), test date and sample depth.
2. THE form SHALL accept any subset of the fields and SHALL validate each value against a plausible range, such as pH 3.5 to 10, with a plain message for out-of-range values.
3. WHEN the farmer submits Soil_Test values, THE Rotation_Engine SHALL use them in place of the matching SSURGO estimates and SHALL recompute Findings, Strategies and scores.
4. THE Field_Summary SHALL tag every value that came from the Soil_Test as "your soil test" with its date, in place of the SSURGO source tag.
5. THE Frontend SHALL store Soil_Test values only in the browser and SHALL send them to the Backend only as request parameters, and THE Backend SHALL not store or log them.
6. THE form SHALL provide a "clear my soil test" control that returns to the SSURGO estimates.
7. WHEN no Soil_Test is entered, THE Strategy_Card SHALL list "no soil test for pH, phosphorus or potassium" as an information gap.

### Requirement 21: Bare-soil and crop-stress months from satellite (Phase 1)

**User Story:** As a farmer, I want the tool to see from space when my field is bare or stressed, so that suggestions target the real weak months.

#### Acceptance Criteria

1. THE Backend SHALL retrieve the MODIS 250 m vegetation index (NDVI) time series for the Location from the ORNL DAAC MODIS web service, for the last 3 complete years, prepared in advance for demo farms. Other Locations SHALL show "not prepared" with the reason. *(Changed 2026-11-15 by the team, option b: the service takes 20–37 s per 10-date request, so 10 years would take about 20 minutes per location.)*
2. THE Backend SHALL compute, for each month, the typical NDVI and the share of years in which the field looked bare, using a documented NDVI threshold.
3. THE Calendar_Strip for the Current_Rotation SHALL use the satellite bare-month result in place of the crop-calendar estimate WHEN it is available, and SHALL say which one it shows.
4. THE Field_Summary SHALL explain NDVI in plain language and SHALL state that a 250 m pixel can include land outside the field.
5. THE Field_Summary SHALL show the NDVI time series as a chart, and SHALL state that MODIS is a NASA satellite observation.
6. THE Backend SHALL cache the NDVI result per Cache_Key and refresh it at most once a month.

### Requirement 22: County crops and prices (Phase 2)

**User Story:** As a farmer, I want to see what my county grows and rough prices, so that I can judge whether a new crop has a local market.

#### Acceptance Criteria

1. THE Backend SHALL retrieve county acreage for the Crop_Table crops and state average prices from the USDA NASS Quick Stats API for the county of the Location.
2. THE Backend SHALL read the Quick Stats API key from the environment variable named in `.env.example`, and SHALL keep the key out of responses, logs and Frontend code.
3. THE Strategy_Card SHALL show, for each crop, whether it is grown in the county and its most recent state price with the year and units.
4. THE Rotation_Engine SHALL use county acreage and state prices in the income potential score, and SHALL state that prices are state averages and not local quotes.
5. IF Quick Stats has no data or the request fails, THEN THE Strategy_Card SHALL show "no market data" and the income score SHALL fall back to the Crop_Table estimate.

### Requirement 23: NASA satellite water data (Phase 1)

**User Story:** As a farmer, I want to see what NASA satellites measured about rain, soil moisture and groundwater at my field, so that I can judge water shortage from observations and not only from models.

#### Acceptance Criteria

1. THE Backend SHALL retrieve GPM IMERG Final monthly precipitation (0.1°, about 10 km) for the Location from June 2000 to the last complete month, through the NASA GES DISC Giovanni Time Series API.
2. THE Backend SHALL retrieve the GRACE and GRACE-FO data-assimilation drought indicators (US, 0.125°, weekly) for root-zone soil moisture and groundwater storage for the Location, through the same API.
3. THE Backend SHALL attempt to retrieve SMAP soil moisture for the Location from April 2015 to the latest available month, and IF SMAP cannot be reached with the configured credentials, THEN THE Backend SHALL report SMAP as unavailable with the reason and keep the other water data.
4. THE Backend SHALL authenticate with the NASA Earthdata Login bearer token read from the `EARTHDATA_TOKEN` environment variable, and SHALL keep the token out of responses, logs, cache files and Frontend code.
5. IF `EARTHDATA_TOKEN` is not set or is rejected, THEN THE Rotation_API SHALL report the NASA water data as unavailable with a plain reason and SHALL still return everything else.
6. THE Backend SHALL compute monthly values, the average for each calendar month, and a yearly trend for IMERG rain, using the method of Requirement 17.
7. THE Field_Summary SHALL show IMERG monthly rain next to NASA POWER rain for the same months, and SHALL explain that IMERG is built from satellite microwave and infrared observations while POWER is a model reanalysis.
8. THE Field_Summary SHALL show the GRACE-based groundwater and root-zone soil moisture as time series of drought percentiles, with a plain explanation of what a percentile of 10 or 90 means, and SHALL state that GRACE measures water across a large region.
9. THE Rotation_Engine SHALL produce a Finding WHEN the latest 12 months of GRACE groundwater average below the 20th percentile, citing the value and source.
10. THE Field_Summary SHALL show each of these as time series or location-level values only, never as a fine-resolution map, and SHALL label each with its resolution.
11. THE Backend SHALL cache the water data per Cache_Key and refresh it at most once a month.
12. THE Test_Suite SHALL test the parsing, monthly aggregation, trend and Finding for these sources with saved responses and no network requests.
