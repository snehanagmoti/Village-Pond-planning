"""
Elevation Service
-----------------
Fetches real Digital Elevation Model (DEM) data from the Open-Meteo Elevation API.
The API provides ~90m resolution SRTM-based elevation data worldwide, for free.

Returns a 2D NumPy grid of elevations along with the latitude and longitude arrays
that define the spatial extent of the grid.
"""

import httpx
import numpy as np
import asyncio
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

# Open-Meteo Elevation API — free, no API key required
ELEVATION_API_URL = "https://api.open-meteo.com/v1/elevation"
BATCH_SIZE = 100  # Max points per API call to stay within URL length limits


async def fetch_elevation_grid(
    center_lat: float,
    center_lng: float,
    radius_km: float = 2.0,
    grid_size: int = 25
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fetch a grid of elevation values centered on the given coordinates.

    Uses the Open-Meteo Elevation API (SRTM-based, ~90m resolution).

    Parameters:
        center_lat: Latitude of the center point
        center_lng: Longitude of the center point
        radius_km:  Radius of the area to analyze (default 2km)
        grid_size:  Number of grid points per side (default 25 → 625 total points)

    Returns:
        Tuple of:
            - elevation_grid (np.ndarray): 2D array of shape (grid_size, grid_size) with elevation in meters
            - lat_array (np.ndarray): 1D array of latitude values (south to north)
            - lng_array (np.ndarray): 1D array of longitude values (west to east)
    """
    # Convert radius_km to degree offsets
    # 1 degree latitude ≈ 111.32 km everywhere
    # 1 degree longitude ≈ 111.32 km × cos(latitude)
    lat_offset = radius_km / 111.32
    lng_offset = radius_km / (111.32 * np.cos(np.radians(center_lat)))

    lat_array = np.linspace(center_lat - lat_offset, center_lat + lat_offset, grid_size)
    lng_array = np.linspace(center_lng - lng_offset, center_lng + lng_offset, grid_size)

    # Build the flat list of all grid points (row-major order)
    all_lats = []
    all_lngs = []
    for lat in lat_array:
        for lng in lng_array:
            all_lats.append(round(float(lat), 6))
            all_lngs.append(round(float(lng), 6))

    total_points = len(all_lats)
    elevations = []

    async with httpx.AsyncClient() as client:
        for start in range(0, total_points, BATCH_SIZE):
            batch_lats = all_lats[start : start + BATCH_SIZE]
            batch_lngs = all_lngs[start : start + BATCH_SIZE]

            lat_str = ",".join(str(v) for v in batch_lats)
            lng_str = ",".join(str(v) for v in batch_lngs)
            url = f"{ELEVATION_API_URL}?latitude={lat_str}&longitude={lng_str}"

            try:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    batch_elev = data.get("elevation", [])
                    # Replace any None values with NaN
                    batch_elev = [e if e is not None else float('nan') for e in batch_elev]
                    elevations.extend(batch_elev)
                    logger.info(
                        "Elevation batch %d–%d fetched (%d values)",
                        start, start + len(batch_lats), len(batch_elev),
                    )
                else:
                    logger.warning("Elevation API returned %d for batch %d", response.status_code, start)
                    elevations.extend([float('nan')] * len(batch_lats))
            except Exception as exc:
                logger.error("Elevation API error for batch %d: %s", start, exc)
                elevations.extend([float('nan')] * len(batch_lats))

            # Small delay between batches to be respectful to the free API
            await asyncio.sleep(0.1)

    # Reshape the flat list into a 2D grid
    elevation_grid = np.array(elevations, dtype=np.float64).reshape(grid_size, grid_size)

    # Handle NaN values by interpolating from neighbours
    if np.any(np.isnan(elevation_grid)):
        elevation_grid = _interpolate_nan(elevation_grid)

    logger.info(
        "Elevation grid ready: shape=%s, range=%.1f–%.1f m",
        elevation_grid.shape,
        float(np.nanmin(elevation_grid)),
        float(np.nanmax(elevation_grid)),
    )

    return elevation_grid, lat_array, lng_array


def _interpolate_nan(grid: np.ndarray) -> np.ndarray:
    """Fill NaN values by averaging valid neighbours (simple kernel interpolation)."""
    result = grid.copy()
    nan_mask = np.isnan(result)

    if nan_mask.all():
        # If everything is NaN, fall back to a flat surface at 100m
        return np.full_like(result, 100.0)

    mean_val = float(np.nanmean(result))

    rows, cols = result.shape
    for i in range(rows):
        for j in range(cols):
            if nan_mask[i, j]:
                neighbours = []
                for di in [-1, 0, 1]:
                    for dj in [-1, 0, 1]:
                        ni, nj = i + di, j + dj
                        if 0 <= ni < rows and 0 <= nj < cols and not nan_mask[ni, nj]:
                            neighbours.append(result[ni, nj])
                result[i, j] = np.mean(neighbours) if neighbours else mean_val

    return result
