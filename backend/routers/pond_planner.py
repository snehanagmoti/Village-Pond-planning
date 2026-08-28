"""Version-2 screening analysis, explicit place search, and protected history APIs."""

import asyncio
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile

from config import get_settings
from models.database import fetch_history, save_analysis
from models.schemas import (
    AnalysisQuality,
    AnalysisRequest,
    AnalysisResponse,
    ContourAnalysisResponse,
    ContourLine,
    Coordinates,
    ElevationStats,
    HistoryItem,
    LandAnalysis,
    MonthlyRainfall,
    PersistenceStatus,
    PondRecommendation,
    RainfallData,
    RunoffStats,
    SourceMetadata,
    VillageSearchResult,
)
from services.contour_analyzer import (
    ContourFileError,
    analyze_contour_file,
    contour_dataset_context,
    parse_contour_document,
)
from services.cv_analyzer import (
    LandCoverResult,
    analyze_satellite_image,
    buffer_terrain_exclusion,
    contour_to_polygon,
    download_satellite_mosaic,
    raster_mask_to_terrain_grid,
)
from services.elevation import fetch_elevation_grid
from services.geocoding import search_village
from services.quality import AnalysisValidationError, SourceInfo, UpstreamDataError
from services.rainfall import get_rainfall_data
from services.rate_limit import limiter
from services.terrain import (
    calculate_peak_discharge,
    calculate_runoff,
    recommend_pond_geometry,
    run_terrain_analysis,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


def _source_model(source: SourceInfo) -> SourceMetadata:
    return SourceMetadata(**source.to_dict())


def _unavailable_source(name: str, message: str) -> SourceMetadata:
    return SourceMetadata(
        name=name,
        status="unavailable",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        message=message,
    )


@router.post(
    "/analyze-contour",
    response_model=ContourAnalysisResponse,
    summary="Analyze an uploaded KML/KMZ contour map",
)
@router.post(
    "/analyzeContour",
    response_model=ContourAnalysisResponse,
    include_in_schema=False,
)
@router.post(
    "/findCatchment",
    response_model=ContourAnalysisResponse,
    include_in_schema=False,
)
async def analyze_contour_upload(
    request: Request,
    contour_file: Annotated[
        UploadFile,
        File(description="Contour map in KML or KMZ format"),
    ],
    selection_mode: Annotated[str, Form()] = "automatic",
    selected_lat: Annotated[float | None, Form()] = None,
    selected_lng: Annotated[float | None, Form()] = None,
    selected_region: Annotated[str | None, Form()] = None,
) -> ContourAnalysisResponse:
    """Reconstruct terrain from uploaded contours and delineate a watershed.

    ``/api/analyzeContour`` and ``/api/findCatchment`` are compatibility aliases
    for the assignment wording; ``/api/analyze-contour`` is the documented route.
    """
    await limiter.enforce(request, "contour", settings.rate_contour_per_minute)
    filename = contour_file.filename or "upload.kml"
    try:
        document = await contour_file.read(settings.contour_max_upload_bytes + 1)
    finally:
        await contour_file.close()
    if len(document) > settings.contour_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "contour_file_too_large",
                "message": (
                    "Contour upload exceeds the configured "
                    f"{settings.contour_max_upload_bytes // (1024 * 1024)} MB limit"
                ),
            },
        )
    mode = selection_mode.casefold().strip()
    point = None
    region = None
    try:
        if mode not in {"automatic", "point", "region"}:
            raise ValueError("Selection mode must be automatic, point, or region")
        if mode == "point":
            if selected_lat is None or selected_lng is None:
                raise ValueError("Point selection requires selected_lat and selected_lng")
            point_model = Coordinates(lat=selected_lat, lng=selected_lng)
            point = point_model.model_dump()
        if mode == "region":
            decoded = json.loads(selected_region or "null")
            if not isinstance(decoded, list) or not 3 <= len(decoded) <= 100:
                raise ValueError("Region selection requires 3 to 100 coordinate vertices")
            region = [Coordinates(**item).model_dump() for item in decoded]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_contour_selection", "message": str(exc)},
        ) from exc

    try:
        dataset, _ = await asyncio.to_thread(parse_contour_document, document, filename)
        center_lat, center_lng, coverage_radius_km = contour_dataset_context(dataset)
    except ContourFileError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_contour_file", "message": str(exc)},
        ) from exc

    rainfall_task = asyncio.create_task(get_rainfall_data(center_lat, center_lng))
    imagery_task = None
    if coverage_radius_km <= settings.analysis_max_radius_km:
        imagery_task = asyncio.create_task(
            download_satellite_mosaic(center_lat, center_lng, coverage_radius_km)
        )

    imagery_result = None
    land_result = None
    imagery_error: Exception | None = None
    if imagery_task is None:
        imagery_error = UpstreamDataError(
            "satellite_imagery",
            "Contour coverage exceeds the configured satellite-screening radius",
        )
    else:
        try:
            imagery_result = await imagery_task
            land_result = await asyncio.to_thread(
                analyze_satellite_image, imagery_result.image
            )
        except Exception as exc:
            imagery_error = exc

    try:
        result = await asyncio.to_thread(
            analyze_contour_file,
            document,
            filename,
            selection_mode=mode,
            selected_point=point,
            selected_region=region,
            water_mask=land_result.water_mask if land_result else None,
            water_bounds=imagery_result.bounds if imagery_result else None,
            water_exclusion_buffer_m=settings.contour_detected_water_setback_m,
        )
    except ContourFileError as exc:
        rainfall_task.cancel()
        await asyncio.gather(rainfall_task, return_exceptions=True)
        raise HTTPException(
            status_code=422,
            detail={
                "code": (
                    "invalid_contour_selection"
                    if mode in {"point", "region"}
                    else "invalid_contour_file"
                ),
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        rainfall_task.cancel()
        await asyncio.gather(rainfall_task, return_exceptions=True)
        logger.exception("contour_analysis_failed filename=%s", filename)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "contour_analysis_failed",
                "message": "Contour analysis failed unexpectedly",
            },
        ) from exc

    warnings = result["quality"]["warnings"]
    sources = result["quality"]["sources"]
    if imagery_result is not None and land_result is not None:
        sources["imagery"] = _source_model(imagery_result.source).model_dump(mode="json")
        sources["water_screening"] = _source_model(SourceInfo(
            name="RGB/HSV satellite water exclusion",
            status="degraded",
            resolution=imagery_result.source.resolution,
            coverage_ratio=imagery_result.source.coverage_ratio,
            message=land_result.message,
        )).model_dump(mode="json")
    else:
        message = (
            imagery_error.message
            if isinstance(imagery_error, UpstreamDataError)
            else "Satellite water screening failed"
        )
        sources["imagery"] = _unavailable_source(
            settings.imagery_source_name, message
        ).model_dump(mode="json")

    rainfall_result = await asyncio.gather(rainfall_task, return_exceptions=True)
    rainfall_value = rainfall_result[0]
    if isinstance(rainfall_value, Exception):
        message = (
            rainfall_value.message
            if isinstance(rainfall_value, UpstreamDataError)
            else "Rainfall processing failed"
        )
        sources["rainfall"] = _unavailable_source(
            "Historical rainfall", message
        ).model_dump(mode="json")
        warnings.append(message)
        rainfall_data = RainfallData()
    else:
        sources["rainfall"] = _source_model(rainfall_value.source).model_dump(mode="json")
        rainfall_data = RainfallData(
            annual_avg_mm=rainfall_value.annual_avg_mm,
            valid_years=rainfall_value.valid_years,
            monthly=[MonthlyRainfall(**item) for item in rainfall_value.monthly],
        )

    coefficient = settings.approved_runoff_coefficient
    coefficient_basis = settings.approved_runoff_coefficient_source
    if coefficient is None:
        sources["runoff_coefficient"] = _unavailable_source(
            "Approved runoff coefficient",
            "No field- or authority-approved runoff coefficient is configured",
        ).model_dump(mode="json")
        warnings.append(
            "Runoff volume and pond sizing are unavailable until an approved runoff coefficient is configured."
        )
    else:
        sources["runoff_coefficient"] = _source_model(SourceInfo(
            name="Configured runoff coefficient",
            status="reliable" if coefficient_basis else "degraded",
            model=coefficient_basis,
            message=f"Configured coefficient: {coefficient:g}",
        )).model_dump(mode="json")

    annual_rainfall = rainfall_data.annual_avg_mm
    volume = None
    peak_discharge = None
    pond = None
    if coefficient is not None and annual_rainfall is not None:
        volume = calculate_runoff(result["catchment"]["area_sqm"], annual_rainfall, coefficient)
        warnings.append(
            "Annual runoff is a screening water-yield estimate; evaporation, infiltration, sediment reserve, routing and environmental releases are not modelled."
        )
        if settings.design_rainfall_intensity_mm_h is not None:
            peak_discharge = calculate_peak_discharge(
                result["catchment"]["area_sqm"],
                settings.design_rainfall_intensity_mm_h,
                coefficient,
            )
        else:
            warnings.append(
                "Peak discharge is unavailable because no approved design rainfall intensity is configured."
            )
        try:
            geometry = recommend_pond_geometry(volume)
            pond = PondRecommendation(
                lat=result["pond_location"]["lat"],
                lng=result["pond_location"]["lng"],
                **geometry,
            )
            warnings.append(
                "Contour-workflow pond dimensions are preliminary runoff-storage geometry; cadastral land, soil, groundwater, spillway routing and a site survey are not yet available."
            )
        except AnalysisValidationError as exc:
            warnings.append(str(exc))

    result["rainfall_data"] = rainfall_data.model_dump(mode="json")
    result["runoff_stats"] = RunoffStats(
        catchment_area_sqm=result["catchment"]["area_sqm"],
        annual_rainfall_mm=annual_rainfall,
        runoff_coefficient=coefficient,
        runoff_coefficient_basis=coefficient_basis,
        estimated_volume_m3=round(volume, 2) if volume is not None else None,
        peak_discharge_m3_s=(
            round(peak_discharge, 5) if peak_discharge is not None else None
        ),
        peak_method=(
            "Rational Method with configured design rainfall intensity"
            if peak_discharge is not None else None
        ),
    ).model_dump(mode="json")
    result["pond"] = pond.model_dump(mode="json") if pond else None
    result["quality"]["warnings"] = list(dict.fromkeys(warnings))
    if pond is None or annual_rainfall is None or coefficient is None:
        result["analysis_status"] = "incomplete"
        result["quality"]["status"] = "incomplete"
    return ContourAnalysisResponse(**result)


@router.post("/analyze", response_model=AnalysisResponse, summary="Run a screening pond analysis")
async def analyze_location(payload: AnalysisRequest, http_request: Request) -> AnalysisResponse:
    await limiter.enforce(http_request, "analyze", settings.rate_analyze_per_minute)
    if payload.radius_km > settings.analysis_max_radius_km:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "radius_not_supported",
                "message": f"Maximum configured analysis radius is {settings.analysis_max_radius_km:g} km",
            },
        )

    elevation_task = asyncio.create_task(
        fetch_elevation_grid(payload.center.lat, payload.center.lng, payload.radius_km)
    )
    imagery_task = asyncio.create_task(
        download_satellite_mosaic(payload.center.lat, payload.center.lng, payload.radius_km)
    )
    rainfall_task = asyncio.create_task(
        get_rainfall_data(payload.center.lat, payload.center.lng)
    )
    try:
        elevation_result = await elevation_task
    except Exception as elevation_error:
        imagery_task.cancel()
        rainfall_task.cancel()
        await asyncio.gather(imagery_task, rainfall_task, return_exceptions=True)
        message = (
            elevation_error.message
            if isinstance(elevation_error, UpstreamDataError)
            else "Elevation processing failed"
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "elevation_unavailable", "message": message},
        ) from elevation_error
    imagery_result, rainfall_result = await asyncio.gather(
        imagery_task, rainfall_task, return_exceptions=True
    )

    warnings = [
        "Screening result only: cadastral ownership, hydrogeology, soils, groundwater, structures, utilities and field conditions are not verified."
    ]
    sources: dict[str, SourceMetadata] = {"elevation": _source_model(elevation_result.source)}
    if elevation_result.source.message:
        warnings.append(elevation_result.source.message)
    candidate_polygon_raw: list[dict] = []
    candidate_land_grid = None
    water_exclusion_grid = None
    land_result: LandCoverResult | None = None

    if isinstance(imagery_result, Exception):
        message = imagery_result.message if isinstance(imagery_result, UpstreamDataError) else "Satellite imagery processing failed"
        sources["imagery"] = _unavailable_source(settings.imagery_source_name, message)
        sources["land_cover"] = _unavailable_source("RGB/HSV land-cover screening", "No valid imagery was available")
        warnings.append(message)
    else:
        sources["imagery"] = _source_model(imagery_result.source)
        try:
            land_result = await asyncio.to_thread(analyze_satellite_image, imagery_result.image)
            if land_result.candidate_contour is not None:
                candidate_polygon_raw = contour_to_polygon(
                    land_result.candidate_contour, imagery_result.bounds, imagery_result.image.shape
                )
            if land_result.candidate_mask is not None:
                candidate_land_grid = raster_mask_to_terrain_grid(
                    land_result.candidate_mask, elevation_result.dem.shape
                )
            if land_result.water_mask is not None:
                water_exclusion_grid = raster_mask_to_terrain_grid(
                    land_result.water_mask, elevation_result.dem.shape
                )
                water_exclusion_grid = buffer_terrain_exclusion(
                    water_exclusion_grid,
                    settings.contour_detected_water_setback_m,
                    elevation_result.cell_size_m,
                )
            land_source = SourceInfo(
                name="RGB/HSV land-cover screening",
                status="degraded",
                resolution=imagery_result.source.resolution,
                coverage_ratio=imagery_result.source.coverage_ratio,
                message=land_result.message,
            )
            sources["land_cover"] = _source_model(land_source)
            warnings.append(land_result.message)
        except Exception as exc:
            sources["land_cover"] = _unavailable_source(
                "RGB/HSV land-cover screening", f"Land-cover analysis failed: {type(exc).__name__}"
            )
            warnings.append("Land-cover analysis failed; no land candidate or pond location was produced.")

    if isinstance(rainfall_result, Exception):
        message = rainfall_result.message if isinstance(rainfall_result, UpstreamDataError) else "Rainfall processing failed"
        sources["rainfall"] = _unavailable_source("Historical rainfall", message)
        warnings.append(message)
        rainfall_data = RainfallData()
    else:
        sources["rainfall"] = _source_model(rainfall_result.source)
        rainfall_data = RainfallData(
            annual_avg_mm=rainfall_result.annual_avg_mm,
            valid_years=rainfall_result.valid_years,
            monthly=[MonthlyRainfall(**item) for item in rainfall_result.monthly],
        )

    try:
        terrain = await asyncio.to_thread(
            run_terrain_analysis,
            elevation_result.dem,
            elevation_result.latitudes,
            elevation_result.longitudes,
            candidate_polygon_raw,
            candidate_land_mask=candidate_land_grid,
            candidate_exclusion_mask=water_exclusion_grid,
        )
    except AnalysisValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "terrain_quality_failed", "message": str(exc)},
        ) from exc
    warnings.extend(terrain["warnings"])
    terrain_status = "degraded" if terrain["warnings"] else "reliable"
    sources["hydrology"] = _source_model(SourceInfo(
        name="Priority-Flood, resolved-flat D8 catchment and multi-criteria site ranking",
        status=terrain_status,
        resolution=f"{elevation_result.cell_size_m:.1f} m analysis cells",
        message="; ".join(terrain["warnings"]) or None,
    ))

    coefficient = settings.approved_runoff_coefficient
    coefficient_basis = settings.approved_runoff_coefficient_source
    if coefficient is None:
        sources["runoff_coefficient"] = _unavailable_source(
            "Approved runoff coefficient",
            "No field- or authority-approved runoff coefficient is configured",
        )
        warnings.append(
            "Annual runoff and pond sizing are unavailable until an approved runoff coefficient and its basis are configured."
        )
    else:
        sources["runoff_coefficient"] = _source_model(SourceInfo(
            name="Configured runoff coefficient",
            status="reliable" if coefficient_basis else "degraded",
            model=coefficient_basis,
            message=f"Configured coefficient: {coefficient:g}",
        ))
    annual_rainfall = rainfall_data.annual_avg_mm
    volume = None
    peak_discharge = None
    if coefficient is not None and annual_rainfall is not None:
        volume = calculate_runoff(terrain["catchment_area_sqm"], annual_rainfall, coefficient)
        warnings.append(
            "Annual runoff is a screening water-yield estimate; evaporation, infiltration, sediment reserve, routing and environmental releases are not modelled."
        )
        if settings.design_rainfall_intensity_mm_h is not None:
            peak_discharge = calculate_peak_discharge(
                terrain["catchment_area_sqm"], settings.design_rainfall_intensity_mm_h, coefficient
            )
        else:
            warnings.append("Peak discharge is unavailable because no approved design rainfall intensity is configured.")

    pond = None
    if volume is not None and terrain["pond_location"] is not None:
        try:
            geometry = recommend_pond_geometry(volume, terrain["candidate_area_sqm"])
            pond = PondRecommendation(
                lat=terrain["pond_location"]["lat"],
                lng=terrain["pond_location"]["lng"],
                **geometry,
            )
            if geometry["constrained_by_available_area"]:
                warnings.append("Pond capacity was reduced to fit the detected bare-surface candidate area.")
        except AnalysisValidationError as exc:
            warnings.append(str(exc))
    elif terrain["pond_location"] is None:
        warnings.append("No pond location is reported because no detected bare-surface candidate overlaps the watershed.")
    else:
        warnings.append("No pond dimensions are reported because rainfall or runoff-coefficient evidence is unavailable.")

    statuses = [source.status for source in sources.values()]
    if pond is None or "unavailable" in statuses:
        analysis_status = "incomplete"
    elif "degraded" in statuses or warnings:
        analysis_status = "degraded"
    else:
        analysis_status = "complete"

    catchment_polygon = [Coordinates(**point) for point in terrain["catchment_polygon"]]
    candidate_polygon = [Coordinates(**point) for point in candidate_polygon_raw]
    contours = [
        ContourLine(
            elevation=item["elevation"],
            points=[Coordinates(**point) for point in item["points"]],
        )
        for item in terrain["contours"]
    ]
    elevation_stats = ElevationStats(**terrain["elevation_stats"])
    land_analysis = LandAnalysis(
        status=land_result.status if land_result else "unavailable",
        bare_surface_ratio=land_result.bare_surface_ratio if land_result else None,
        vegetation_ratio=land_result.vegetation_ratio if land_result else None,
        water_ratio=land_result.water_ratio if land_result else None,
        low_saturation_surface_ratio=land_result.low_saturation_surface_ratio if land_result else None,
        candidate_area_sqm=round(terrain["candidate_area_sqm"], 2) if candidate_polygon else None,
    )
    runoff_stats = RunoffStats(
        catchment_area_sqm=round(terrain["catchment_area_sqm"], 2),
        annual_rainfall_mm=annual_rainfall,
        runoff_coefficient=coefficient,
        runoff_coefficient_basis=coefficient_basis,
        estimated_volume_m3=round(volume, 2) if volume is not None else None,
        peak_discharge_m3_s=round(peak_discharge, 4) if peak_discharge is not None else None,
        peak_method="Rational Method using configured design intensity" if peak_discharge is not None else None,
    )

    persistence = PersistenceStatus(status="disabled", message="History storage is disabled")
    if settings.history_enabled:
        values = {
            "analysis_status": analysis_status,
            "village_name": payload.village_name,
            "center_lat": payload.center.lat,
            "center_lng": payload.center.lng,
            "min_elevation": elevation_stats.min_elevation,
            "max_elevation": elevation_stats.max_elevation,
            "mean_elevation": elevation_stats.mean_elevation,
            "relief": elevation_stats.relief,
            "catchment_area_sqm": runoff_stats.catchment_area_sqm,
            "annual_rainfall_mm": annual_rainfall,
            "runoff_coefficient": coefficient,
            "estimated_volume_m3": runoff_stats.estimated_volume_m3,
            "bare_surface_ratio": land_analysis.bare_surface_ratio,
            "pond_lat": pond.lat if pond else None,
            "pond_lng": pond.lng if pond else None,
            "depth_m": pond.water_depth_m if pond else None,
            "capacity_m3": pond.capacity_m3 if pond else None,
            "surface_area_sqm": pond.excavation_footprint_area_sqm if pond else None,
            "catchment_polygon": [point.model_dump() for point in catchment_polygon],
            "candidate_land_polygon": [point.model_dump() for point in candidate_polygon],
            "contours": [item.model_dump() for item in contours],
            "monthly_rainfall": [item.model_dump() for item in rainfall_data.monthly],
            "source_metadata": {
                key: value.model_dump(mode="json") for key, value in sources.items()
            },
            "warnings": warnings,
        }
        try:
            record_id = await asyncio.to_thread(save_analysis, values)
            persistence = PersistenceStatus(status="saved", record_id=record_id)
        except Exception as exc:
            logger.warning("analysis_persistence_failed error_type=%s", type(exc).__name__)
            persistence = PersistenceStatus(status="failed", message="Analysis completed but could not be saved")
            warnings.append("Analysis history could not be saved.")

    quality = AnalysisQuality(
        status=analysis_status,
        sources=sources,
        warnings=list(dict.fromkeys(warnings)),
    )
    candidate_options = [
        {
            "rank": option["rank"],
            "lat": option["lat"],
            "lng": option["lng"],
            "elevation_m": option["elevation"],
            "boundary_distance_m": option["boundary_distance_m"],
            "local_slope_percent": option["local_slope_percent"],
            "suitability_score": option["suitability_score"],
            "contributing_area_hectares": option["contributing_area_sqm"] / 10_000.0,
            "water_distance_m": option["water_distance_m"],
            "selected": option["selected"],
            "selection_reason": option["selection_reason"],
        }
        for option in terrain.get("candidate_options", [])
    ]
    return AnalysisResponse(
        analysis_status=analysis_status,
        quality=quality,
        pond=pond,
        candidate_options=candidate_options,
        runoff_stats=runoff_stats,
        candidate_land_polygon=candidate_polygon,
        catchment_polygon=catchment_polygon,
        contours=contours,
        elevation_stats=elevation_stats,
        rainfall_data=rainfall_data,
        land_analysis=land_analysis,
        persistence=persistence,
    )


@router.get("/search-village", response_model=List[VillageSearchResult], summary="Search for a place after explicit submission")
async def search_village_endpoint(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
) -> list[VillageSearchResult]:
    await limiter.enforce(request, "search", settings.rate_search_per_minute)
    try:
        results = await search_village(q)
    except UpstreamDataError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "geocoding_unavailable", "message": exc.message},
        ) from exc
    return [VillageSearchResult(**result) for result in results]


def _authorize_history(api_key: str | None) -> None:
    if not settings.history_enabled:
        raise HTTPException(status_code=404, detail={"code": "history_disabled", "message": "Analysis history is disabled"})
    if settings.history_api_key and not hmac.compare_digest(api_key or "", settings.history_api_key):
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "A valid history API key is required"})


@router.get("/history", response_model=List[HistoryItem], summary="Get protected analysis history")
async def get_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> list[HistoryItem]:
    await limiter.enforce(request, "history", settings.rate_history_per_minute)
    _authorize_history(x_api_key)
    try:
        records = await asyncio.to_thread(fetch_history, limit)
    except Exception as exc:
        logger.warning("history_query_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "history_unavailable", "message": "History storage is unavailable"}) from exc
    return [
        HistoryItem(
            id=record.id,
            created_at=record.created_at,
            center_lat=record.center_lat,
            center_lng=record.center_lng,
            village_name=record.village_name,
            analysis_status=record.analysis_status,
            catchment_area_sqm=record.catchment_area_sqm,
            annual_rainfall_mm=record.annual_rainfall_mm,
            estimated_volume_m3=record.estimated_volume_m3,
            pond_depth_m=record.depth_m,
            pond_capacity_m3=record.capacity_m3,
        )
        for record in records
    ]
