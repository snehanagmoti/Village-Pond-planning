"""
Pond Planner Router
-------------------
API endpoints for the Village Pond Planning System.

Endpoints:
    POST /api/analyze          — Full terrain + rainfall + land analysis
    GET  /api/search-village   — Geocode a village name to coordinates
    GET  /api/history          — Retrieve past analysis records
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from models.schemas import (
    AnalysisRequest, AnalysisResponse, RunoffStats, PondRecommendation,
    Coordinates, ContourLine, ElevationStats, RainfallData,
    MonthlyRainfall, LandAnalysis, VillageSearchResult, HistoryItem,
)
from models.database import get_db, PondAnalysis
from services.elevation import fetch_elevation_grid
from services.terrain import run_terrain_analysis, calculate_runoff, recommend_pond_dimensions
from services.rainfall import get_rainfall_data
from services.cv_analyzer import download_satellite_tile, analyze_satellite_image, barren_contour_to_polygon
from services.geocoding import search_village
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse, summary="Run full pond analysis")
async def analyze_location(request: AnalysisRequest, db: Session = Depends(get_db)):
    """
    Perform a complete terrain, rainfall, and land-cover analysis for pond planning.

    Pipeline:
    1. Fetch real DEM elevation grid from Open-Meteo
    2. Download satellite tile and run OpenCV barren-land detection
    3. Run D8 flow direction → flow accumulation → watershed delineation
    4. Query 11-year historical rainfall from Open-Meteo
    5. Calculate runoff volume (Rational Method) with CV-adjusted coefficient
    6. Recommend pond dimensions and optimal location (lowest elevation point)
    7. Save everything to PostgreSQL for auditing
    """
    lat = request.center.lat
    lng = request.center.lng
    radius = request.radius_km

    logger.info("=== Analysis started for (%.4f, %.4f) radius=%.1f km ===", lat, lng, radius)

    # ── Step 1: Fetch real elevation data ──────────────────────
    logger.info("Step 1: Fetching elevation grid...")
    dem, lat_array, lng_array = await fetch_elevation_grid(lat, lng, radius, grid_size=25)

    # ── Step 2: Satellite land-cover analysis (OpenCV) ─────────
    logger.info("Step 2: Downloading satellite tile for CV analysis...")
    sat_img = await download_satellite_tile(lat, lng, zoom=14)

    barren_ratio = 0.3
    adjusted_c = 0.3
    gov_land_raw = []

    if sat_img is not None:
        logger.info("Step 2b: Running OpenCV land analysis...")
        cv_result = analyze_satellite_image(sat_img)
        barren_ratio = cv_result["barren_ratio"]
        adjusted_c = cv_result["adjusted_runoff_coeff"]

        if cv_result["barren_contour"] is not None:
            gov_land_raw = barren_contour_to_polygon(
                cv_result["barren_contour"], lat, lng, sat_img.shape, zoom=14
            )
    else:
        logger.warning("Satellite tile unavailable, using default barren ratio")

    # ── Step 3: Terrain analysis (D8, watershed, contours) ─────
    logger.info("Step 3: Running terrain analysis (D8 flow, watershed, contours)...")
    terrain_result = run_terrain_analysis(dem, lat_array, lng_array, gov_land_raw)

    catchment_polygon_raw = terrain_result["catchment_polygon"]
    contours_raw = terrain_result["contours"]
    catchment_area_sqm = terrain_result["catchment_area_sqm"]
    pond_lat = terrain_result["pond_lat"]
    pond_lng = terrain_result["pond_lng"]
    elev_stats = terrain_result["elevation_stats"]

    # Convert to Pydantic models
    catchment_polygon = [Coordinates(lat=p["lat"], lng=p["lng"]) for p in catchment_polygon_raw]
    contours = [
        ContourLine(
            elevation=c["elevation"],
            points=[Coordinates(lat=p["lat"], lng=p["lng"]) for p in c["points"]],
        )
        for c in contours_raw
    ]
    elevation_stats = ElevationStats(**elev_stats)

    # ── Step 4: Rainfall data ──────────────────────────────────
    logger.info("Step 4: Fetching rainfall data...")
    rainfall_result = await get_rainfall_data(lat, lng)
    annual_rainfall_mm = rainfall_result["annual_avg_mm"]
    monthly_rainfall = [
        MonthlyRainfall(month=m["month"], rainfall_mm=m["rainfall_mm"])
        for m in rainfall_result["monthly"]
    ]
    rainfall_data = RainfallData(annual_avg_mm=annual_rainfall_mm, monthly=monthly_rainfall)

    # Convert raw CV polygon to Coordinates, or apply fallback
    if gov_land_raw:
        gov_land_polygon = [Coordinates(lat=p["lat"], lng=p["lng"]) for p in gov_land_raw]
    else:
        offset = 0.003
        gov_land_polygon = [
            Coordinates(lat=pond_lat - offset, lng=pond_lng - offset),
            Coordinates(lat=pond_lat - offset, lng=pond_lng + offset),
            Coordinates(lat=pond_lat + offset, lng=pond_lng + offset),
            Coordinates(lat=pond_lat + offset, lng=pond_lng - offset),
        ]

    land_analysis = LandAnalysis(barren_ratio=barren_ratio, adjusted_runoff_coeff=adjusted_c)

    # ── Step 5: Runoff calculation ─────────────────────────────
    logger.info("Step 5: Calculating runoff (C=%.3f, A=%.0f m², P=%.1f mm)...", adjusted_c, catchment_area_sqm, annual_rainfall_mm)
    volume_m3 = calculate_runoff(catchment_area_sqm, annual_rainfall_mm, adjusted_c)

    runoff_stats = RunoffStats(
        catchment_area_sqm=round(catchment_area_sqm, 2),
        annual_rainfall_mm=annual_rainfall_mm,
        runoff_coefficient=adjusted_c,
        estimated_volume_m3=round(volume_m3, 2),
    )

    # ── Step 6: Pond sizing ────────────────────────────────────
    logger.info("Step 6: Recommending pond dimensions...")
    depth, capacity, surface_area = recommend_pond_dimensions(volume_m3)

    pond = PondRecommendation(
        lat=pond_lat,
        lng=pond_lng,
        depth_m=depth,
        capacity_m3=capacity,
        surface_area_sqm=surface_area,
    )

    # ── Step 7: Save to database ───────────────────────────────
    logger.info("Step 7: Saving to database...")
    db_analysis = PondAnalysis(
        village_name=request.village_name,
        center_lat=lat,
        center_lng=lng,
        min_elevation=elev_stats["min_elevation"],
        max_elevation=elev_stats["max_elevation"],
        mean_elevation=elev_stats["mean_elevation"],
        relief=elev_stats["relief"],
        catchment_area_sqm=runoff_stats.catchment_area_sqm,
        annual_rainfall_mm=runoff_stats.annual_rainfall_mm,
        runoff_coefficient=runoff_stats.runoff_coefficient,
        estimated_volume_m3=runoff_stats.estimated_volume_m3,
        barren_ratio=barren_ratio,
        pond_lat=pond.lat,
        pond_lng=pond.lng,
        depth_m=pond.depth_m,
        capacity_m3=pond.capacity_m3,
        surface_area_sqm=pond.surface_area_sqm,
        catchment_polygon=[p.model_dump() for p in catchment_polygon],
        government_land_polygon=[p.model_dump() for p in gov_land_polygon],
        contours=[c.model_dump() for c in contours],
        monthly_rainfall=[m.model_dump() for m in monthly_rainfall],
    )

    try:
        db.add(db_analysis)
        db.commit()
        db.refresh(db_analysis)
        logger.info("Analysis saved with id=%d", db_analysis.id)
    except Exception as exc:
        logger.error("Failed to save to database: %s", exc)
        db.rollback()

    logger.info("=== Analysis complete ===")

    return AnalysisResponse(
        pond=pond,
        runoff_stats=runoff_stats,
        government_land_polygon=gov_land_polygon,
        catchment_polygon=catchment_polygon,
        contours=contours,
        elevation_stats=elevation_stats,
        rainfall_data=rainfall_data,
        land_analysis=land_analysis,
    )


@router.get("/search-village", response_model=List[VillageSearchResult], summary="Search for a village by name")
async def search_village_endpoint(q: str = Query(..., description="Village or place name to search")):
    """
    Geocode a village name using the Nominatim (OpenStreetMap) API.
    Returns up to 5 matching locations with their coordinates.
    """
    results = await search_village(q)
    return [VillageSearchResult(**r) for r in results]


@router.get("/history", response_model=List[HistoryItem], summary="Get past analysis records")
async def get_history(db: Session = Depends(get_db), limit: int = Query(20, le=100)):
    """
    Retrieve the most recent analysis records from the database.
    """
    records = (
        db.query(PondAnalysis)
        .order_by(PondAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        HistoryItem(
            id=r.id,
            created_at=r.created_at.isoformat() if r.created_at else "",
            center_lat=r.center_lat,
            center_lng=r.center_lng,
            village_name=r.village_name,
            catchment_area_sqm=r.catchment_area_sqm,
            annual_rainfall_mm=r.annual_rainfall_mm,
            estimated_volume_m3=r.estimated_volume_m3,
            pond_depth_m=r.depth_m,
            pond_capacity_m3=r.capacity_m3,
        )
        for r in records
    ]
