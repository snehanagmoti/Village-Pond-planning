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
# Preserve valid tiles across partial upstream failures without caching a partial mosaic.
_tile_cache: TTLCache[np.ndarray] = TTLCache(maxsize=128, ttl_seconds=settings.cache_ttl_seconds)


@dataclass
class SatelliteMosaic:
    image: np.ndarray
    bounds: Tuple[float, float, float, float]
    zoom: int
    source: SourceInfo


@dataclass
class MappedHydrography:
    mask: np.ndarray
    bounds: Tuple[float, float, float, float]
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


async def _download_tile(
    semaphore: asyncio.Semaphore,
    x: int,
    y: int,
    zoom: int,
    *,
    tile_url: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
):
    template = tile_url or settings.imagery_tile_url
    cache_key = (template, zoom, x, y)
    cached = _tile_cache.get(cache_key)
    if cached is not None:
        return x, y, cached
    async with semaphore:
        response = await get_with_retries(
            template.format(z=zoom, y=y, x=x),
            headers=headers or {"Accept": "image/*"},
        )
    if response.status_code != 200 or not response.content:
        return x, y, None
    content_type = response.headers.get("content-type", "")
    if content_type and "image" not in content_type.lower():
        return x, y, None
    image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[0] < 128 or image.shape[1] < 128:
        return x, y, None
    _tile_cache.set(cache_key, image)
    return x, y, image


def _assemble_tile_crop(
    tiles: dict[tuple[int, int], np.ndarray],
    *,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    lat_min: float,
    lat_max: float,
    lng_min: float,
    lng_max: float,
    zoom: int,
    source_key: str,
) -> np.ndarray:
    tile_height, tile_width = next(iter(tiles.values())).shape[:2]
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
        raise UpstreamDataError(source_key, "Map crop is unexpectedly small")
    return mosaic[top:bottom, left:right].copy()


def extract_mapped_water_mask(map_image: np.ndarray) -> np.ndarray:
    """Extract the standard-map cyan hydrography without treating it as land data."""
    if map_image is None or map_image.ndim != 3 or map_image.shape[2] != 3:
        raise UpstreamDataError("mapped_hydrography", "Decoded map has an invalid shape")
    blue, green, red = cv2.split(map_image)
    mapped_water = (
        (blue >= 190)
        & (green >= 180)
        & (red <= 205)
        & (blue.astype(np.int16) >= red.astype(np.int16) + 22)
        & (green.astype(np.int16) >= red.astype(np.int16) + 12)
    ).astype(np.uint8) * 255
    return cv2.morphologyEx(
        mapped_water,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )


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
    ], return_exceptions=True)
    tiles = {
        (item[0], item[1]): item[2] for item in downloads
        if not isinstance(item, BaseException) and item[2] is not None
    }
    coverage = len(tiles) / tile_count
    if coverage < 1.0:
        raise UpstreamDataError("satellite_imagery", f"Imagery coverage is insufficient ({coverage * 100:.1f}%)")
    tile_height, tile_width = next(iter(tiles.values())).shape[:2]
    if any(image.shape != (tile_height, tile_width, 3) for image in tiles.values()):
        raise UpstreamDataError("satellite_imagery", "Imagery tiles have inconsistent dimensions")
    mosaic = _assemble_tile_crop(
        tiles,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
        zoom=zoom,
        source_key="satellite_imagery",
    )
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


async def download_mapped_hydrography(
    lat: float, lng: float, radius_km: float
) -> MappedHydrography:
    """Return mapped rivers and water bodies as a conservative exclusion mask."""
    zoom = _choose_zoom(radius_km)
    lat_min, lat_max, lng_min, lng_max = _study_bounds(lat, lng, radius_km)
    x_min, y_max = _lat_lng_to_tile(lat_min, lng_min, zoom)
    x_max, y_min = _lat_lng_to_tile(lat_max, lng_max, zoom)
    if x_max < x_min:
        x_min, x_max = x_max, x_min
    if y_max < y_min:
        y_min, y_max = y_max, y_min
    tile_count = (x_max - x_min + 1) * (y_max - y_min + 1)
    if tile_count > 64:
        raise UpstreamDataError(
            "mapped_hydrography", f"Study area requires too many map tiles ({tile_count})"
        )

    semaphore = asyncio.Semaphore(4)
    downloads = await asyncio.gather(
        *[
            _download_tile(
                semaphore,
                x,
                y,
                zoom,
                tile_url=settings.mapped_hydrography_tile_url,
                headers={
                    "Accept": "image/png,image/*",
                    "User-Agent": "VillagePondPlanningCourseProject/2.0",
                },
            )
            for y in range(y_min, y_max + 1)
            for x in range(x_min, x_max + 1)
        ],
        return_exceptions=True,
    )
    tiles = {
        (item[0], item[1]): item[2]
        for item in downloads
        if not isinstance(item, BaseException) and item[2] is not None
    }
    coverage = len(tiles) / tile_count
    if coverage < 1.0:
        raise UpstreamDataError(
            "mapped_hydrography",
            f"Mapped hydrography coverage is insufficient ({coverage * 100:.1f}%)",
        )
    tile_height, tile_width = next(iter(tiles.values())).shape[:2]
    if any(image.shape != (tile_height, tile_width, 3) for image in tiles.values()):
        raise UpstreamDataError("mapped_hydrography", "Map tiles have inconsistent dimensions")
    mosaic = _assemble_tile_crop(
        tiles,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
        zoom=zoom,
        source_key="mapped_hydrography",
    )

    # OSM water is light cyan (#aad3df). Tolerances include antialiased edges
    # and mapped waterways while rejecting grey roads and beige land.
    mapped_water = extract_mapped_water_mask(mosaic)
    return MappedHydrography(
        mask=mapped_water,
        bounds=(lat_min, lat_max, lng_min, lng_max),
        source=SourceInfo(
            name="OpenStreetMap mapped hydrography",
            status="reliable",
            resolution=f"mapped water at zoom {zoom}",
            coverage_ratio=round(coverage, 4),
            message="Mapped rivers and water bodies used as a hard exclusion layer",
            license_url="https://www.openstreetmap.org/copyright",
        ),
    )


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
    water_blue = cv2.inRange(hsv, np.array([88, 20, 12]), np.array([145, 255, 220]))
    water_dark = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 48]))

    # Rivers in agricultural imagery are frequently dark teal, muddy or partly
    # shaded rather than strongly blue.  Add conservative channel-oriented
    # tests in BGR space instead of relying on hue alone.  False positives are
    # preferable here: this mask is a hard *exclusion*, never evidence that a
    # site is suitable.
    blue, green, red = cv2.split(image)
    cool_channel = (
        (blue.astype(np.int16) >= red.astype(np.int16) + 8)
        & (green.astype(np.int16) >= red.astype(np.int16) + 4)
        & (blue >= 30)
        & (grayscale <= 155)
    )
    cool_channel = cool_channel.astype(np.uint8) * 255
    water = cv2.bitwise_or(water_blue, water_dark)
    water = cv2.bitwise_or(water, cool_channel)
    water = cv2.morphologyEx(
        water,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )

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
            "Color-based surface screening excludes detected water with a conservative buffer; "
            "confirm seasonal rivers and land conditions during the site visit"
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


def geospatial_mask_to_terrain_grid(
    mask: np.ndarray,
    bounds: Tuple[float, float, float, float],
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    """Sample a north-up geospatial raster onto south-to-north terrain axes."""
    if mask is None or mask.ndim != 2 or len(latitudes) < 3 or len(longitudes) < 3:
        raise ValueError("A two-dimensional mask and valid terrain axes are required")
    lat_min, lat_max, lng_min, lng_max = bounds
    if lat_max <= lat_min or lng_max <= lng_min:
        raise ValueError("Imagery bounds are invalid")
    rows, cols = mask.shape
    sampled = np.zeros((len(latitudes), len(longitudes)), dtype=bool)
    x_indices = np.rint(
        (np.asarray(longitudes) - lng_min) / (lng_max - lng_min) * (cols - 1)
    ).astype(int)
    y_indices = np.rint(
        (lat_max - np.asarray(latitudes)) / (lat_max - lat_min) * (rows - 1)
    ).astype(int)
    valid_x = (x_indices >= 0) & (x_indices < cols)
    valid_y = (y_indices >= 0) & (y_indices < rows)
    for terrain_row, (source_row, row_valid) in enumerate(zip(y_indices, valid_y, strict=False)):
        if row_valid:
            sampled[terrain_row, valid_x] = mask[source_row, x_indices[valid_x]] > 0
    return sampled


def buffer_terrain_exclusion(
    mask: np.ndarray,
    buffer_m: float,
    cell_size_m: float,
) -> np.ndarray:
    """Dilate a boolean terrain-grid exclusion by a configurable metric buffer."""
    source = np.asarray(mask, dtype=bool)
    if source.ndim != 2 or cell_size_m <= 0 or buffer_m < 0:
        raise ValueError("A two-dimensional mask and non-negative metric sizes are required")
    buffer_cells = int(math.ceil(buffer_m / cell_size_m))
    if buffer_cells == 0 or not np.any(source):
        return source.copy()
    kernel_size = buffer_cells * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    return cv2.dilate(source.astype(np.uint8), kernel).astype(bool)


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
