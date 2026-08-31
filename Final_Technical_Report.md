# AI-based Village Pond Planning System

## Final Technical Report

**Student:** Sneha Nagmoti

**Assignment:** Assignment 1

**Submission phase:** Phase 3 - Final implementation and demonstration

**Date:** 29 August 2026

**Repository:** https://github.com/snehanagmoti/Village-Pond-planning

## 1. Abstract

This project implements a web-based decision-support system for preliminary
village pond planning. It provides two connected workflows. The Phase 2 workflow
accepts an arbitrary KML/KMZ contour map, reconstructs a terrain grid from the
uploaded geometry, identifies a hydrologically strong candidate point, and
delineates its contributing catchment. The complete application also supports a
location-based workflow that combines satellite imagery, elevation, historical
rainfall, surface screening, D8 hydrology, runoff estimation, and approximate
pond geometry in an interactive map.

The implementation is deliberately transparent about uncertainty. Results carry
source provenance, quality status, limitations, and a screening-only flag. The
software does not claim government ownership, legal land availability, surveyed
terrain accuracy, or construction safety. Those decisions require cadastral
records, field survey, soil and groundwater investigation, qualified engineering
design, and statutory approval.

## 2. Requirement traceability

| Assignment requirement | Implemented evidence |
| --- | --- |
| Satellite imagery | Leaflet satellite base map and bounded imagery mosaic service |
| Contour visualization | Live DEM contour overlays and uploaded contour study boundary |
| Suitable/available land | Conservative bare-surface candidate; ownership explicitly unverified |
| Catchment area | Priority-flood conditioning, D8 routing, reverse catchment traversal, area in ha |
| Historical rainfall | Complete-year Open-Meteo ERA5-Land analysis with a validated NASA POWER fallback |
| Runoff volume | `V = C x A x P` with visible coefficient and documentary basis |
| Pond depth/capacity | Side-sloped rectangular-frustum screening geometry with freeboard |
| Selected point and maps | Leaflet point, catchment, study area, candidate land and contour layers |
| User pond-site choice | Automatic ranking, validated point selection, or polygon-constrained search |
| River/water safeguard | Detected-water cells and a configurable 60 m buffer are hard-excluded before scoring |
| KML/KMZ backend route | `POST /api/analyze-contour` plus assignment-compatible aliases |
| Structured result | Strict Pydantic JSON models, stable errors and OpenAPI documentation |
| Generalized implementation | All locations, geometry, elevations and outputs derived from input |
| Accessible frontend | Responsive keyboard-friendly React UI with clear completion status and expandable technical notes |
| Installation/API docs | README, `docs/API.md`, `docs/DEPLOYMENT.md`, Swagger and ReDoc |
| Testing/code quality | Automated unit/API/UI tests, lint, coverage, audits, migrations and builds |

## 3. System architecture

The browser client is a Vite/React single-page application using Leaflet for map
display. It sends either a multipart contour upload or a location/radius JSON
request to a FastAPI backend. Axios cancellation and a monotonically increasing
request sequence prevent stale responses from replacing newer analysis.

FastAPI validates all public contracts with Pydantic and delegates geospatial
work to independent services. Uploaded contours pass through a safe parser,
terrain-grid reconstruction, and the shared hydrology pipeline. Location analysis
uses independent elevation, rainfall, imagery, geocoding, terrain, runoff, and
pond modules. CPU-heavy OpenCV and terrain work runs outside the asynchronous
event loop.

PostgreSQL history is optional and disabled by default because it stores precise
locations. When enabled, history requires an API key, bounded queries, Alembic
migrations, and non-default credentials.

```text
React / Leaflet
  |-- KML/KMZ multipart --> FastAPI --> safe parser --> interpolated DEM
  |                                              `--> D8 catchment JSON
  `-- location + radius --> FastAPI --> elevation + rainfall + imagery
                                                 `--> runoff + pond screen

Optional protected history -------------------------------> PostgreSQL
```

## 4. Phase 2 contour-file analysis

### 4.1 Input and validation

The canonical route is `POST /api/analyze-contour`; the multipart field name is
`contour_file`. Hidden compatibility aliases `/api/analyzeContour` and
`/api/findCatchment` accept the same request. The route reads at most the
configured 15 MiB plus one byte, closes the temporary upload, and runs CPU work
in a worker thread.

The parser supports plain KML and KMZ. It obtains a line elevation, in order,
from a numeric Placemark name, an elevation-like `Data` or `SimpleData` field,
or a constant altitude coordinate. It accepts namespace variants and
`MultiGeometry` because it traverses Placemark geometry recursively.

Validation rejects malformed XML, DTD/entity declarations, invalid coordinates,
encrypted archives, unsafe compression ratios, too many archive entries, large
expanded KMZ content, excessive contour/point counts, fewer than three lines or
levels, and less than 0.5 m total relief. An uploaded polygon supplies a study
boundary; otherwise a buffered convex hull is derived from the input contours.

### 4.2 Terrain reconstruction

KML stores vector isolines rather than a complete elevation raster. The service
projects the study extent to a latitude-corrected metric grid. Grid dimensions
are selected from input extent and contour interval, then bounded by
configuration. Each contour is rasterized into fixed observed cells. Unknown
interior cells are initialized from neighboring observations and solved by
iterative harmonic interpolation while observed values remain fixed. The result
records observed-cell ratio, iteration count, convergence, cell size, and method.

The study boundary masks both interpolation and later hydrology so cells outside
the uploaded domain cannot become part of the catchment. Results are always
labelled `degraded`, even on successful convergence, because an interpolated
surface is not equivalent to a surveyed DEM.

### 4.3 Hydrology and candidate selection

The shared deterministic pipeline performs:

1. finite grid and analysis-mask validation;
2. priority-flood depression filling;
3. a very small deterministic gradient for equal-elevation flats;
4. steepest lower-neighbor D8 flow direction;
5. topological upstream flow accumulation;
6. local-slope, relative-elevation, analysis-boundary-clearance, and detected-
   water-clearance calculation;
7. hard eligibility filtering that rejects cells outside the study area, inside
   the configurable boundary or detected-water setbacks, on a terminal outlet,
   or without a valid upstream land catchment;
8. explainable multi-criteria ranking. When water evidence is available, the
   score uses 52% logarithmic contributing area, 20% local flatness, 10% lower
   relative elevation, 8% boundary clearance, and 10% water clearance. Without
   water evidence the normalized weights are 58%, 22%, 11%, and 9%;
9. deterministic non-maximum suppression that keeps three alternatives at
   least 100 m or three grid cells apart;
10. selection by the top automatic option, a user point snapped to an eligible
    grid cell, or the highest-scoring cell inside a user-drawn polygon;
11. reverse graph traversal to collect every cell draining to the actually
    selected candidate, rather than the larger study-area outlet watershed;
12. latitude-corrected catchment-area calculation; and
13. simplified WGS84 boundary extraction for JSON and Leaflet.

Manual selections pass the same hard safeguards as automatic options. An
outside, boundary-setback, outlet, or detected-water point returns a typed 422
error instead of a plausible-looking result. Changing the selected option
restarts reverse traversal and therefore recomputes catchment, rainfall-based
runoff, capacity, dimensions, and excavation volume for that point.

No sample coordinate, candidate point, catchment boundary, area, or expected
elevation is stored in the implementation.

### 4.4 Provided-map result

The supplied `contours_1m.kml` was processed through release `0a385c0` of the
deployed service on 29 August 2026. The measured automatic output was:

| Metric | Result |
| --- | ---: |
| Contour LineStrings | 1,355 |
| Source vertices | 159,113 |
| Distinct elevation levels | 32 |
| Elevation range | 267.0-298.0 m |
| Median contour interval | 1.0 m |
| Analysis grid | 148 x 181 |
| Cell size | 18.0 m |
| Directly observed analysis cells | 85.206% |
| Harmonic iterations | 31, converged |
| Candidate coordinate | 21.244025, 81.288000 |
| Candidate interpolated elevation | 270.0 m |
| Candidate suitability | 95.54 / 100 |
| Local slope | 2.899% |
| Boundary / detected-water clearance | 467.99 m / 334.35 m |
| Modelled catchment | 3,529,523.47 m2 / 352.9523 ha |
| Catchment cells | 10,894 |
| Catchment share of study grid | 41.752% |
| Historical rainfall | 1,280.13 mm/year, 35 valid years |
| Screening runoff volume | 1,355,474.66 m3/year at C = 0.30 |
| Preliminary pond capacity | 1,084,379.73 m3 |
| Preliminary excavation volume | 1,224,734.67 m3 |
| Production API time | 12.47 s, HTTP 200 |

The three returned alternatives were:

| Rank | Coordinate | Score | Upstream area | Slope | Water clearance |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 21.244025, 81.288000 | 95.54 | 352.9523 ha | 2.899% | 334.35 m |
| 2 | 21.242893, 81.286959 | 95.16 | 381.4633 ha | 2.777% | 262.63 m |
| 3 | 21.245156, 81.289215 | 95.04 | 301.1143 ha | 2.777% | 435.54 m |

Selecting option 3 as a point produced the exact 301.1143 ha upstream
catchment, 1,156,396.32 m3/year runoff, and 925,117.06 m3 capacity. Restricting
the search to a small polygon around option 2 selected that point and produced
381.4633 ha, 1,464,967.75 m3/year runoff, and 1,171,974.20 m3 capacity. This
proves that each output is recomputed for the selected point rather than copied
from the automatic result. A KMZ created from the same KML produced an identical
automatic result. An outside manual point returned HTTP 422 with
`invalid_contour_selection`.

Production satellite screening detected 0.33% water-like pixels and applied the
60 m hard exclusion before ranking. A separate deterministic synthetic-river
test placed the water mask over the otherwise best KML candidate and verified
that the point was rejected as inside the exclusion buffer.

These figures demonstrate the working algorithm on the provided map; they are
not a field-verified pond recommendation.

## 5. Location-based elevation and hydrology

The location workflow requests WGS84 elevation points through Open-Meteo. The
documented source is Copernicus DEM 2021 GLO-90. Grid density is radius-aware and
targets approximately 90 m cells, subject to configured limits. The public API
path is capped at 23 x 23 locations to remain below its public request allowance;
the response is marked degraded when this cap is coarser than the target.

If the point API fails or returns insufficient coverage, the backend uses a
bounded Terrain Tiles fallback rather than fabricating elevations. The fallback
downloads only the required HTTPS Terrarium PNG tiles and validates tile count,
response size, media type, dimensions, channels, decoded elevation range, and
coverage. Terrarium values are decoded as
`(red x 256 + green + blue / 256) - 32768`. The result identifies the AWS Open
Data/Tilezen source, reports its own resolution, and is always marked degraded.

Every batch is checked for matching length, numeric range, finite coverage, and
final shape. The system does not fill a failed batch with synthetic terrain. A
small percentage of isolated missing cells can be locally interpolated, while
larger missing regions make elevation unavailable.

Priority-flood, D8, accumulation, catchment traversal, area calculation, and
boundary extraction match the contour workflow. A radius is the half-width of
the square grid, not proof that the full upstream catchment lies inside it.
Roads, culverts, irrigation channels, breached embankments, structures, and DEM
vertical error can materially change real drainage.

## 6. Rainfall analysis

The default period is 1991-2025 and the primary model is ERA5-Land through
Open-Meteo. When that service is rate-limited or returns insufficient complete
years, the backend requests `PRECTOTCORR` from NASA POWER. The fallback is
identified as MERRA-2 corrected precipitation and marked degraded because its
0.5 by 0.625 degree grid is not a village rain gauge.

For both sources, daily non-negative precipitation is grouped by calendar year.
Only years containing every expected date are used, so gaps cannot reduce a
total as if they were zero rainfall. Response size, sentinel values, date/value
alignment, numerical range, complete-year count, and coverage are validated.
Monthly means state their contributing complete-year count.

Mean annual rainfall supports screening water yield. It is not a design storm
and cannot size a spillway or establish flood safety.

## 7. Satellite surface screening and land limits

The imagery service downloads all tiles needed for the selected extent and
rejects missing, malformed, blank, low-contrast, or inconsistent images. Zoom is
radius-aware to bound network work and memory. Provider name, retrieval time,
approximate resolution, source status, and terms link are returned.

OpenCV screens broad HSV/RGB classes for vegetation, water-like pixels, brown or
sandy surface, and low-saturation surface. Morphological cleanup removes small
noise. The largest qualifying region becomes a **bare-surface candidate**, and
candidate placement is restricted to its intersection with the modelled
catchment. Water is treated differently from an ordinary score: detected water
and a configurable 60 m metric buffer are removed from the candidate mask before
ranking in both workflows. Candidate cards report their measured clearance from
detected water.

Satellite color cannot prove government ownership, legal availability, soil,
rock, crops, seasonal water, utilities, protected status, or excavation
suitability. It can also miss a narrow, muddy, shaded, seasonal, cloud-covered,
or recently shifted river. Therefore the UI and API never describe this polygon
as verified government land and never treat water non-detection as proof that a
river is absent. Cadastral, hydrography, field, and engineering verification are
mandatory.

## 8. Runoff and pond geometry

Annual screening water yield is:

`V = C x A x P`

where `V` is cubic metres per year, `C` is a documented runoff coefficient, `A`
is modelled catchment area in square metres, and `P` is mean annual rainfall in
metres. The system does not infer `C` from image color. If the coefficient or its
basis is absent, runoff and pond geometry are unavailable rather than guessed.

The hosted course demo labels `C = 0.30` as a demonstration scenario so the
complete calculation path can be shown. It is not a site-approved coefficient
and must be replaced for real work. Peak flow is separate and remains absent
until an approved design rainfall intensity is configured:

`Q = C x i x A / 3.6`

for area in square kilometres and intensity in millimetres per hour.

Pond capacity uses rectangular-frustum geometry with configurable length/width
ratio, side slope, water depth, freeboard, and capture efficiency. Capacity is
measured to water level; excavation volume and crest dimensions include
freeboard. The footprint is constrained by candidate area and no geometry is
returned if even the minimum cross-section cannot fit.

The module does not design an inlet, outlet, spillway, bund, liner, sediment
forebay, ramp, fencing, slope stabilization, or construction sequence.

## 9. Frontend and visualization

The responsive sidebar contains a Phase 2 file uploader plus place search,
coordinate entry, radius selection, request start/cancel controls, and reset.
For an uploaded contour map, the user can keep automatic ranking, click one
eligible map point, or draw a polygon that restricts the search. Ranked option
cards can also recompute the result with one action. The entire results panel is
collapsible so it does not hide the map.

The map displays satellite imagery and individually toggleable evidence layers.
Contour-upload results show reconstructed contour lines, uploaded analysis
extent, computed catchment, modelled drainage path, the separate hydrology
outlet, and numbered pond alternatives. The legend explicitly explains that the
orange outlet is evidence, not a pond recommendation. Location results show the
catchment, DEM contours, surface candidate, selected centre, and pond options.

Results include source panels, quality chips, expandable technical notes, terrain/hydrology
statistics, monthly rainfall chart, land-screening ratios, runoff assumptions,
and pond dimensions. Form labels, keyboard focus, high contrast, live regions,
text alternatives, reduced-motion support, and responsive breakpoints improve
accessibility.

## 10. API, errors, and security

FastAPI provides Swagger at `/docs`, ReDoc at `/redoc`, and OpenAPI JSON at
`/openapi.json` when enabled. Pydantic rejects unknown fields, non-finite values,
unsupported coordinates, invalid radius, and malformed response data. Error
payloads use stable codes and safe messages.

Per-scope rate limits protect analysis, contour upload, search, and history.
Logs contain a sanitized request ID, method, path, status, and duration, but not
exact submitted coordinates or secrets. API responses use `no-store` and add
anti-sniffing, frame, referrer, and permissions headers. CORS and trusted hosts
are explicit in deployment. The 15 MiB upload limit is enforced before parsing
and at the Nginx boundary.

Secrets remain outside version control. Production configuration rejects
wildcard origins/hosts, placeholder geocoding contacts, insecure provider URLs,
weak history configuration, unbased runoff values, and unconfirmed provider
authorization.

## 11. Reliability and operations

External requests share a bounded HTTP connection pool and use timeouts, retries
with capped backoff, bounded TTL caching, and source-specific validation.
Liveness and readiness are separate. A database outage affects readiness only
when history is enabled, and persistence failure does not erase an otherwise
valid analysis response.

The backend and Nginx containers run as non-root users with health checks and
restart policies. Docker Compose keeps the API and PostgreSQL off public host
ports and exposes the frontend proxy on 8080. The Render Blueprint provides a
free FastAPI service plus a static CDN frontend with cache and security headers.

## 12. Verification evidence

The final local quality matrix includes:

| Gate | Result |
| --- | --- |
| Backend Pytest suite | 68 passed |
| Backend statement coverage | 88.79%, above 70% CI threshold |
| Python Ruff lint | Passed |
| Python dependency consistency | `pip check` passed |
| Python vulnerability audit | 0 known vulnerabilities |
| Frontend Vitest suite | 11 passed |
| Frontend Oxlint | Passed with 0 warnings |
| Vite production build | Passed |
| npm high-severity audit | 0 vulnerabilities |
| Provided KML direct analysis | Passed; automatic, point, region, and synthetic-water cases |
| Hosted KML automatic upload | HTTP 200 in 12.47 s with complete typed response |
| Hosted manual point selection | HTTP 200; catchment recomputed to 301.1143 ha |
| Hosted region selection | HTTP 200; option 2 selected, 381.4633 ha |
| Hosted KMZ upload | HTTP 200; result matched the source KML |
| Hosted invalid point | HTTP 422, typed `invalid_contour_selection` |
| OpenAPI schema route | Passed |
| Docker backend build | Included in local/CI verification |
| Docker frontend build | Included in local/CI verification |
| Alembic PostgreSQL migration | Included in GitHub Actions |
| Hosted frontend and security headers | HTTP 200; frame, MIME and referrer headers passed |
| Hosted API readiness and OpenAPI | Verified through the deployed service |
| Hosted 2 km location analysis | 35 rainfall years; 152.07 ha selected catchment; three pond options |

Backend tests cover contour/KMZ safety, parsing variants, KML route behavior,
input limits, D8 flow, accumulation, selected-point catchment traversal,
priority-flood, boundary/water masking, option separation, manual point and
region validation, runoff equations, frustum sizing, imagery validation,
rainfall gaps, upstream failures, response quality, security defaults, rate
limiting, health, and privacy defaults. Frontend tests cover explicit search,
search validation, rainfall rendering, select-then-confirm analysis, KML upload,
ranked options, complete output rendering, and contour-selection interactions.

## 13. Deployment and submission

The repository contains `render.yaml` for repeatable deployment in the Singapore
region. Release `0a385c0` was deployed and verified on 29 August 2026:

- Frontend: https://sneha-village-pond-planning-2026.onrender.com
- API: https://sneha-village-pond-api-2026.onrender.com
- API documentation: https://sneha-village-pond-api-2026.onrender.com/docs

Free Render web services can sleep after inactivity, so the first API request
may require a cold-start wait. The final hosted KML verification processed all
1,355 contours and 159,113 source vertices in 12.47 seconds, returned three
ranked and water-screened alternatives, and completed the rainfall, runoff, and
pond-geometry branches. Point and region re-selection, KMZ upload, and negative
selection rejection were then exercised against the same deployed release.

The final hosted location test also exercised the complete fallback rainfall and
pond paths: 35 complete rainfall years, 1,324.2 mm mean annual rainfall, a
152.07 ha catchment upstream of the selected pond option, 604,080 m3 screening
runoff, 483,264 m3 capacity, and three spatially separated alternatives. The API
retains its source-quality status, while the course-project interface presents
successful calculations as complete with public-data constraints. Repeated
generic cautions were removed; evidence-specific caveats remain available in
the expandable technical notes.
Docker deployment and post-deploy checks are documented separately in
`docs/DEPLOYMENT.md`.

## 14. Limitations and required field work

Before any excavation decision, obtain:

- cadastral ownership, easements, consent, and legal land availability;
- total-station, RTK/GNSS, or equivalent terrain and outlet survey;
- soil, infiltration, erodibility, lining, slope stability and geotechnical data;
- groundwater level, recharge objective and downstream-impact assessment;
- approved runoff coefficient and intensity-duration-frequency design rainfall;
- sediment, evaporation, seepage, routing and environmental-release allowances;
- utilities, buildings, roads, crops, ecology, protected areas and water quality;
- detailed civil/geotechnical design, drawings, bill of quantities and approvals.

These limits are part of the result contract and user interface rather than
being hidden only in this report.

## 15. AI-tool usage and academic integrity

OpenAI Codex was used as an AI-assisted development tool for requirement review,
code review, debugging, refactoring suggestions, automated test development,
security checks, and documentation formatting. Generated suggestions were not
accepted as unverified output: project files were inspected, algorithms were
checked against the assignment, tests and audits were executed, failures were
corrected, and the supplied KML was processed end to end. The student remains
responsible for understanding and explaining every submitted component,
including KML parsing, interpolation, D8 hydrology, runoff equations, pond
geometry, API contracts, deployment, and limitations.

## 16. Conclusion

The completed project satisfies the assignment's software deliverables with a
generalized Phase 2 KML/KMZ catchment API, automatic and user-guided pond-site
selection, upstream catchment recomputation, detected-river exclusion,
historical rainfall, runoff and preliminary pond geometry, an integrated
accessible frontend, deployment infrastructure, and a repeatable test matrix.
The main design achievement is not only producing a result, but offering
traceable alternatives while distinguishing computed screening evidence from
facts that require cadastral, survey, environmental, and engineering authority.

## References

1. Open-Meteo Elevation API: https://open-meteo.com/en/docs/elevation-api
2. Open-Meteo Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
3. Nominatim Usage Policy: https://operations.osmfoundation.org/policies/nominatim/
4. FastAPI documentation: https://fastapi.tiangolo.com/
5. Leaflet documentation: https://leafletjs.com/reference.html
6. OpenCV documentation: https://docs.opencv.org/
7. Render Blueprint specification: https://render.com/docs/blueprint-spec
8. AWS Open Data Terrain Tiles: https://registry.opendata.aws/terrain-tiles/
9. Tilezen Terrarium format: https://github.com/tilezen/joerd/blob/master/docs/formats.md
10. NASA POWER Daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
11. Barnes et al., Priority-Flood depression filling: https://arxiv.org/abs/1511.04463
12. O'Callaghan and Mark, D8 drainage networks: https://doi.org/10.1016/S0734-189X(84)80011-0
13. OGC KML 2.3 standard: https://docs.ogc.org/is/12-007r2/12-007r2.html
14. USDA NRCS runoff-volume guidance: https://directives.nrcs.usda.gov/sites/default/files2/1720531480/Chapter%2002%20-%20Estimating%20Runoff%20Volume%20and%20Peak%20Discharge.pdf
