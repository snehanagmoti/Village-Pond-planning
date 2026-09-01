"""Pydantic request and response contracts for screening analyses."""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Coordinates(APIModel):
    lat: float = Field(..., ge=-85.0, le=85.0)
    lng: float = Field(..., ge=-180.0, le=180.0)

    @field_validator("lat", "lng")
    @classmethod
    def round_coordinate(cls, value: float) -> float:
        return round(value, 6)


class AnalysisRequest(APIModel):
    center: Coordinates
    radius_km: float = Field(2.0, ge=0.5, le=10.0)
    village_name: Optional[str] = Field(None, max_length=200)

    @field_validator("village_name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class SourceMetadata(APIModel):
    name: str
    status: Literal["reliable", "degraded", "unavailable"]
    retrieved_at: datetime
    resolution: Optional[str] = None
    period: Optional[str] = None
    model: Optional[str] = None
    coverage_ratio: Optional[float] = None
    message: Optional[str] = None
    license_url: Optional[str] = None


class AnalysisQuality(APIModel):
    status: Literal["complete", "degraded", "incomplete"]
    screening_only: bool = True
    sources: Dict[str, SourceMetadata]
    warnings: List[str] = Field(default_factory=list)


class ContourLine(APIModel):
    elevation: float
    points: List[Coordinates]


class ElevationStats(APIModel):
    min_elevation: float
    max_elevation: float
    mean_elevation: float
    relief: float
    grid_size: int
    cell_size_m: float


class MonthlyRainfall(APIModel):
    month: str
    rainfall_mm: float
    valid_years: int


class RainfallData(APIModel):
    annual_avg_mm: Optional[float] = None
    valid_years: int = 0
    monthly: List[MonthlyRainfall] = Field(default_factory=list)


class LandAnalysis(APIModel):
    status: Literal["reliable", "degraded", "unavailable"]
    bare_surface_ratio: Optional[float] = None
    vegetation_ratio: Optional[float] = None
    water_ratio: Optional[float] = None
    low_saturation_surface_ratio: Optional[float] = None
    candidate_area_sqm: Optional[float] = None
    method: str = "RGB/HSV screening heuristic"


class RunoffStats(APIModel):
    catchment_area_sqm: float
    annual_rainfall_mm: Optional[float] = None
    runoff_coefficient: Optional[float] = None
    runoff_coefficient_basis: Optional[str] = None
    estimated_volume_m3: Optional[float] = None
    peak_discharge_m3_s: Optional[float] = None
    volume_method: str = "Runoff-coefficient annual volume estimate"
    peak_method: Optional[str] = None


class PondRecommendation(APIModel):
    lat: float
    lng: float
    water_depth_m: float
    excavation_depth_m: float
    freeboard_m: float
    capacity_m3: float
    water_surface_area_sqm: float
    excavation_footprint_area_sqm: float
    excavation_volume_m3: float
    water_length_m: float
    water_width_m: float
    bottom_area_sqm: float
    crest_length_m: float
    crest_width_m: float
    bottom_length_m: float
    bottom_width_m: float
    side_slope_h_to_v: float
    capture_efficiency: float
    constrained_by_available_area: bool


class PondCandidateOption(Coordinates):
    rank: int = Field(..., ge=1, le=5)
    elevation_m: float
    boundary_distance_m: float = Field(..., ge=0)
    local_slope_percent: float = Field(..., ge=0)
    suitability_score: float = Field(..., ge=0, le=100)
    contributing_area_hectares: float = Field(..., gt=0)
    water_distance_m: Optional[float] = Field(None, ge=0)
    selected: bool
    selection_reason: str


class PersistenceStatus(APIModel):
    status: Literal["saved", "disabled", "failed"]
    record_id: Optional[int] = None
    message: Optional[str] = None


class AnalysisResponse(APIModel):
    analysis_status: Literal["complete", "degraded", "incomplete"]
    quality: AnalysisQuality
    pond: Optional[PondRecommendation] = None
    candidate_options: List[PondCandidateOption] = Field(default_factory=list, max_length=5)
    runoff_stats: RunoffStats
    candidate_land_polygon: List[Coordinates] = Field(default_factory=list)
    catchment_polygon: List[Coordinates] = Field(default_factory=list)
    contours: List[ContourLine] = Field(default_factory=list)
    elevation_stats: ElevationStats
    rainfall_data: RainfallData
    land_analysis: LandAnalysis
    persistence: PersistenceStatus


class ContourSummary(APIModel):
    contour_count: int = Field(..., ge=3)
    source_point_count: int = Field(..., ge=6)
    elevation_level_count: int = Field(..., ge=3)
    minimum_elevation_m: float
    maximum_elevation_m: float
    median_contour_interval_m: Optional[float] = Field(None, gt=0)


class ContourGrid(APIModel):
    rows: int = Field(..., ge=3)
    columns: int = Field(..., ge=3)
    cell_size_m: float = Field(..., gt=0)
    observed_cell_ratio: float = Field(..., gt=0, le=1)
    interpolation_iterations: int = Field(..., ge=1)
    interpolation_converged: bool
    method: str


class DemVisualization(APIModel):
    image_data_url: str = Field(..., min_length=32)
    south_west: Coordinates
    north_east: Coordinates
    minimum_elevation_m: float
    maximum_elevation_m: float
    method: str


class ContourPondLocation(Coordinates):
    elevation_m: float
    boundary_distance_m: float = Field(..., ge=0)
    local_slope_percent: float = Field(..., ge=0)
    suitability_score: float = Field(..., ge=0, le=100)
    contributing_area_sqm: float = Field(..., gt=0)
    water_distance_m: Optional[float] = Field(None, ge=0)
    selection_method: str


class ContourOutletLocation(Coordinates):
    elevation_m: float
    contributing_cells: int = Field(..., ge=1)


class ContourCatchment(APIModel):
    area_sqm: float = Field(..., gt=0)
    area_hectares: float = Field(..., gt=0)
    cell_count: int = Field(..., ge=3)
    study_grid_fraction: float = Field(..., gt=0, le=1)
    boundary: List[Coordinates] = Field(..., min_length=3)


class ContourCandidateOption(Coordinates):
    rank: int = Field(..., ge=1, le=5)
    elevation_m: float
    boundary_distance_m: float = Field(..., ge=0)
    local_slope_percent: float = Field(..., ge=0)
    suitability_score: float = Field(..., ge=0, le=100)
    contributing_area_hectares: float = Field(..., gt=0)
    water_distance_m: Optional[float] = Field(None, ge=0)
    selected: bool
    selection_reason: str


class ContourSelection(APIModel):
    mode: Literal["automatic", "point", "region"]
    requested_point: Optional[Coordinates] = None
    requested_region: List[Coordinates] = Field(default_factory=list)
    snapped_distance_m: Optional[float] = Field(None, ge=0)


class WaterScreening(APIModel):
    status: Literal["applied", "unavailable"]
    method: str
    detected_water_ratio: Optional[float] = Field(None, ge=0, le=1)
    exclusion_buffer_m: float = Field(..., ge=0)
    message: str


class ContourAnalysisResponse(APIModel):
    analysis_status: Literal["complete", "degraded", "incomplete"]
    input_file: str = Field(..., min_length=1, max_length=255)
    input_format: Literal["kml", "kmz"]
    contour_summary: ContourSummary
    grid: ContourGrid
    dem_visualization: DemVisualization
    pond_location: ContourPondLocation
    candidate_options: List[ContourCandidateOption] = Field(..., min_length=1, max_length=5)
    selection: ContourSelection
    outlet_location: ContourOutletLocation
    catchment: ContourCatchment
    rainfall_data: RainfallData
    runoff_stats: RunoffStats
    pond: Optional[PondRecommendation] = None
    eligible_candidate_area_sqm: float = Field(..., gt=0)
    water_screening: WaterScreening
    contours: List[ContourLine] = Field(default_factory=list)
    drainage_path: List[Coordinates] = Field(default_factory=list)
    study_area_boundary: List[Coordinates] = Field(..., min_length=3)
    study_boundary_source: Literal["uploaded_polygon", "derived_extent"]
    candidate_boundary_setback_m: float = Field(..., ge=0)
    quality: AnalysisQuality


class VillageSearchResult(APIModel):
    display_name: str = Field(..., min_length=1, max_length=500)
    lat: float = Field(..., ge=-85.0, le=85.0)
    lng: float = Field(..., ge=-180.0, le=180.0)


class HistoryItem(APIModel):
    id: int
    created_at: datetime
    center_lat: float
    center_lng: float
    village_name: Optional[str] = None
    analysis_status: Optional[str] = None
    catchment_area_sqm: Optional[float] = None
    annual_rainfall_mm: Optional[float] = None
    estimated_volume_m3: Optional[float] = None
    pond_depth_m: Optional[float] = None
    pond_capacity_m3: Optional[float] = None


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    checks: Dict[str, str] = Field(default_factory=dict)
