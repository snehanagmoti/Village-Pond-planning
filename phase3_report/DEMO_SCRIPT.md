# Phase 3 public demo script (target: 4 minutes 30 seconds)

## 0:00-0:25 - Problem and objective

“This project is an AI- and geospatial-assisted village pond planning system. It combines elevation, drainage, satellite land evidence and historical rainfall to suggest pond locations and estimate the contributing catchment and expected water volume. It is a screening tool, not a replacement for field and civil-engineering approval.”

## 0:25-1:30 - Live land-area analysis

1. Open `https://sneha-village-pond-planning-2026.onrender.com/`.
2. Select **Live analysis**.
3. Enter `21.244025, 81.288000` or click the same area on the map.
4. Keep the default radius and click **Start screening analysis**.
5. While it runs, explain that elevation, satellite imagery and rainfall are requested concurrently.
6. Point out the selected radius, candidate-land mask, catchment boundary, reconstructed contours and the three numbered pond options.

Narration: “The top options are not arbitrary map pins. Each lies inside eligible land, outside detected water and the boundary setback, and is ranked using flow accumulation, elevation, slope and clearance.”

## 1:30-2:20 - Results

Show the result cards and read the units:

- catchment area: approximately 119.01 ha;
- mean annual rainfall: approximately 1,324.2 mm/year;
- expected runoff: approximately 472,758 m³/year using the displayed coefficient;
- selected pond capacity: approximately 378,206 m³;
- water depth and dimensions; and
- source-quality and technical notes.

Select option 2 and then option 1 again to show that the catchment and pond geometry are tied to the chosen candidate.

## 2:20-3:20 - Contour upload

1. Switch to **Contour upload**.
2. Upload `contours_1m.kml` using the `contour_map` workflow.
3. Click **Analyze contour map**.
4. Expand the map and show the coloured DEM, source contours, selected catchment, modelled drainage path and three ranked options.
5. Briefly mention automatic, clicked-point and drawn-region selection.

Narration: “The KML lines are rasterized onto a metric grid. Observed contour cells remain fixed while gaps are harmonically interpolated. Priority-Flood conditions the terrain, resolved-flat D8 routes flow, and reverse traversal delineates the upstream watershed of the selected pond point.”

## 3:20-4:05 - API and validation

Open `https://sneha-village-pond-api-2026.onrender.com/docs`. Show `POST /api/analyze-contour`, noting that the assignment-compatible multipart field is `contour_map`, and show `POST /api/analyze` for live analysis.

Narration: “The API returns structured JSON, source status, quality warnings and map geometry. Invalid files, oversized archives, unsupported radii and unavailable sources are handled explicitly. The final backend suite has 68 passing tests; the frontend has 11 passing tests, and lint and production build succeed.”

## 4:05-4:30 - CSD design and conclusion

“The implementation is a modular monolith with typed REST contracts, asynchronous source calls, bounded caching, rate limits and graceful fallbacks. The analysis is stateless when optional history is disabled, so replicas can be run on the allotted systems. The final output provides the required suggested pond location, catchment area and expected water volume, all visualized on the map.”

Stop recording before 5:00. Upload as **Public** or **Unlisted only if the assignment accepts Unlisted**; otherwise choose Public. Verify the link in an incognito window before submission.
