# Phase 3 submission checklist

## Ready

- Final report: `output/pdf/Phase_3_Final_Technical_Report.pdf` (9 pages, supplied template, college deployment and measured results included).
- GitHub: `https://github.com/snehanagmoti/Village-Pond-planning`.
- Frontend: `http://10.1.75.53:3238/` (college network).
- Backend upload: `POST http://10.1.75.53:3238/api/analyze-contour`, field `contour_map`.
- Swagger: `http://10.1.75.53:3238/docs`.
- Backend tests: 76 passed locally and on system 2 (33.84 seconds remotely in the 27 September recheck), including independent hydrology reference checks.
- Frontend tests: 14 passed across six files; selection-preserving retry fix deployed.
- Frontend lint and production build: passed.
- Contour workflow: KML/KMZ, point and region API checks passed; fresh manual desktop/mobile results and screenshots included. Live workflow has earlier successful evidence, but the latest run and retry were incomplete because satellite imagery was unavailable.
- Two concurrent sample-contour requests completed; 15 health checks passed while they ran. See `DEV_MACHINE_VERIFICATION.md` for exact timings and resource limits.

## Must be completed before pressing “Mark as done”

- Final human-voice demo uploaded: `https://youtu.be/Kt8YKtDSnM0`.
- Verify the public YouTube URL while signed out.
- Add the PDF, GitHub URL, frontend URL and YouTube URL to the Classroom submission.
- Check the college frontend `http://10.1.75.53:3238/` immediately before the demo. Intermittent network connection timeouts were observed.
- Recheck live-source availability before the demo: the latest 27 September run and retry could not produce a pond recommendation because imagery was unavailable. Do not treat the earlier successful result as a current pass.
- Open every submitted link once from an incognito/private window.

## Allotted systems

The assigned SSH ports are 2237, 2238, 2239 and 2240 at `student@10.1.75.53`. System 2 now serves both frontend and API at `http://10.1.75.53:3238/`; Swagger is at `/docs`. A full contour upload through this URL returned HTTP 200 and complete status in 31.58 seconds. Supervisor application restart was verified. System 1 has staged files but an incomplete virtual environment; systems 3 and 4 are not pond deployment targets. See `DEV_MACHINE_VERIFICATION.md` and `../docs/LAB_DEPLOYMENT.md` for evidence and recovery commands. Only port 3238 is confirmed as an external web port.
