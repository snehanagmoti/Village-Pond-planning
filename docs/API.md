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
screens satellite water, ranks spatially separated pond alternatives, delineates
the D8 catchment draining to the selected candidate, queries historical
rainfall, and returns runoff plus preliminary pond geometry. The multipart field
name is `contour_file`.

Selection fields are optional multipart form values:

- `selection_mode=automatic` ranks the full eligible study area (default);
- `selection_mode=point` requires `selected_lat` and `selected_lng`; the point
  is snapped to the terrain grid and rejected if it is outside the study area,
  on an outlet, inside detected water, or inside the configured boundary setback;
- `selection_mode=region` requires `selected_region`, a JSON array containing
  3-100 `{ "lat": ..., "lng": ... }` vertices. Options are ranked only inside
  that polygon.

Compatibility aliases required by common assignment wording are also accepted:

- `POST /api/analyzeContour`
- `POST /api/findCatchment`

The canonical kebab-case route is the only one displayed in OpenAPI.

PowerShell example:

```powershell
curl.exe -X POST `
  -F "contour_file=@C:\path\to\contours_1m.kml" `
  -F "selection_mode=automatic" `
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
    "lat": 21.244025,
    "lng": 81.288,
    "elevation_m": 270.0,
    "boundary_distance_m": 467.99,
    "local_slope_percent": 2.899,
    "suitability_score": 95.09,
    "contributing_area_sqm": 3529523.47,
    "water_distance_m": 120.0,
    "selection_method": "Highest spatially separated multi-criteria terrain score after boundary, outlet and detected-water checks"
  },
  "candidate_options": [
    {
      "rank": 1,
      "lat": 21.244025,
      "lng": 81.288,
      "suitability_score": 95.09,
      "contributing_area_hectares": 352.9523,
      "local_slope_percent": 2.899,
      "selected": true
    }
  ],
  "selection": {
    "mode": "automatic",
    "requested_point": null,
    "requested_region": [],
    "snapped_distance_m": null
  },
  "catchment": {
    "area_sqm": 3529523.47,
    "area_hectares": 352.9523,
    "cell_count": 10893,
    "study_grid_fraction": 0.4175,
    "boundary": [{ "lat": 21.23, "lng": 81.28 }]
  },
  "rainfall_data": {
    "annual_avg_mm": 1324.16,
    "valid_years": 35,
    "monthly": []
  },
  "runoff_stats": {
    "catchment_area_sqm": 3529523.47,
    "annual_rainfall_mm": 1324.16,
    "runoff_coefficient": 0.3,
    "estimated_volume_m3": 1402022.21
  },
  "pond": {
    "lat": 21.244025,
    "lng": 81.288,
    "water_depth_m": 4.0,
    "capacity_m3": 1121617.77
  },
  "water_screening": {
    "status": "applied",
    "detected_water_ratio": 0.015,
    "exclusion_buffer_m": 60.0,
    "message": "Detected water was excluded before candidate scoring; non-detection is not proof that a river is absent."
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

The example is abbreviated; pond geometry, candidate metrics, monthly rainfall,
boundary arrays and source metadata contain more fields in the real response.
Contour results are always
`degraded` by design because interpolation is not equivalent to a surveyed DEM.

Errors:

- `413 contour_file_too_large` - configured upload limit exceeded.
- `422 invalid_contour_file` - unsupported, unsafe, malformed, or insufficient
  contour content, or a selected point/region that fails terrain safeguards.
- `422 invalid_contour_selection` - malformed selection mode, point, or region.
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

Elevation acquisition first uses the configured point API. If that provider is
unavailable, the service can use a bounded HTTPS fallback backed by Terrarium-
encoded Terrain Tiles. Tile count, response size, PNG type, dimensions,
channels, decoded range, and coverage are validated; fallback results are
labelled degraded with their own source URL and are never presented as survey
data.

Historical rainfall first uses the configured Open-Meteo archive model. When
that provider is unavailable or quota-limited, a bounded NASA POWER fallback
requests daily `PRECTOTCORR` values for the same configured years. The service
still requires complete calendar years, rejects missing/sentinel values, caps
response size, and labels the coarser MERRA-2 grid result degraded.

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
