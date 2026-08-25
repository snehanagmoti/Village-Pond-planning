"""Validated, radius-aware elevation-grid acquisition."""

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import numpy as np

from config import get_settings
from services.cache import TTLCache
from services.http_client import get_with_retries
from services.quality import SourceInfo, UpstreamDataError

logger = logging.getLogger(__name__)
BATCH_SIZE = 100
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
        raise UpstreamDataError(
            "elevation", f"{failed_batches} elevation batch request(s) failed; the DEM was not fabricated"
        )

    dem = np.asarray(values, dtype=np.float64).reshape(grid_size, grid_size)
    dem[(dem < -500.0) | (dem > 9_000.0)] = np.nan
    missing_ratio = float(np.isnan(dem).mean())
    if missing_ratio >= 1.0:
        raise UpstreamDataError("elevation", "No valid elevation values were returned")
    if missing_ratio > 0.02:
        raise UpstreamDataError(
            "elevation",
            f"Elevation coverage is insufficient ({(1 - missing_ratio) * 100:.1f}% valid)",
        )
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
            "configure a reserved or self-hosted elevation endpoint for native-resolution coverage"
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
