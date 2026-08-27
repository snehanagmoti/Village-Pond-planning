# Deployment guide

## Render submission deployment

The root `render.yaml` defines two free services in the Singapore region:

- `sneha-village-pond-api-2026` - FastAPI web service;
- `sneha-village-pond-planning-2026` - Vite/React static site.

Active public URLs, deployed and verified on 26 August 2026:

- frontend: `https://sneha-village-pond-planning-2026.onrender.com`
- API: `https://sneha-village-pond-api-2026.onrender.com`
- API docs: `https://sneha-village-pond-api-2026.onrender.com/docs`

Deploy steps:

1. Push the repository to the `main` branch on GitHub.
2. In Render, choose **New > Blueprint**.
3. Connect `snehanagmoti/Village-Pond-planning` and keep the Blueprint path as
   `render.yaml`.
4. Review the two free services and apply the Blueprint.
5. Wait for the API health check and static-site build to pass.
6. If Render changes either service slug, update `CORS_ORIGINS`,
   `TRUSTED_HOSTS`, and `VITE_API_BASE_URL` to the actual URLs and redeploy.

The hosted course demo intentionally uses `APP_ENV=demo`, leaves history
disabled, and does not assert production rights that the repository owner has
not personally reviewed. It configures `C=0.30` as an explicitly labelled course
screening scenario so the runoff and pond-geometry path can be demonstrated; it
is not a site-approved engineering value. A production operator must replace it,
confirm provider terms, and set the production gates described in
`.env.example`.

The API also enables a bounded Terrain Tiles fallback for elevation-provider
outages. Keep the HTTPS template, zoom, tile-count limit, and byte limit explicit
in production. Fallback results are source-labelled and degraded; they do not
replace a field survey.

NASA POWER daily precipitation is enabled as a bounded rainfall fallback for
Open-Meteo archive quota failures. Its MERRA-2 grid is coarser and therefore
reported as degraded even when all configured calendar years are complete.

Render free web services may sleep after inactivity. Allow time for the first
API request to wake the backend before judging the endpoint.

The recorded hosted verification returned HTTP 200 for the homepage, liveness
endpoint, OpenAPI schema, and supplied KML upload. The KML request completed in
6.66 seconds and returned 1,355 contours, 159,113 source vertices, a 148 x 181
grid, and a 392.1225 ha catchment.

Post-deploy checks:

```powershell
curl.exe https://sneha-village-pond-api-2026.onrender.com/health/live
curl.exe https://sneha-village-pond-api-2026.onrender.com/openapi.json
curl.exe -X POST `
  -F "contour_file=@C:\path\to\contours_1m.kml" `
  https://sneha-village-pond-api-2026.onrender.com/api/analyze-contour
```

Then open the frontend, upload the same KML in the Phase 2 panel, confirm the
map layers and metrics appear, and test a coordinate-based location workflow.

## Docker Compose deployment

For a self-managed deployment, copy `.env.example` to an untracked `.env` and
replace every placeholder. The production Compose configuration deliberately
requires explicit provider-authorization confirmations.

```powershell
Copy-Item .env.example .env
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl.exe http://127.0.0.1:8080/health/live
```

The browser-facing container listens on port 8080 and proxies `/api` to the
private backend service. PostgreSQL stores history only when explicitly enabled.

Before a real production launch, add managed TLS, a distributed rate limiter,
centralized logging and alerting, tested backups, secret rotation, an approved
imagery/data plan, and a qualified engineering review of all field inputs.
