# A-category remediation ledger (A1–A59)

This ledger maps each software-fixable issue to the implemented control. “Fixed” means the repository no longer silently claims an unsupported result; it does not mean missing cadastral, field, hydrologic, legal, or engineering inputs have been invented.

1. **A1 — Synthetic elevation fallback:** Fixed. Required elevation failure returns HTTP 503.
2. **A2 — Weak DEM coverage validation:** Fixed. Numeric range and minimum 98 percent coverage are enforced.
3. **A3 — Fixed low-resolution analysis grid:** Fixed. Grid density scales with radius near the 90 m source resolution.
4. **A4 — Sequential/unvalidated elevation batches:** Fixed. Batches are concurrent, bounded, length-checked, retried, and fail closed.
5. **A5 — Over-aggressive elevation gap filling:** Fixed. Failed batches are rejected and only small residual gaps are interpolated.
6. **A6 — Missing DEM provenance:** Fixed. Provider, Copernicus dataset/release, resolution, coverage, time, and terms are returned.
7. **A7 — Fabricated rainfall fallback:** Fixed. Unavailable rainfall remains unavailable.
8. **A8 — Missing rainfall treated as zero:** Fixed. Null days are excluded and valid-day coverage is counted.
9. **A9 — Incorrect climatology denominator:** Fixed. Annual and monthly means use only complete calendar years.
10. **A10 — Hard-coded short rainfall period:** Fixed. Period, model, and minimum valid years are configured; default is 1991–2025.
11. **A11 — Missing rainfall provenance:** Fixed. Model, period, approximate resolution, coverage, time, and terms are returned.
12. **A12 — Silent imagery failure:** Fixed. Incomplete or malformed imagery is unavailable, never replaced.
13. **A13 — Single tile not matching radius:** Fixed. A complete multi-tile mosaic is cropped to the study bounds.
14. **A14 — No imagery quality gate:** Fixed. Shape, dimensions, coverage, brightness, and contrast are validated.
15. **A15 — Hard-coded/unreviewed external data terms:** Fixed in software. Open-Meteo and imagery endpoints/credentials are configurable and production requires authorization confirmation.
16. **A16 — “Government land” mislabelling:** Fixed. API, map, database, and docs use “bare-surface candidate.”
17. **A17 — Overlapping HSV classes:** Fixed. Water and vegetation are masked out of the bare-surface class.
18. **A18 — Ownership/suitability claim from RGB:** Fixed. Every result and interface states that RGB cannot establish either.
19. **A19 — Unbounded pixel-noise candidate:** Fixed. Morphology, minimum region area, simplification, and coordinate validation are applied.
20. **A20 — Runoff coefficient inferred from RGB:** Fixed. No coefficient is produced unless an approved value and basis are configured.
21. **A21 — DEM pits left untreated:** Fixed. Priority-flood conditioning precedes flow routing.
22. **A22 — Flat areas had no drainage:** Fixed. Deterministic sub-millimetre gradients route plateaus toward outlets.
23. **A23 — Arbitrary/global pour point:** Fixed. The maximum-accumulation natural outlet is selected, with an elevation tie-break.
24. **A24 — Circular fake catchment:** Fixed. Reverse D8 traversal delineates the watershed; no circular substitute exists.
25. **A25 — Polygon-only catchment area error:** Fixed. Area uses contributing cell count and latitude-corrected cell dimensions.
26. **A26 — Implausibly tiny watershed accepted:** Fixed. Minimum cell-count and grid-share quality gates are enforced.
27. **A27 — Candidate outside catchment accepted:** Fixed. The imagery candidate is intersected with the watershed mask.
28. **A28 — Pond placed only at lowest elevation:** Fixed. Accumulation is preferred, then elevation among ties.
29. **A29 — Depression filling hidden:** Fixed. Modified-cell ratio and maximum fill depth generate warnings.
30. **A30 — Contours tied to a fixed 25×25 grid:** Fixed. Upscaling adapts to the validated dynamic grid.
31. **A31 — Annual volume mislabeled Rational Method:** Fixed. Annual yield and Rational peak flow are separated and named correctly.
32. **A32 — Unsupported default runoff coefficient:** Fixed. Missing approval makes runoff and pond output incomplete.
33. **A33 — Peak flow from annual rainfall:** Fixed. Peak flow requires separately configured design intensity.
34. **A34 — Hidden capture-efficiency assumption:** Fixed. It is configurable, returned, and documented.
35. **A35 — Vertical-sided pond assumption:** Fixed. A configurable trapezoidal/frustum side slope is used.
36. **A36 — No freeboard:** Fixed. Water depth and excavation depth/freeboard are distinct.
37. **A37 — Capacity and excavation geometry conflated:** Fixed. Water surface/capacity and crest/footprint/excavation volume are separate.
38. **A38 — Pond footprint could exceed candidate area:** Fixed. Excavation footprint constrains the solved capacity and is flagged when binding.
39. **A39 — Engineering recommendation overstated:** Fixed. Outputs are screening-only and enumerate unmodelled design components.
40. **A40 — Weak API input validation:** Fixed. Finite coordinate bounds, name normalization, radius limits, extra-field rejection, and bounded query sizes are enforced.
41. **A41 — No abuse controls:** Fixed. Per-client analysis/search/history sliding windows include Retry-After and bounded key cleanup.
42. **A42 — Ad-hoc external HTTP calls:** Fixed. One bounded async client supplies timeouts, retry/backoff, and clean shutdown.
43. **A43 — Repeated upstream downloads:** Fixed. Bounded TTL caches cover elevation, rainfall, imagery, and geocoding.
44. **A44 — Upstream failures became generic success:** Fixed. Required failure returns 503; optional evidence produces explicit unavailable sources and incomplete status.
45. **A45 — Nominatim autocomplete/policy breach:** Fixed. Search is explicit, cached, globally throttled per instance, contactable, and provider-configurable.
46. **A46 — Scattered/untyped configuration:** Fixed. Central settings parse, bound, validate, and document environment values.
47. **A47 — Permissive web security defaults:** Fixed. Explicit CORS/hosts, security headers, production docs control, proxy body limit, and CSP are configured.
48. **A48 — Sensitive/noisy request logging:** Fixed. Coordinates and secrets are omitted; sanitized request IDs and durations remain.
49. **A49 — Missing lifecycle and readiness behavior:** Fixed. HTTP shutdown, liveness, and conditional database readiness are implemented.
50. **A50 — Schema creation/import side effects:** Fixed. Import-time creation was removed and Alembic owns schema upgrades.
51. **A51 — Public/fragile history:** Fixed. History is off by default, API-key protected when enabled, bounded, thread-contained, and non-fatal to analysis.
52. **A52 — Accidental/stale frontend analyses:** Fixed. Selection and confirmation are separate; requests can be cancelled and stale responses are ignored.
53. **A53 — UI assumed every field existed:** Fixed. Optional rainfall, land, runoff, peak, pond, persistence, and history values render safely.
54. **A54 — No visible provenance or limitations:** Fixed. Source cards, timestamps, coverage/status, terms, warnings, and a screening banner are rendered.
55. **A55 — Accessibility/responsive defects:** Fixed. Semantic forms/sections, keyboard controls, labels, live regions, focus, contrast, reduced motion, mobile layout, and textual chart descriptions are included.
56. **A56 — Floating/unscanned dependencies:** Fixed. Python and npm dependencies are exact, npm is locked, and CI audits both ecosystems.
57. **A57 — Inadequate backend quality gates:** Fixed. Algorithm, source-failure, geometry, and API tests plus Ruff and coverage run in CI.
58. **A58 — No frontend regression gates:** Fixed. Component/workflow tests, Oxlint, and optimized build run locally and in CI.
59. **A59 — No production delivery path:** Fixed. Non-root containers, reverse proxy, health checks, migrations, PostgreSQL volume, CI container builds, environment templates, and deployment/operations documentation are present.

The remaining work is intentionally outside A-category automation: provide verified local data and approvals, replace screening assumptions with a qualified design, review provider licenses, configure production secrets/domains/TLS/monitoring/backups, and conduct field validation.
