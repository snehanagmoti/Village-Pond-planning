"""Radius-matched satellite mosaic and conservative land-cover screening."""

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from config import get_settings
from services.cache import TTLCache
from services.http_client import get_with_retries
from services.quality import SourceInfo, UpstreamDataError

logger = logging.getLogger(__name__)
settings = get_settings()
_cache: TTLCache["SatelliteMosaic"] = TTLCache(maxsize=32, ttl_seconds=settings.cache_ttl_seconds)


@dataclass
class SatelliteMosaic:
    image: np.ndarray
    bounds: Tuple[float, float, float, float]
    zoom: int
    source: SourceInfo


@dataclass
class LandCoverResult:
    bare_surface_ratio: float
    vegetation_ratio: float
    water_ratio: float
    low_saturation_surface_ratio: float
    candidate_contour: Optional[np.ndarray]
    status: str
    message: str
    candidate_mask: Optional[np.ndarray] = None
    water_mask: Optional[np.ndarray] = None


def _lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 2**zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _lat_lng_to_fractional_tile(lat: float, lng: float, zoom: int) -> Tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 2**zoom
    x = (lng + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _study_bounds(lat: float, lng: float, radius_km: float) -> Tuple[float, float, float, float]:
    lat_offset = radius_km / 111.32
    lng_offset = radius_km / (111.32 * math.cos(math.radians(lat)))
    bounds = (lat - lat_offset, lat + lat_offset, lng - lng_offset, lng + lng_offset)
    if bounds[2] < -180 or bounds[3] > 180:
        raise UpstreamDataError(
            "satellite_imagery", "Study areas crossing the antimeridian are not supported"
        )
    return bounds


def _choose_zoom(radius_km: float) -> int:
    if radius_km <= 1.5:
        return 15
    if radius_km <= 3.0:
        return 14
    return 13


async def _download_tile(semaphore: asyncio.Semaphore, x: int, y: int, zoom: int):
    async with semaphore:
        response = await get_with_retries(
            settings.imagery_tile_url.format(z=zoom, y=y, x=x),
            headers={"Accept": "image/*"},
        )
    if response.status_code != 200 or not response.content:
        return x, y, None
    content_type = response.headers.get("content-type", "")
    if content_type and "image" not in content_type.lower():
        return x, y, None
    image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[0] < 128 or image.shape[1] < 128:
        return x, y, None
    return x, y, image


async def download_satellite_mosaic(lat: float, lng: float, radius_km: float) -> SatelliteMosaic:
    zoom = _choose_zoom(radius_km)
    cache_key = (round(lat, 5), round(lng, 5), round(radius_km, 2), zoom)
    cached = _cache.get(cache_key)
    if cached is not None:
        cached.source.message = "; ".join(
            filter(None, [cached.source.message, "served from in-process cache"])
        )
        return cached

    lat_min, lat_max, lng_min, lng_max = _study_bounds(lat, lng, radius_km)
    x_min, y_max = _lat_lng_to_tile(lat_min, lng_min, zoom)
    x_max, y_min = _lat_lng_to_tile(lat_max, lng_max, zoom)
    if x_max < x_min:
        x_min, x_max = x_max, x_min
    if y_max < y_min:
        y_min, y_max = y_max, y_min
    tile_count = (x_max - x_min + 1) * (y_max - y_min + 1)
    if tile_count > 64:
        raise UpstreamDataError("satellite_imagery", f"Study area requires too many imagery tiles ({tile_count})")

    semaphore = asyncio.Semaphore(6)
    downloads = await asyncio.gather(*[
        _download_tile(semaphore, x, y, zoom)
        for y in range(y_min, y_max + 1)
        for x in range(x_min, x_max + 1)
    ])
    tiles = {(x, y): image for x, y, image in downloads if image is not None}
    coverage = len(tiles) / tile_count
    if coverage < 1.0:
        raise UpstreamDataError("satellite_imagery", f"Imagery coverage is insufficient ({coverage * 100:.1f}%)")
    tile_height, tile_width = next(iter(tiles.values())).shape[:2]
    if any(image.shape != (tile_height, tile_width, 3) for image in tiles.values()):
        raise UpstreamDataError("satellite_imagery", "Imagery tiles have inconsistent dimensions")
    mosaic = np.zeros(
        ((y_max - y_min + 1) * tile_height, (x_max - x_min + 1) * tile_width, 3),
        dtype=np.uint8,
    )
    for (x, y), image in tiles.items():
        row = (y - y_min) * tile_height
        col = (x - x_min) * tile_width
        mosaic[row : row + tile_height, col : col + tile_width] = image

    west_x, north_y = _lat_lng_to_fractional_tile(lat_max, lng_min, zoom)
    east_x, south_y = _lat_lng_to_fractional_tile(lat_min, lng_max, zoom)
    left = max(0, int(math.floor((west_x - x_min) * tile_width)))
    right = min(mosaic.shape[1], int(math.ceil((east_x - x_min) * tile_width)))
    top = max(0, int(math.floor((north_y - y_min) * tile_height)))
    bottom = min(mosaic.shape[0], int(math.ceil((south_y - y_min) * tile_height)))
    if right - left < 32 or bottom - top < 32:
        raise UpstreamDataError("satellite_imagery", "Imagery crop is unexpectedly small")
    mosaic = mosaic[top:bottom, left:right].copy()
    mosaic_bounds = (lat_min, lat_max, lng_min, lng_max)
    pixel_resolution = 156543.03392 * math.cos(math.radians(lat)) / (2**zoom)
    source = SourceInfo(
        name=settings.imagery_source_name,
        status="reliable",
        resolution=f"approximately {pixel_resolution:.1f} m/pixel at zoom {zoom}",
        coverage_ratio=round(coverage, 4),
        message="Square study-area crop; RGB interpretation is separately marked degraded",
        license_url=settings.imagery_license_url,
    )
    result = SatelliteMosaic(mosaic, mosaic_bounds, zoom, source)
    _cache.set(cache_key, result)
    return result


def analyze_satellite_image(image: np.ndarray) -> LandCoverResult:
    """Classify broad RGB/HSV surface groups for screening, never ownership."""
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise UpstreamDataError("satellite_imagery", "Decoded imagery has an invalid shape")
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(grayscale))
    contrast = float(np.std(grayscale))
    if mean_brightness < 5 or mean_brightness > 250 or contrast < 4:
        raise UpstreamDataError("satellite_imagery", "Imagery appears blank or has insufficient contrast")

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    vegetation = cv2.inRange(hsv, np.array([32, 35, 25]), np.array([95, 255, 245]))
    water_blue = cv2.inRange(hsv, np.array([90, 25, 15]), np.array([140, 255, 210]))
    water_dark = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 55, 70]))
    water = cv2.bitwise_or(water_blue, water_dark)

    brown = cv2.inRange(hsv, np.array([5, 35, 45]), np.array([32, 255, 245]))
    sand = cv2.inRange(hsv, np.array([15, 18, 110]), np.array([38, 170, 255]))
    bare = cv2.bitwise_or(brown, sand)
    bare = cv2.bitwise_and(bare, cv2.bitwise_not(vegetation))
    # Maintain a conservative buffer around pixels classified as water. This
    # does not prove that all rivers are detected, but prevents known water
    # pixels from being reintroduced when the candidate polygon is simplified.
    water_buffer_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    buffered_water = cv2.dilate(water, water_buffer_kernel)
    bare = cv2.bitwise_and(bare, cv2.bitwise_not(buffered_water))

    low_saturation = cv2.inRange(hsv, np.array([0, 0, 75]), np.array([180, 45, 230]))
    low_saturation = cv2.bitwise_and(low_saturation, cv2.bitwise_not(water))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    bare = cv2.morphologyEx(bare, cv2.MORPH_CLOSE, kernel)
    bare = cv2.morphologyEx(bare, cv2.MORPH_OPEN, kernel)

    total = float(image.shape[0] * image.shape[1])
    def ratio(mask: np.ndarray) -> float:
        return cv2.countNonZero(mask) / total

    bare_ratio = ratio(bare)
    vegetation_ratio = ratio(vegetation)
    water_ratio = ratio(water)
    low_saturation_ratio = ratio(low_saturation)

    contours, _ = cv2.findContours(bare, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum_region_area = total * 0.0025
    candidates = [contour for contour in contours if cv2.contourArea(contour) >= minimum_region_area]
    largest = max(candidates, key=cv2.contourArea) if candidates else None
    candidate_mask = None
    if largest is not None:
        candidate_mask = np.zeros_like(bare)
        cv2.drawContours(candidate_mask, [largest], -1, 255, thickness=cv2.FILLED)
        candidate_mask = cv2.bitwise_and(candidate_mask, bare)

    return LandCoverResult(
        bare_surface_ratio=round(bare_ratio, 4),
        vegetation_ratio=round(vegetation_ratio, 4),
        water_ratio=round(water_ratio, 4),
        low_saturation_surface_ratio=round(low_saturation_ratio, 4),
        candidate_contour=largest,
        status="degraded",
        message=(
            "RGB/HSV screening applies a conservative pixel buffer around detected water, but cannot establish "
            "ownership, soil suitability, structures, crops, legal availability, or complete river detection"
        ),
        candidate_mask=candidate_mask,
        water_mask=water,
    )


def raster_mask_to_terrain_grid(mask: np.ndarray, grid_shape: Tuple[int, int]) -> np.ndarray:
    """Align a north-up imagery mask to the DEM's south-to-north row order."""
    if mask is None or mask.ndim != 2 or len(grid_shape) != 2 or min(grid_shape) < 3:
        raise ValueError("A two-dimensional imagery mask and valid terrain shape are required")
    rows, cols = grid_shape
    resized = cv2.resize(mask, (cols, rows), interpolation=cv2.INTER_NEAREST)
    return np.flipud(resized > 0).copy()


def contour_to_polygon(
    contour: np.ndarray,
    bounds: Tuple[float, float, float, float],
    image_shape: Tuple[int, ...],
) -> List[Dict[str, float]]:
    lat_min, lat_max, lng_min, lng_max = bounds
    height, width = image_shape[:2]
    epsilon = 0.01 * cv2.arcLength(contour, True)
    simplified = cv2.approxPolyDP(contour, epsilon, True)
    polygon = []
    for point in simplified:
        px, py = point[0]
        lat = lat_max - (lat_max - lat_min) * float(py) / max(1, height - 1)
        lng = lng_min + (lng_max - lng_min) * float(px) / max(1, width - 1)
        polygon.append({"lat": lat, "lng": lng})
    return polygon if len(polygon) >= 3 else []
