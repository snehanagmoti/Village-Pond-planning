import httpx
import numpy as np
import pytest

from main import app
from routers import pond_planner
from services.cv_analyzer import LandCoverResult, SatelliteMosaic
from services.elevation import ElevationGrid
from services.quality import SourceInfo, UpstreamDataError
from services.rainfall import RainfallResult


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as session:
        yield session


def _elevation():
    grid = np.tile(np.arange(9, 0, -1, dtype=float)[:, None], (1, 9))
    return ElevationGrid(
        dem=grid,
        latitudes=np.linspace(18.0, 18.01, 9),
        longitudes=np.linspace(73.0, 73.01, 9),
        source=SourceInfo(name="test elevation", status="reliable"),
        missing_ratio=0.0,
        cell_size_m=125.0,
    )


def _imagery():
    return SatelliteMosaic(
        image=np.full((128, 128, 3), 120, dtype=np.uint8),
        bounds=(18.0, 18.01, 73.0, 73.01),
        zoom=14,
        source=SourceInfo(name="test imagery", status="reliable", coverage_ratio=1.0),
    )


def _rainfall():
    return RainfallResult(
        annual_avg_mm=800.0,
        valid_years=30,
        monthly=[{"month": name, "rainfall_mm": 800 / 12, "valid_years": 30} for name in [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]],
        source=SourceInfo(name="test rainfall", status="reliable", period="1991-2020"),
    )


@pytest.mark.anyio
async def test_analysis_contract_exposes_quality_and_uses_no_fallback(monkeypatch, client):
    async def elevation(*args, **kwargs):
        return _elevation()

    async def imagery(*args, **kwargs):
        return _imagery()

    async def rain(*args, **kwargs):
        return _rainfall()

    def land(*args, **kwargs):
        return LandCoverResult(0.3, 0.4, 0.1, 0.1, None, "degraded", "screening only")

    def terrain(*args, **kwargs):
        return {
            "catchment_polygon": [
                {"lat": 18.0, "lng": 73.0}, {"lat": 18.0, "lng": 73.01},
                {"lat": 18.01, "lng": 73.01}, {"lat": 18.01, "lng": 73.0},
            ],
            "contours": [],
            "catchment_area_sqm": 1_000_000.0,
            "candidate_area_sqm": 0.0,
            "pond_location": None,
            "warnings": ["No candidate land"],
            "elevation_stats": {
                "min_elevation": 1.0, "max_elevation": 9.0, "mean_elevation": 5.0,
                "relief": 8.0, "grid_size": 9, "cell_size_m": 125.0,
            },
        }

    monkeypatch.setattr(pond_planner, "fetch_elevation_grid", elevation)
    monkeypatch.setattr(pond_planner, "download_satellite_mosaic", imagery)
    monkeypatch.setattr(pond_planner, "get_rainfall_data", rain)
    monkeypatch.setattr(pond_planner, "analyze_satellite_image", land)
    monkeypatch.setattr(pond_planner, "run_terrain_analysis", terrain)

    response = await client.post(
        "/api/analyze", json={"center": {"lat": 18.005, "lng": 73.005}, "radius_km": 1}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["analysis_status"] == "incomplete"
    assert data["quality"]["screening_only"] is True
    assert data["pond"] is None
    assert data["candidate_land_polygon"] == []
    assert data["runoff_stats"]["runoff_coefficient"] is None
    assert data["persistence"]["status"] == "disabled"
    assert not any("cadastral ownership" in note for note in data["quality"]["warnings"])


@pytest.mark.anyio
async def test_required_elevation_failure_returns_503(monkeypatch, client):
    async def elevation(*args, **kwargs):
        raise UpstreamDataError("elevation", "source unavailable")

    async def imagery(*args, **kwargs):
        return _imagery()

    async def rain(*args, **kwargs):
        return _rainfall()

    monkeypatch.setattr(pond_planner, "fetch_elevation_grid", elevation)
    monkeypatch.setattr(pond_planner, "download_satellite_mosaic", imagery)
    monkeypatch.setattr(pond_planner, "get_rainfall_data", rain)
    response = await client.post(
        "/api/analyze", json={"center": {"lat": 18.005, "lng": 73.005}, "radius_km": 1}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "elevation_unavailable"


@pytest.mark.anyio
async def test_extreme_mercator_latitude_is_rejected(client):
    response = await client.post(
        "/api/analyze", json={"center": {"lat": 89, "lng": 73}, "radius_km": 1}
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_history_is_private_by_default(client):
    response = await client.get("/api/history")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_approved_coefficient_produces_consistent_screening_geometry(monkeypatch, client):
    async def elevation(*args, **kwargs):
        return _elevation()

    async def imagery(*args, **kwargs):
        return _imagery()

    async def rain(*args, **kwargs):
        return _rainfall()

    def land(*args, **kwargs):
        contour = np.array([[[10, 10]], [[100, 10]], [[100, 100]], [[10, 100]]])
        return LandCoverResult(0.3, 0.4, 0.1, 0.1, contour, "degraded", "screening only")

    def polygon(*args, **kwargs):
        return [
            {"lat": 18.0, "lng": 73.0},
            {"lat": 18.0, "lng": 73.01},
            {"lat": 18.01, "lng": 73.01},
            {"lat": 18.01, "lng": 73.0},
        ]

    def terrain(*args, **kwargs):
        return {
            "catchment_polygon": polygon(),
            "contours": [],
            "catchment_area_sqm": 100_000.0,
            "candidate_area_sqm": 20_000.0,
            "pond_location": {"lat": 18.005, "lng": 73.005, "elevation": 4.0},
            "warnings": [],
            "elevation_stats": {
                "min_elevation": 1.0,
                "max_elevation": 9.0,
                "mean_elevation": 5.0,
                "relief": 8.0,
                "grid_size": 9,
                "cell_size_m": 125.0,
            },
        }

    monkeypatch.setattr(pond_planner, "fetch_elevation_grid", elevation)
    monkeypatch.setattr(pond_planner, "download_satellite_mosaic", imagery)
    monkeypatch.setattr(pond_planner, "get_rainfall_data", rain)
    monkeypatch.setattr(pond_planner, "analyze_satellite_image", land)
    monkeypatch.setattr(pond_planner, "contour_to_polygon", polygon)
    monkeypatch.setattr(pond_planner, "run_terrain_analysis", terrain)
    monkeypatch.setattr(pond_planner.settings, "approved_runoff_coefficient", 0.3)
    monkeypatch.setattr(
        pond_planner.settings,
        "approved_runoff_coefficient_source",
        "Approved field study 2026",
    )

    response = await client.post(
        "/api/analyze",
        json={"center": {"lat": 18.005, "lng": 73.005}, "radius_km": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pond"]["capacity_m3"] > 0
    assert data["pond"]["excavation_volume_m3"] > data["pond"]["capacity_m3"]
    assert data["pond"]["excavation_footprint_area_sqm"] <= 20_000
    assert data["runoff_stats"]["runoff_coefficient_basis"] == "Approved field study 2026"
    assert not any("Annual runoff is a screening" in note for note in data["quality"]["warnings"])
    assert not any("Peak discharge is unavailable" in note for note in data["quality"]["warnings"])


@pytest.mark.anyio
async def test_health_endpoints_report_optional_database_state(client):
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    root = await client.get("/")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "disabled"
    assert root.status_code == 200
