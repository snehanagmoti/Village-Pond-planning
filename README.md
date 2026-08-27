# AI-based Village Pond Planning System

This repository contains the complete Phase 2 and Phase 3 software for the
course assignment. It supports two complementary workflows:

1. Upload a KML/KMZ contour map, reconstruct a terrain surface, identify a
   drainage candidate, delineate its catchment, and return structured JSON.
2. Select a real location and combine elevation, rainfall, satellite imagery,
   hydrology, runoff assumptions, and pond geometry in one screening interface.

The system is intentionally a **screening prototype**, not a construction
design, cadastral record, or approval authority. It reports unavailable data and
quality limitations instead of inventing convincing fallback values.

## Submission links

- GitHub: <https://github.com/snehanagmoti/Village-Pond-planning>
- Live Render frontend:
  <https://sneha-village-pond-planning-2026.onrender.com>
- Live Render API:
  <https://sneha-village-pond-api-2026.onrender.com>
- Live interactive API documentation:
  <https://sneha-village-pond-api-2026.onrender.com/docs>
- Final report source: [Final_Technical_Report.md](Final_Technical_Report.md)
- API reference: [docs/API.md](docs/API.md)
- Deployment guide: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Assignment requirements implemented

### Phase 2: contour catchment backend

- accepts KML and KMZ as a bounded multipart upload;
- extracts contour elevations from standard KML names, data properties, or
  constant altitude coordinates;
- validates XML, coordinates, archive safety, file size, contour count, point
  count, elevation levels, and elevation range;
- derives the study boundary from an uploaded polygon or contour hull;
- rasterizes contour observations and performs fixed-observation harmonic
  interpolation without sample-specific coordinates or outputs;
- conditions the surface, resolves flats, computes D8 flow direction and flow
  accumulation, selects a candidate point, and reverse-delineates its catchment;
- returns a typed JSON response containing contour summary, grid quality,
  candidate point, catchment area and boundary, provenance, and warnings;
- exposes the canonical `POST /api/analyze-contour` route plus compatible
  `/api/analyzeContour` and `/api/findCatchment` aliases;
- provides a complete upload workflow in the React frontend and Swagger/ReDoc
  documentation in the backend.

### Phase 3: complete application and demo

- satellite map with click, coordinate, and explicit place-search selection;
- radius-aware elevation grid and hydrologic screening;
- bounded, validated Terrarium terrain-tile fallback when the primary elevation
  provider rejects the deployment host;
- historical ERA5-Land rainfall climatology with valid-year accounting;
- NASA POWER daily precipitation fallback with the same complete-year checks
  when the primary archive quota is unavailable;
- satellite RGB/HSV surface screening labelled as a candidate only;
- annual runoff only when an approved coefficient and source are configured;
- peak discharge only when an approved design intensity is configured;
- side-sloped pond geometry with water depth, freeboard, water dimensions,
  excavation crest/bottom dimensions, capacity, excavation volume, and area;
- visible source provenance, analysis status, warnings, cancellation, stale
  response protection, responsive layout, and accessible status messages;
- reproducible Docker Compose and Render Blueprint deployments;
- automated backend, frontend, migration, dependency, and container CI gates.

## Architecture

```text
React + Leaflet static frontend
    |-- multipart KML/KMZ ----> FastAPI contour-analysis route
    |                              |-- safe KML/KMZ parser
    |                              |-- contour rasterization/interpolation
    |                              `-- shared D8 hydrology
    |
    `-- location/radius JSON ---> FastAPI live-source analysis route
                                   |-- Open-Meteo elevation + bounded tile fallback
                                   |-- Open-Meteo rainfall + NASA POWER fallback
                                   |-- configurable imagery tiles + OpenCV
                                   `-- runoff and pond screening

Optional protected history ----> PostgreSQL + Alembic
```

## Local development

Prerequisites: Python 3.12 and Node.js 24. PostgreSQL 17 is needed only when
protected history is enabled.

Backend on Windows:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --requirement requirements-dev.txt
Copy-Item .env.example .env
uvicorn main:app --reload
```

Frontend in another terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite proxy sends `/api` to
`http://127.0.0.1:8000`, whose interactive docs are at `/docs`.

Test the provided contour map directly:

```powershell
curl.exe -X POST `
  -F "contour_file=@C:\Users\Sneha Nagmoti\Downloads\contours_1m.kml" `
  http://127.0.0.1:8000/api/analyze-contour
```

## Verification

```powershell
cd backend
ruff check .
pytest --cov --cov-report=term-missing --cov-fail-under=70
pip check
pip-audit --requirement requirements.txt

cd ..\frontend
npm run lint
npm run test
npm run build
npm audit --audit-level=high

cd ..
docker compose config
docker build --tag village-pond-backend:test backend
docker build --tag village-pond-frontend:test frontend
```

GitHub Actions repeats the backend/frontend gates, runs Alembic against a real
PostgreSQL service, audits both dependency trees, and builds both containers.

## API summary

- `POST /api/analyze-contour` - upload KML/KMZ and compute a contour-derived
  catchment (`contour_file` multipart field, 15 MiB default limit).
- `POST /api/analyze` - run location/radius screening (0.5-5 km default).
- `GET /api/search-village?q=...` - explicitly submitted place search.
- `GET /api/history?limit=...` - optional protected history; disabled by default.
- `GET /health/live` and `GET /health/ready` - health endpoints.
- `GET /docs`, `/redoc`, and `/openapi.json` - API documentation when enabled.

Errors contain a stable `detail.code` and safe `detail.message`. See
[docs/API.md](docs/API.md) for request formats, response fields, validation, and
error behavior.

## Algorithms and scientific limits

The uploaded contours are observations, not a raster DEM. The service preserves
observed contour cells, interpolates between them, masks the study area, and
passes the resulting grid through the shared hydrology pipeline. The candidate
is the cell with maximum contributing area inside the supported domain, with
lower elevation used as a tie-breaker. Reverse D8 traversal determines the
contributing cells and latitude-corrected grid spacing determines catchment area.

The live workflow uses a priority-flood conditioned DEM, deterministic flat
resolution, steepest-descent D8 routing, watershed extraction, and source-aware
quality gates. Annual water yield is `V = C x A x P`; peak flow uses
`Q = C x i x A / 3.6` only when the required approved values exist. Pond volume
uses rectangular-frustum geometry with configurable side slopes and freeboard.

These outputs remain sensitive to contour quality, DEM resolution, boundary
truncation, roads and culverts, soil, infiltration, groundwater, sediment,
seepage, evaporation, rainfall extremes, land ownership, ecology, and field
conditions. Survey and qualified engineering verification are required.

## Configuration and privacy

Copy the relevant `.env.example` and review every value. Important controls:

- production mode requires explicit CORS and trusted hosts, a contactable
  geocoding user agent, HTTPS providers, and affirmative provider-terms gates;
- precise-location history is disabled unless explicitly enabled with a strong
  API key and database credentials;
- runoff coefficients and design rainfall intensities remain blank until their
  approved sources are documented;
- upload, archive, geometry, grid, external-call, rate, and cache limits are
  configurable;
- secrets belong in an untracked `.env` or deployment secret manager.

The public course demo uses `APP_ENV=demo`, keeps history disabled, and labels
`C=0.30` as a course screening scenario so the complete runoff/geometry path can
be demonstrated. That value must be replaced by an approved site-specific
coefficient for real work. The demo does not represent an assertion of
commercial production rights for third-party data.

## Deployment

`render.yaml` provisions a free FastAPI service and static React site. Follow
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) to connect the repository and verify the
public URLs. For self-hosting, copy the root `.env.example`, replace every
placeholder, and use `docker compose up -d` behind managed HTTPS.

## Repository map

- `backend/` - FastAPI service, geospatial/hydrology code, migrations, tests.
- `frontend/` - React/Leaflet interface, tests, Nginx container.
- `docs/API.md` - request/response and route documentation.
- `docs/DEPLOYMENT.md` - Render and Docker deployment procedure.
- `Final_Technical_Report.md` - final report source.
- `output/pdf/` - rendered final report after generation.
- `.github/workflows/ci.yml` - continuous integration quality gates.
- `render.yaml` and `docker-compose.yml` - cloud and container infrastructure.
