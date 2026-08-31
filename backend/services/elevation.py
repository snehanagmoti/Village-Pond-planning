"""Validated, radius-aware elevation-grid acquisition."""

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import cv2
import numpy as np

from config import get_settings
from services.cache import TTLCache
from services.http_client import get_with_retries
from services.quality import SourceInfo, UpstreamDataError

logger = logging.getLogger(__name__)
BATCH_SIZE = 100
TILE_SIZE = 256
settings = get_settings()
_cache: TTLCache["ElevationGrid"] = TTLCache(maxsize=64, ttl_seconds=settings.cache_ttl_seconds)
_batch_start_lock = asyncio.Lock()
_last_batch_started_at: float | None = None


@dataclass
class ElevationGrid:
    dem: np.ndarray
    latitudes: np.ndarray
    longitudes: np.ndarray
    source: SourceInfo
    missing_ratio: float
    cell_size_m: float


async def _wait_for_batch_slot() -> None:
    """Pace point batches so the public elevation service is not burst-throttled."""
    global _last_batch_started_at
    interval = settings.elevation_min_interval_seconds
    if interval <= 0:
        return
    async with _batch_start_lock:
        now = time.monotonic()
        if _last_batch_started_at is not None:
            delay = interval - (now - _last_batch_started_at)
            if delay > 0:
                await asyncio.sleep(delay)
        _last_batch_started_at = time.monotonic()


def _native_grid_target(radius_km: float) -> int:
    diameter_m = radius_km * 2000.0
    target = int(math.ceil(diameter_m / 90.0)) + 1
    if target % 2 == 0:
        target += 1
    return target


def _uses_rate_limited_public_endpoint() -> bool:
    hostname = (urlparse(settings.elevation_api_url).hostname or "").casefold()
    return hostname == "api.open-meteo.com" and settings.open_meteo_api_key is None


def choose_grid_size(radius_km: float) -> int:
    """Target native spacing, with a quota-safe cap for Open-Meteo's public endpoint."""
    max_size = settings.elevation_grid_max
    if _uses_rate_limited_public_endpoint():
        max_size = min(max_size, settings.elevation_public_grid_max)
    min_size = min(settings.elevation_grid_min, max_size)
    target = max(min_size, min(max_size, _native_grid_target(radius_km)))
    if target % 2 == 0:
        target = target + 1 if target < max_size else target - 1
    return target


async def _fetch_batch(
    semaphore: asyncio.Semaphore,
    latitudes: list[float],
    longitudes: list[float],
) -> list[float]:
    async with semaphore:
        await _wait_for_batch_slot()
        response = await get_with_retries(
            settings.elevation_api_url,
            params={
                "latitude": ",".join(str(value) for value in latitudes),
                "longitude": ",".join(str(value) for value in longitudes),
                **({"apikey": settings.open_meteo_api_key} if settings.open_meteo_api_key else {}),
            },
        )
    if response.status_code != 200:
        raise UpstreamDataError("elevation", f"Elevation source returned HTTP {response.status_code}")
    data = response.json()
    values = data.get("elevation")
    if not isinstance(values, list) or len(values) != len(latitudes):
        raise UpstreamDataError("elevation", "Elevation source returned an incomplete batch")
    return [float(value) if value is not None else float("nan") for value in values]


def _slippy_pixel(latitude: float, longitude: float, zoom: int) -> tuple[int, int, int, int]:
    """Map WGS84 coordinates to a 256-pixel Web Mercator tile and pixel."""
    latitude = max(-85.05112878, min(85.05112878, latitude))
    world_pixels = TILE_SIZE * (1 << zoom)
    global_x = ((longitude + 180.0) / 360.0) * world_pixels
    latitude_rad = math.radians(latitude)
    global_y = (
        1.0
        - math.asinh(math.tan(latitude_rad)) / math.pi
    ) / 2.0 * world_pixels
    maximum = math.nextafter(float(world_pixels), 0.0)
    global_x = max(0.0, min(maximum, global_x))
    global_y = max(0.0, min(maximum, global_y))
    tile_x = int(global_x // TILE_SIZE)
    tile_y = int(global_y // TILE_SIZE)
    pixel_x = min(TILE_SIZE - 1, int(global_x - tile_x * TILE_SIZE))
    pixel_y = min(TILE_SIZE - 1, int(global_y - tile_y * TILE_SIZE))
    return tile_x, tile_y, pixel_x, pixel_y


async def _fetch_terrarium_tile(zoom: int, tile_x: int, tile_y: int) -> np.ndarray:
    try:
        url = settings.elevation_tile_url.format(z=zoom, x=tile_x, y=tile_y)
    except (KeyError, ValueError) as exc:
        raise UpstreamDataError("elevation", "Terrain tile URL template is invalid") from exc
    response = await get_with_retries(url, headers={"Accept": "image/png"})
    if response.status_code != 200:
        raise UpstreamDataError(
            "elevation", f"Terrain tile source returned HTTP {response.status_code}"
        )
    content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
    if content_type and content_type != "image/png":
        raise UpstreamDataError("elevation", "Terrain tile source returned a non-PNG response")
    content = response.content
    if not content or len(content) > settings.elevation_tile_max_bytes:
        raise UpstreamDataError("elevation", "Terrain tile response size is invalid")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.shape[:2] != (TILE_SIZE, TILE_SIZE) or image.ndim != 3:
        raise UpstreamDataError("elevation", "Terrain tile PNG dimensions are invalid")
    if image.shape[2] not in (3, 4):
        raise UpstreamDataError("elevation", "Terrain tile PNG channels are invalid")
    red = image[:, :, 2].astype(np.float64)
    green = image[:, :, 1].astype(np.float64)
    blue = image[:, :, 0].astype(np.float64)
    return red * 256.0 + green + blue / 256.0 - 32768.0


async def _fetch_terrarium_grid(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    primary_failure: str,
) -> ElevationGrid:
    """Load a bounded DEM fallback from public Terrarium-encoded terrain tiles."""
    zoom = settings.elevation_tile_zoom
    samples: list[tuple[int, int, int, int]] = []
    required_tiles: set[tuple[int, int]] = set()
    for latitude in latitudes:
        for longitude in longitudes:
            tile_x, tile_y, pixel_x, pixel_y = _slippy_pixel(
                float(latitude), float(longitude), zoom
            )
            required_tiles.add((tile_x, tile_y))
            samples.append((tile_x, tile_y, pixel_x, pixel_y))
    if len(required_tiles) > settings.elevation_tile_max_count:
        raise UpstreamDataError(
            "elevation",
            f"Terrain fallback requires {len(required_tiles)} tiles, above the configured limit",
        )

    tile_keys = sorted(required_tiles)
    tile_results = await asyncio.gather(
        *(_fetch_terrarium_tile(zoom, tile_x, tile_y) for tile_x, tile_y in tile_keys),
        return_exceptions=True,
    )
    if any(isinstance(result, Exception) for result in tile_results):
        raise UpstreamDataError(
            "elevation", "One or more required terrain fallback tiles were unavailable"
        )
    tiles = dict(zip(tile_keys, tile_results, strict=True))
    values = [
        float(tiles[(tile_x, tile_y)][pixel_y, pixel_x])
        for tile_x, tile_y, pixel_x, pixel_y in samples
    ]
    dem = np.asarray(values, dtype=np.float64).reshape(len(latitudes), len(longitudes))
    dem[(dem < -500.0) | (dem > 9_000.0)] = np.nan
    missing_ratio = float(np.isnan(dem).mean())
    if missing_ratio > 0.02:
        raise UpstreamDataError(
            "elevation",
            f"Terrain fallback coverage is insufficient ({(1 - missing_ratio) * 100:.1f}% valid)",
        )
    if missing_ratio > 0:
        dem = _interpolate_nan(dem)

    cos_lat = math.cos(math.radians(float(np.mean(latitudes))))
    lat_spacing_m = abs(float(latitudes[1] - latitudes[0])) * 111_320.0
    lng_spacing_m = abs(float(longitudes[1] - longitudes[0])) * 111_320.0 * cos_lat
    cell_size_m = (lat_spacing_m + lng_spacing_m) / 2.0
    tile_resolution_m = 156_543.03392 * cos_lat / (1 << zoom)
    source = SourceInfo(
        name="AWS Open Data Terrain Tiles / Tilezen Terrarium",
        status="degraded",
        resolution=(
            f"approximately {tile_resolution_m:.1f} m terrain pixels at zoom {zoom}; "
            f"analysis grid {cell_size_m:.1f} m"
        ),
        coverage_ratio=round(1.0 - missing_ratio, 4),
        message=(
            f"{primary_failure}; used the bounded Terrain Tiles fallback. "
            "The source mosaic varies by location and is not a field survey"
        ),
        license_url="https://registry.opendata.aws/terrain-tiles/",
    )
    return ElevationGrid(dem, latitudes, longitudes, source, missing_ratio, cell_size_m)


async def _fallback_or_raise(
    reason: str,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> ElevationGrid:
    if not settings.elevation_fallback_enabled:
        raise UpstreamDataError("elevation", reason)
    try:
        return await _fetch_terrarium_grid(latitudes, longitudes, reason)
    except UpstreamDataError as exc:
        logger.warning("elevation_fallback_failed error_type=%s", type(exc).__name__)
        raise UpstreamDataError(
            "elevation", f"{reason}; terrain fallback was also unavailable"
        ) from exc


async def fetch_elevation_grid(
    center_lat: float,
    center_lng: float,
    radius_km: float = 2.0,
    grid_size: int | None = None,
) -> ElevationGrid:
    automatic_grid = grid_size is None
    grid_size = grid_size or choose_grid_size(radius_km)
    public_quota_limited = (
        automatic_grid
        and _uses_rate_limited_public_endpoint()
        and grid_size < _native_grid_target(radius_km)
    )
    if grid_size < 9 or grid_size > settings.elevation_grid_max or grid_size % 2 == 0:
        raise ValueError("Elevation grid size must be odd and within configured bounds")
    cache_key = (round(center_lat, 5), round(center_lng, 5), round(radius_km, 2), grid_size)
    cached = _cache.get(cache_key)
    if cached is not None:
        cached.source.message = "; ".join(
            filter(None, [cached.source.message, "served from in-process cache"])
        )
        return cached

    cos_lat = math.cos(math.radians(center_lat))
    if abs(cos_lat) < 0.05:
        raise UpstreamDataError("elevation", "Latitude is outside the supported Web Mercator range")
    lat_offset = radius_km / 111.32
    lng_offset = radius_km / (111.32 * cos_lat)
    latitudes = np.linspace(center_lat - lat_offset, center_lat + lat_offset, grid_size)
    longitudes = np.linspace(center_lng - lng_offset, center_lng + lng_offset, grid_size)

    flat_lats = [round(float(lat), 6) for lat in latitudes for _ in longitudes]
    flat_lngs = [round(float(lng), 6) for _ in latitudes for lng in longitudes]
    semaphore = asyncio.Semaphore(settings.elevation_concurrency)
    tasks = [
        _fetch_batch(
            semaphore,
            flat_lats[start : start + BATCH_SIZE],
            flat_lngs[start : start + BATCH_SIZE],
        )
        for start in range(0, len(flat_lats), BATCH_SIZE)
    ]
    batches = await asyncio.gather(*tasks, return_exceptions=True)
    values: list[float] = []
    failed_batches = 0
    for task, start in zip(batches, range(0, len(flat_lats), BATCH_SIZE), strict=False):
        expected = min(BATCH_SIZE, len(flat_lats) - start)
        if isinstance(task, Exception):
            logger.warning("elevation_batch_failed error_type=%s", type(task).__name__)
            values.extend([float("nan")] * expected)
            failed_batches += 1
        else:
            values.extend(task)

    if failed_batches:
        result = await _fallback_or_raise(
            f"{failed_batches} primary elevation batch request(s) failed",
            latitudes,
            longitudes,
        )
        _cache.set(cache_key, result)
        return result

    dem = np.asarray(values, dtype=np.float64).reshape(grid_size, grid_size)
    dem[(dem < -500.0) | (dem > 9_000.0)] = np.nan
    missing_ratio = float(np.isnan(dem).mean())
    if missing_ratio >= 1.0:
        result = await _fallback_or_raise(
            "No valid primary elevation values were returned", latitudes, longitudes
        )
        _cache.set(cache_key, result)
        return result
    if missing_ratio > 0.02:
        result = await _fallback_or_raise(
            f"Primary elevation coverage is insufficient ({(1 - missing_ratio) * 100:.1f}% valid)",
            latitudes,
            longitudes,
        )
        _cache.set(cache_key, result)
        return result
    if missing_ratio > 0:
        dem = _interpolate_nan(dem)

    lat_spacing_m = abs(float(latitudes[1] - latitudes[0])) * 111_320.0
    lng_spacing_m = (
        abs(float(longitudes[1] - longitudes[0])) * 111_320.0 * cos_lat
    )
    cell_size_m = (lat_spacing_m + lng_spacing_m) / 2.0
    status = "degraded" if missing_ratio > 0 or public_quota_limited else "reliable"
    messages: list[str] = []
    if missing_ratio > 0:
        messages.append(f"Interpolated {missing_ratio * 100:.1f}% missing grid cells")
    if public_quota_limited:
        messages.append(
            f"Public API quota limited the analysis grid to {grid_size}×{grid_size}; "
            "the model used a coarser grid while preserving the full study extent"
        )
    source = SourceInfo(
        name="Open-Meteo Elevation API / Copernicus DEM GLO-90 (2021)",
        status=status,
        resolution="90 m source DEM; analysis grid %.1f m" % cell_size_m,
        coverage_ratio=round(1.0 - missing_ratio, 4),
        message="; ".join(messages) or None,
        license_url="https://open-meteo.com/en/docs/elevation-api",
    )
    result = ElevationGrid(dem, latitudes, longitudes, source, missing_ratio, cell_size_m)
    _cache.set(cache_key, result)
    return result


def _interpolate_nan(grid: np.ndarray) -> np.ndarray:
    """Fill a small proportion of gaps from valid local neighbors, then the valid median."""
    result = grid.copy()
    for _ in range(4):
        missing = np.argwhere(np.isnan(result))
        if len(missing) == 0:
            break
        changed = False
        for row, col in missing:
            window = result[
                max(0, row - 1) : min(result.shape[0], row + 2),
                max(0, col - 1) : min(result.shape[1], col + 2),
            ]
            valid = window[np.isfinite(window)]
            if valid.size >= 2:
                result[row, col] = float(np.mean(valid))
                changed = True
        if not changed:
            break
    if np.isnan(result).any():
        result[np.isnan(result)] = float(np.nanmedian(result))
    return result
