# Allotted development-machine verification

Verified on 26 September 2026 by logging in as `student` to `10.1.75.53` using the assigned SSH ports. Passwords are not stored in this report.

## Machine findings

- **2237 / stu70_sys1:** Backend files are present at `/home/student/village_pond_planning_backend`. No pond API was listening at the time of inspection. A separate load-balancer process occupied port 4000 and was left untouched. SHA-256 hashes of `main.py`, `services/terrain.py`, `services/contour_analyzer.py` and `routers/pond_planner.py` exactly match the local project. The old virtual environment has no pip module; its dependencies were therefore not certified with pip check.
- **2238 / stu70_sys2:** Project present at `/home/student/village-pond-api`, originally revision `74b1fcb`. The four core algorithm/API files match the local project, and `pip check` reports no broken requirements. A new combined frontend/API wrapper and locally built frontend have now been deployed. One supervised Uvicorn process serves the same application on internal ports 8000, 3000 and 8080. The frontend uses relative `/api` requests, not the Render backend. External HTTP port 3238 was subsequently verified from the laptop.
- **2239 / stu70_sys3:** SSH login succeeds. No pond checkout or application was found in the inspected home-directory locations. A separate Python service listens on port 5000 and was left untouched.
- **2240 / stu70_sys4:** SSH login succeeds. No pond checkout or application was found in the inspected home-directory locations. A separate Python service listens on port 5000 and was left untouched.

## Tests executed on system 2

- `/health/live`: HTTP 200, status `ok`.
- `/health/ready`: HTTP 200, API `ok`, optional database disabled.
- `/docs` and `/openapi.json`: HTTP 200.
- OpenAPI upload contract includes `contour_map`, `contour_file`, `selection_mode`, `selected_lat`, `selected_lng` and `selected_region`.
- An invalid latitude returns HTTP 422.
- A missing contour upload returns HTTP 422 with `missing_contour_file`.
- Full `contours_1m.kml` upload using `contour_map`: HTTP 200, `analysis_status=complete`, 32.69 seconds.
- Live analysis at latitude 21.244025, longitude 81.288000, radius 2 km: HTTP 200 with rainfall, catchment, runoff and pond geometry. Quality is `degraded` because a public elevation quota limited the grid to 23 by 23 cells; the 0.08-second response reused cached data and is not a cold-request benchmark.
- Complete backend automated suite: **68 passed in 11.67 seconds**, executed on the dev machine. Pytest was installed in isolated temporary storage from locally downloaded wheels because the machine could not resolve PyPI. The production virtual environment was not modified for the test dependency installation.

## Actual sample-contour output

The supplied KML contains 1,355 contours and 159,113 coordinate points over 32 elevation levels (267-298 m). It produces a 148 by 181 grid of 18 m cells; interpolation converged after 31 iterations.

The selected catchment is 352.952347 ha. Mean annual rainfall is 1,280.13 mm, modeled annual runoff is 1,355,474.66 cubic metres at the configured course coefficient of 0.30, and proposed storage is 1,084,379.73 cubic metres. Three candidate options are returned. The selected location is 21.244025, 81.288000, with 334.35 m modelled clearance from detected water. Water exclusion was applied with a 60 m buffer. These figures are model estimates, not surveyed construction dimensions.

## Access and submission conclusion

2237-2240 are **SSH ports**, not browser/API HTTP ports. After deploying the combined site on system 2, the following exact external routes were verified from the laptop:

- Frontend: `http://10.1.75.53:3238/` (page and map controls loaded in the browser).
- Swagger: `http://10.1.75.53:3238/docs` (HTTP 200).
- API: `POST http://10.1.75.53:3238/api/analyze-contour`, multipart field `contour_map`.
- The full supplied KML returned HTTP 200, `analysis_status=complete`, in 31.58 seconds through this external API URL, with catchment area 3,529,523.47 square metres.

Only port 3238 is now verified; do not infer that adjacent web ports work. This is a private college-network address, not a public Internet service. Initial TCP connections sometimes timed out on both SSH and HTTP; a successful request does not establish uninterrupted availability.

An established browser request was observed at system 2's internal port 3000, confirming that the working external 3238 route reaches the 3000 listener. Port 8000 remains an internal API/tunnel listener.

For access from the laptop through SSH, an example tunnel is:

```powershell
ssh -p 2238 -L 18080:127.0.0.1:8000 student@10.1.75.53
```

Keep that SSH session open, then use `http://localhost:18080/docs` from the same laptop. This tunnel example is an access method, not a public submission URL.

## Runtime and recovery

The combined frontend and API are installed on system 2 under user-owned Supervisor. Terminating the owned application process with SIGTERM caused an automatic restart (PID 177221 to 177458), followed by a successful readiness response. Unrelated services were not stopped. Supervisor survives SSH logout, but the container has no working system init; a container reboot requires the documented manual start command in `docs/LAB_DEPLOYMENT.md`.

The production frontend build passed. The final expanded backend suite passed **72 tests both locally and on system 2 (11.74 seconds remotely)**, including same-origin route/security tests and imagery-cache regression tests. All 11 frontend tests and lint also passed. System 1 has release files staged but no working application: its old virtual environment also lacks Starlette. It is not a submission target. Systems 3 and 4 remain unchanged.

A fresh browser-driven live-analysis request after the restart returned HTTP 200 in 87.93 seconds but correctly reported incomplete analysis: satellite imagery and land-cover screening were unavailable. Rainfall and terrain fallback estimates were shown, but no pond candidate was recommended. This is not a complete-workflow pass. Earlier successful cached live results do not override this observed dependency failure.

An imagery recovery improvement was subsequently deployed: valid image tiles are retained in a bounded, expiring cache even when a sibling download fails. Retry requests reuse those valid tiles; failed tiles are never cached, and incomplete mosaics remain rejected. Both successful-tile reuse and rejection of partial coverage have regression tests. This improves recovery without relaxing water/land evidence requirements.

**Post-fix browser verification succeeded:** at 21.244025, 81.288000 with a 2 km radius, the interface reported analysis complete with public-data constraints, imagery ready and three ranked pond options. The selected catchment was 119.01 ha, annual rainfall 1,324.2 mm, runoff 472,758 cubic metres/year and proposed capacity 378,206 cubic metres. Pond markers and the catchment appeared on the map, and the side panel was collapsed to inspect them. Elevation used the Terrarium fallback and the UI retains its source limitations. The successful retry does not erase the earlier observed network/source outage.

## Final submission pass

- Expanded final backend suite: **76 passed locally (7.24 s) and on system 2 (14.14 s)**. Four new independent path-walk checks compare every cell's flow accumulation and the selected upstream catchment to a separate reference implementation.
- Frontend: **13 tests passed across six files**, lint passed, production build passed (1.45 s).
- Map requirement closed: annual runoff, catchment area, pond coordinates and storage capacity are now available in an on-map summary; selected markers also expose water-volume details. The final deployed live workflow and collapsed-panel summary were checked in the browser.
- Real bounded concurrency: two simultaneous sample KML uploads returned complete status in **41.38 s and 59.05 s**. Both returned catchment 3,529,523.47 square metres, annual runoff 1,355,474.66 cubic metres and three candidates. Independent runoff multiplication and capacity bounds passed.
- All **15 simultaneous readiness probes** succeeded; maximum latency **0.271 s**. This is a small-workload check, not sustained saturation testing.
- Container limits: **512 MiB RAM and one CPU quota**, read from cgroup limits (the host-wide `free` output is not the container allocation).
- Actual sample point/region API checks passed: the warmed automatic request completed in 2.02 s; selecting the last returned candidate recomputed a **3,011,142.94 m²** catchment, while restricting the search to the supplied study boundary returned **3,529,523.47 m²**. Both returned complete status and the requested selection mode. The point coordinates were checked against the requested candidate.
- Recovery helper: `scripts/start_lab_service.sh`, deployed to `~/pond-phase3-release/`, contains no credentials. Container restart remains distinct from an application restart.

The final report has been refreshed with this deployment evidence and the on-map result screenshot, retaining the required ACM template. The user must still record/publish the required public demo video and perform the final Classroom submission. No field-survey reference data was supplied, so physical accuracy for all sites is not claimed.
