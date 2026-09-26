# Phase 3 submission checklist

## Ready

- Final report: `output/pdf/Phase_3_Final_Technical_Report.pdf` (8 pages, supplied template, visually verified).
- GitHub: `https://github.com/snehanagmoti/Village-Pond-planning`.
- Frontend: `https://sneha-village-pond-planning-2026.onrender.com/`.
- Backend: `https://sneha-village-pond-api-2026.onrender.com`.
- Swagger: `https://sneha-village-pond-api-2026.onrender.com/docs`.
- Backend tests: 72 passed locally and on system 2 (11.74 seconds remotely), including combined frontend/API routes and imagery-cache recovery.
- Frontend tests: 11 passed across five files.
- Frontend lint and production build: passed.
- Live and contour workflows: verified with mapped pond options, catchment and volume.

## Must be completed before pressing “Mark as done”

- Record the maximum-five-minute demo using `DEMO_SCRIPT.md`.
- Upload it to YouTube and verify the public URL while signed out.
- Add the PDF, GitHub URL, frontend URL and YouTube URL to the Classroom submission.
- Refresh the final report PDF with the verified college deployment URLs and latest measured timings; the current PDF predates that deployment.
- Check the college frontend `http://10.1.75.53:3238/` immediately before the demo. Intermittent network connection timeouts were observed.
- Recheck live-source availability before the demo: after the imagery-cache recovery fix, browser analysis completed with three pond options, but an earlier upstream outage correctly produced an incomplete result.
- Open every submitted link once from an incognito/private window.

## Allotted systems

The assigned SSH ports are 2237, 2238, 2239 and 2240 at `student@10.1.75.53`. System 2 now serves both frontend and API at `http://10.1.75.53:3238/`; Swagger is at `/docs`. A full contour upload through this URL returned HTTP 200 and complete status in 31.58 seconds. Supervisor application restart was verified. System 1 has staged files but an incomplete virtual environment; systems 3 and 4 are not pond deployment targets. See `DEV_MACHINE_VERIFICATION.md` and `../docs/LAB_DEPLOYMENT.md` for evidence and recovery commands. Only port 3238 is confirmed as an external web port.
