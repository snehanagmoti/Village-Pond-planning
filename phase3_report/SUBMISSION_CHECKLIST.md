# Phase 3 submission checklist

## Ready

- Final report: `output/pdf/Phase_3_Final_Technical_Report.pdf` (10 pages, supplied ACM template, regenerated 15 October 2026 with the water-exclusion results).
- GitHub: `https://github.com/snehanagmoti/Village-Pond-planning` (CI passing).
- Frontend: `http://10.1.75.53:3238/` (college network); running commit `c641fc2`, verified 15 October.
- Backend upload: `POST http://10.1.75.53:3238/api/analyze-contour`, field `contour_map`.
- Swagger: `http://10.1.75.53:3238/docs`.
- Backend tests: 85 passed; frontend 14 passed; lint, build and GitHub CI passed (commit `c641fc2`).
- Supplied KML through the college URL: complete in 6.2 s; 50.90 ha catchment, 195,470 m3/yr runoff, 156,376 m3 storage; three options on land, each re-selectable; region selection and 422 error cases checked.
- Two concurrent KML uploads (5.8-5.9 s, identical results) and ten health probes (max 0.354 s). See `DEV_MACHINE_VERIFICATION.md` (15 October section).
- Live analysis at 21.244025, 81.288 (2 km): HTTP 200, `degraded` (fallback elevation/rainfall), one eligible site.

## Must be completed before pressing “Mark as done”

- Final human-voice demo uploaded: `https://youtu.be/Kt8YKtDSnM0`.
- Verify the public YouTube URL while signed out.
- Add the PDF, GitHub URL, frontend URL and YouTube URL to the Classroom submission.
- Check the college frontend `http://10.1.75.53:3238/` immediately before the demo. Intermittent network connection timeouts were observed.
- If system 2 is unreachable before the demo, SSH in and run `sh "$HOME/pond-phase3-release/start_lab_service.sh"` (the container restart on/before 15 October stopped the service).
- Open every submitted link once from an incognito/private window.

## Allotted systems

The assigned SSH ports are 2237, 2238, 2239 and 2240 at `student@10.1.75.53`. System 2 now serves both frontend and API at `http://10.1.75.53:3238/`; Swagger is at `/docs`. A full contour upload through this URL returned HTTP 200 and complete status in 31.58 seconds. Supervisor application restart was verified. System 1 has staged files but an incomplete virtual environment; systems 3 and 4 are not pond deployment targets. See `DEV_MACHINE_VERIFICATION.md` and `../docs/LAB_DEPLOYMENT.md` for evidence and recovery commands. Only port 3238 is confirmed as an external web port.
