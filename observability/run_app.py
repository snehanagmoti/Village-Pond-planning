"""Run the pond API with OpenTelemetry enabled for the Lab 8 demonstration.

    python observability/run_app.py --port 8001 --offline-fixtures
    python observability/run_app.py --port 8002

--offline-fixtures replaces ONLY the three external data adapters (satellite
tiles, OpenStreetMap tiles, rainfall API) with deterministic local fixtures for
machines that cannot reach those services. Contour parsing, interpolation,
Priority-Flood, D8, ranking, catchment and runoff code all run unchanged.
Without the flag the real network adapters are used.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8001)
parser.add_argument("--offline-fixtures", action="store_true")
args = parser.parse_args()

os.environ.setdefault("OTEL_ENABLED", "true")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
os.environ.setdefault("APP_ENV", "lab-offline-fixtures" if args.offline_fixtures else "lab-live-network")
os.environ.setdefault("APPROVED_RUNOFF_COEFFICIENT", "0.30")
os.environ.setdefault("APPROVED_RUNOFF_COEFFICIENT_SOURCE", "Course demo scenario C=0.30")
os.environ.setdefault("RAINFALL_FALLBACK_ENABLED", "true")
os.environ.setdefault("ELEVATION_FALLBACK_ENABLED", "true")

if args.offline_fixtures:
    import numpy as np

    from routers import pond_planner
    from services.cv_analyzer import (
        LandCoverResult,
        MappedHydrography,
        SatelliteMosaic,
        _study_bounds,
    )
    from services.quality import SourceInfo
    from services.rainfall import RainfallResult

    MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    MONTHLY_MM = [9, 8, 10, 12, 25, 190, 366, 330, 210, 45, 6, 5]  # sums to ~1,216 mm

    async def satellite(lat, lng, radius_km):
        return SatelliteMosaic(np.full((256, 256, 3), 120, np.uint8), _study_bounds(lat, lng, radius_km), 14,
                               SourceInfo(name="Offline imagery fixture", status="degraded", coverage_ratio=1.0))

    async def hydrography(lat, lng, radius_km):
        return MappedHydrography(np.zeros((256, 256), np.uint8), _study_bounds(lat, lng, radius_km),
                                 SourceInfo(name="Offline hydrography fixture", status="degraded"))

    def land(image):
        return LandCoverResult(0.3, 0.4, 0.1, 0.1, None, "degraded", "offline fixture",
                               water_mask=np.zeros(image.shape[:2], np.uint8))

    async def rainfall(lat, lng):
        return RainfallResult(annual_avg_mm=float(sum(MONTHLY_MM)), valid_years=30,
                              monthly=[{"month": m, "rainfall_mm": v, "valid_years": 30} for m, v in zip(MONTHS, MONTHLY_MM)],
                              source=SourceInfo(name="Offline rainfall fixture", status="degraded"))

    pond_planner.download_satellite_mosaic = satellite
    pond_planner.download_mapped_hydrography = hydrography
    pond_planner.analyze_satellite_image = land
    pond_planner.get_rainfall_data = rainfall

import uvicorn  # noqa: E402

from main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
