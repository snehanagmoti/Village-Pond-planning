# Allotted-system deployment

## Verified entry points

- Website: http://10.1.75.53:3238/
- Swagger: http://10.1.75.53:3238/docs
- Upload: `POST http://10.1.75.53:3238/api/analyze-contour`
- Multipart upload field: `contour_map`
- SSH: `ssh -p 2238 student@10.1.75.53` (system 2).

These are private college-network URLs. Off-campus access needs a route to that network, such as the college VPN. SSH ports 2237-2240 are not HTTP ports. Do not assume other external forwarding ports. Port 3238 was tested directly; the host's forwarding configuration itself is not managed by this project. Both SSH and HTTP occasionally timed out during verification.

Observed mapping: external **3238** reaches system 2's internal **3000** listener. Internal 8000 is also available for health checks and SSH tunnels.

## Runtime layout

Backend: `/home/student/village-pond-api/backend`.
Python: `/home/student/village-pond-api/.venv/bin/python`.
Release: `/home/student/pond-phase3-release`.
Supervisor configuration/logs: `/home/student/.local/share/pond-service`.

`web.py` mounts the built frontend and existing API in one application. The frontend is built with `VITE_API_BASE_URL=/api`, so it calls the college backend on the same origin. `/docs`, `/openapi.json` and API error responses remain available. Missing frontend builds fail startup instead of silently serving a broken site.

`lab_server.py` binds one application process to the explicitly configured internal ports 8000, 3000 and 8080. These listeners share the same cache and computation process. This is not three workers or three replicas. Existing unrelated services on port 5000 and on the other systems remain untouched.

Successful satellite tiles are retained in a bounded TTL cache to help retries recover from partial source outages. Complete imagery coverage is still required; failed tiles and partial mosaics are never treated as valid evidence.

## Health, logs and recovery

Run after SSH login:

```sh
export PYTHONPATH="$HOME/.local/share/pond-service/packages"
PY="$HOME/village-pond-api/.venv/bin/python"
CFG="$HOME/.local/share/pond-service/supervisord.conf"
"$PY" -m supervisor.supervisorctl -c "$CFG" status
curl --fail http://127.0.0.1:8000/health/ready
tail -n 60 "$HOME/.local/share/pond-service/web.log"
```

Supervisor automatically restarts an exited app process and survives SSH logout. The restart was tested. It does **not** automatically start after container reboot because these containers have no working system init. If Supervisor is not running after reboot, start it:

```sh
export PYTHONPATH="$HOME/.local/share/pond-service/packages"
"$HOME/village-pond-api/.venv/bin/python" -m supervisor.supervisord \
  -c "$HOME/.local/share/pond-service/supervisord.conf"
```

Do not run the start command when Supervisor is already active. Use `supervisorctl ... restart pond-web` for an intentional application restart instead.

## Rebuilding a release

1. Build `frontend/` with `VITE_API_BASE_URL=/api` and `VITE_API_TIMEOUT_MS=300000`.
2. Package `frontend/dist` as `dist/`, `backend/web.py`, `backend/lab_server.py`, `scripts/install_lab_service.py`, and the Supervisor 4.3.0 wheel in a release directory.
3. Transfer to system 2 with SCP using SSH port 2238 and unpack.
4. Run the installer with the existing backend and virtual environment:

```sh
"$HOME/village-pond-api/.venv/bin/python" "$HOME/pond-phase3-release/install_lab_service.py" \
  --backend "$HOME/village-pond-api/backend" \
  --python "$HOME/village-pond-api/.venv/bin/python" \
  --additional-ports 3000,8080
```

The installer validates the application before stopping its prior process. It does not install missing scientific dependencies or update the algorithm source checkout; synchronize reviewed source separately when it changes. Credentials are entered separately and are never part of the release.

## Laptop check

```powershell
curl.exe --connect-timeout 10 --max-time 300 -F "contour_map=@C:\Users\Sneha Nagmoti\Downloads\contours_1m.kml" -o result.json http://10.1.75.53:3238/api/analyze-contour
```

For temporary access through SSH if direct HTTP fails:

```powershell
ssh -p 2238 -L 18080:127.0.0.1:8000 student@10.1.75.53
```

Then open `http://localhost:18080/` on that laptop while the tunnel remains open. A localhost tunnel is not the URL to submit to evaluators.
