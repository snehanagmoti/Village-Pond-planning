"""
Pydantic Schemas — API request/response models
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class Coordinates(BaseModel):
    """A geographic point with latitude and longitude."""
    lat: float = Field(..., description="Latitude in decimal degrees")
    lng: float = Field(..., description="Longitude in decimal degrees")

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v):
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return round(v, 6)

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v):
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return round(v, 6)


class AnalysisRequest(BaseModel):
    """Request body for the /api/analyze endpoint."""
    center: Coordinates = Field(..., description="Centre point of the analysis area")
    radius_km: float = Field(2.0, ge=0.5, le=10.0, description="Radius in km around the centre to analyze")
    village_name: Optional[str] = Field(None, description="Optional village name for record-keeping")


class ContourLine(BaseModel):
    """A single contour line with its elevation and geographic points."""
    elevation: float = Field(..., description="Elevation of this contour in metres above sea level")
    points: List[Coordinates] = Field(..., description="Ordered list of points forming the contour line")


class ElevationStats(BaseModel):
    """Summary statistics of the elevation data within the analysis area."""
    min_elevation: float = Field(..., description="Minimum elevation in metres")
    max_elevation: float = Field(..., description="Maximum elevation in metres")
    mean_elevation: float = Field(..., description="Mean elevation in metres")
    relief: float = Field(..., description="Total relief (max − min) in metres")


class MonthlyRainfall(BaseModel):
    """Rainfall data for a single month."""
    month: str = Field(..., description="Month name (e.g., 'January')")
    rainfall_mm: float = Field(..., description="Average rainfall for this month in mm")


class RainfallData(BaseModel):
    """Complete rainfall information including annual and monthly breakdown."""
    annual_avg_mm: float = Field(..., description="Average annual rainfall in mm")
    monthly: List[MonthlyRainfall] = Field(..., description="Monthly rainfall breakdown (12 entries)")


class LandAnalysis(BaseModel):
    """Results of OpenCV-based satellite image land-cover analysis."""
    barren_ratio: float = Field(..., description="Fraction of area classified as barren (0–1)")
    adjusted_runoff_coeff: float = Field(..., description="Runoff coefficient adjusted by land cover")


class RunoffStats(BaseModel):
    """Hydrological runoff estimation results."""
    catchment_area_sqm: float = Field(..., description="Catchment area in square metres")
    annual_rainfall_mm: float = Field(..., description="Average annual rainfall in mm")
    runoff_coefficient: float = Field(..., description="Runoff coefficient used for estimation")
    estimated_volume_m3: float = Field(..., description="Estimated annual runoff volume in cubic metres")


class PondRecommendation(BaseModel):
    """Recommended pond dimensions and location."""
    lat: float = Field(..., description="Recommended pond latitude")
    lng: float = Field(..., description="Recommended pond longitude")
    depth_m: float = Field(..., description="Recommended pond depth in metres")
    capacity_m3: float = Field(..., description="Pond storage capacity in cubic metres")
    surface_area_sqm: float = Field(..., description="Pond surface area in square metres")


class AnalysisResponse(BaseModel):
    """Full response from the analysis endpoint, containing all computed data."""
    pond: PondRecommendation
    runoff_stats: RunoffStats
    government_land_polygon: List[Coordinates]
    catchment_polygon: List[Coordinates]
    contours: List[ContourLine]
    elevation_stats: ElevationStats
    rainfall_data: RainfallData
    land_analysis: LandAnalysis


class VillageSearchResult(BaseModel):
    """A single result from the village geocoding search."""
    display_name: str = Field(..., description="Full display name from Nominatim")
    lat: float
    lng: float


class HistoryItem(BaseModel):
    """A past analysis record from the database."""
    id: int
    created_at: str
    center_lat: float
    center_lng: float
    village_name: Optional[str] = None
    catchment_area_sqm: Optional[float] = None
    annual_rainfall_mm: Optional[float] = None
    estimated_volume_m3: Optional[float] = None
    pond_depth_m: Optional[float] = None
    pond_capacity_m3: Optional[float] = None
