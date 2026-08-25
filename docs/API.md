# Village Pond Planning API

The FastAPI service exposes OpenAPI documentation at `/docs` and the schema at
`/openapi.json` whenever `ENABLE_API_DOCS=true`. All analysis responses are
screening outputs, not construction designs or land-ownership determinations.

## Base URLs

- Local development: `http://127.0.0.1:8000`
- Docker Compose through the frontend proxy: `http://127.0.0.1:8080`
- Render blueprint API: `https://sneha-village-pond-api-2026.onrender.com`

## Contour upload and catchment analysis

### `POST /api/analyze-contour`

Uploads a KML or KMZ contour map, reconstructs a gridded elevation surface,
delineates the D8 catchment draining to the strongest candidate point, and
returns structured JSON. The multipart field name is `contour_file`.

Compatibility aliases required by common assignment wording are also accepted:

- `POST /api/analyzeContour`
- `POST /api/findCatchment`

The canonical kebab-case route is the only one displayed in OpenAPI.

PowerShell example:

```powershell
curl.exe -X POST `
  -F "contour_file=@C:\path\to\contours_1m.kml" `
  http://127.0.0.1:8000/api/analyze-contour
```

KML requirements:

- at least three `LineString` contour features at three distinct elevations;
- at least 0.5 m total elevation range;
- WGS84 longitude/latitude coordinates within the supported range;
- elevation stored as a numeric Placemark name, an elevation-like
  `Data`/`SimpleData` property, or a constant third coordinate value;
- an optional `Polygon` can define the study boundary; otherwise the service
  derives a bounded hull from the contour geometry.

The server accepts at most 15 MiB compressed input. KMZ expansion, archive entry
count, compression ratio, contour count, point count, XML DTD/entity content,
grid size, and interpolation work are bounded to reduce resource-exhaustion risk.

Successful response shape:

```json
{
  "analysis_status": "degraded",
  "input_file": "contours_1m.kml",
  "input_format": "kml",
  "contour_summary": {
    "contour_count": 1355,
    "source_point_count": 159113,
    "elevation_level_count": 32,
    "minimum_elevation_m": 267.0,
    "maximum_elevation_m": 298.0,
    "median_contour_interval_m": 1.0
  },
  "grid": {
    "rows": 148,
    "columns": 181,
    "cell_size_m": 18.0,
    "observed_cell_ratio": 0.85206,
    "interpolation_iterations": 31,
    "interpolation_converged": true,
    "method": "Contour rasterization with fixed-observation harmonic interpolation"
  },
  "pond_location": {
    "lat": 21.239822,
    "lng": 81.286438,
    "elevation_m": 271.323,
    "selection_method": "Maximum D8 contributing area within the uploaded study boundary, with lower elevation as tie-breaker"
  },
  "catchment": {
    "area_sqm": 3921224.77,
    "area_hectares": 392.1225,
    "cell_count": 12103,
    "study_grid_fraction": 0.46386,
    "boundary": [{ "lat": 21.23, "lng": 81.28 }]
  },
  "study_area_boundary": [{ "lat": 21.22, "lng": 81.27 }],
  "quality": {
    "status": "degraded",
    "screening_only": true,
    "sources": {},
    "warnings": []
  }
}
```

The example is abbreviated; boundary arrays contain at least three points and
source metadata is included in the real response. Contour results are always
`degraded` by design because interpolation is not equivalent to a surveyed DEM.

Errors:

- `413 contour_file_too_large` - configured upload limit exceeded.
- `422 invalid_contour_file` - unsupported, unsafe, malformed, or insufficient
  contour content.
- `429 rate_limit_exceeded` - per-client contour request budget exceeded.
- `500 contour_analysis_failed` - unexpected processing failure.

## Location-based screening

### `POST /api/analyze`

Runs the live-source terrain, rainfall, imagery, runoff, and pond-screening
workflow.

```json
{
  "center": { "lat": 18.5204, "lng": 73.8567 },
  "radius_km": 2.0,
  "village_name": "Pune"
}
```

`radius_km` is limited to 0.5-5.0 km by default. The response includes
`analysis_status`, source provenance, elevation statistics, display contours,
catchment and candidate polygons, rainfall climatology, surface-screening
ratios, runoff values when an approved coefficient is configured, optional pond
geometry, warnings, and persistence status.

## Place search

### `GET /api/search-village?q=<query>`

Performs an explicitly submitted Nominatim search. Queries must contain at least
three characters. At most five validated WGS84 results are returned.

## Protected history

### `GET /api/history?limit=20`

Disabled by default to avoid retaining exact locations. When enabled, the
request must include `X-API-Key`. `limit` is bounded from 1 to 100.

## Health and metadata

- `GET /` - service metadata and documentation path.
- `GET /health/live` - process liveness.
- `GET /health/ready` - database readiness only when history is enabled.
- `GET /docs` - Swagger UI when enabled.
- `GET /redoc` - ReDoc when enabled.
- `GET /openapi.json` - OpenAPI 3 schema when enabled.

API responses include a sanitized `X-Request-ID`. Analysis routes are
`Cache-Control: no-store` and include anti-sniffing, frame, referrer, and
permissions headers.
