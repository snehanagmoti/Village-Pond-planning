"""
Terrain Analysis Service
------------------------
Implements real hydrological algorithms for watershed delineation and terrain analysis.

Key Algorithms:
    - D8 Flow Direction:   Each cell drains to the steepest downhill neighbour (8 directions)
    - Flow Accumulation:   Counts upstream cells draining through each point (topological sort)
    - Watershed Delineation: Traces all cells draining to a pour point (reverse BFS)
    - Contour Extraction:  Derives contour lines from the DEM using OpenCV threshold + findContours
    - Shoelace Formula:    Computes polygon area in square metres from lat/lng coordinates

All elevation data comes from the real DEM grid fetched by the elevation service.
"""

import numpy as np
import cv2
import math
from collections import deque
from typing import List, Tuple, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────
# D8 Flow Direction
# ────────────────────────────────────────────────────────
# Direction encoding:
#   7  0  1
#   6  X  2
#   5  4  3

DR = [-1, -1,  0,  1, 1, 1, 0, -1]  # row offsets for directions 0–7
DC = [ 0,  1,  1,  1, 0, -1, -1, -1]  # col offsets for directions 0–7
DIST = [1.0, math.sqrt(2), 1.0, math.sqrt(2),
        1.0, math.sqrt(2), 1.0, math.sqrt(2)]


def d8_flow_direction(dem: np.ndarray) -> np.ndarray:
    """
    Compute D8 flow direction for every interior cell.

    For each cell, finds the steepest descent among 8 neighbours.
    Edge cells are assigned direction -1 (boundary/pit).

    Parameters:
        dem: 2D elevation grid (rows × cols)

    Returns:
        2D int array of same shape.  Each cell contains 0–7 (direction index)
        or -1 if the cell is a pit / on the boundary.
    """
    rows, cols = dem.shape
    flow_dir = np.full((rows, cols), -1, dtype=np.int32)

    for i in range(1, rows - 1):
        for j in range(1, cols - 1):
            max_slope = 0.0
            best_dir = -1
            for d in range(8):
                ni, nj = i + DR[d], j + DC[d]
                slope = (dem[i, j] - dem[ni, nj]) / DIST[d]
                if slope > max_slope:
                    max_slope = slope
                    best_dir = d
            flow_dir[i, j] = best_dir

    return flow_dir


# ────────────────────────────────────────────────────────
# Flow Accumulation (Topological Sort)
# ────────────────────────────────────────────────────────

def flow_accumulation(flow_dir: np.ndarray) -> np.ndarray:
    """
    Compute flow accumulation: each cell's value = number of upstream cells
    that eventually drain through it (including itself).

    Uses a topological sort (Kahn's algorithm) on the D8 flow graph.

    Parameters:
        flow_dir: 2D flow direction grid from d8_flow_direction()

    Returns:
        2D int array of same shape with accumulation counts.
    """
    rows, cols = flow_dir.shape
    acc = np.ones((rows, cols), dtype=np.int32)

    # Build in-degree for each cell (how many cells flow INTO it)
    in_degree = np.zeros((rows, cols), dtype=np.int32)
    for i in range(rows):
        for j in range(cols):
            d = flow_dir[i, j]
            if d >= 0:
                ni, nj = i + DR[d], j + DC[d]
                if 0 <= ni < rows and 0 <= nj < cols:
                    in_degree[ni, nj] += 1

    # Seed the queue with cells that have no upstream contributors
    queue = deque()
    for i in range(rows):
        for j in range(cols):
            if in_degree[i, j] == 0:
                queue.append((i, j))

    # Process in topological order (headwaters first → outlets last)
    while queue:
        ci, cj = queue.popleft()
        d = flow_dir[ci, cj]
        if d >= 0:
            ni, nj = ci + DR[d], cj + DC[d]
            if 0 <= ni < rows and 0 <= nj < cols:
                acc[ni, nj] += acc[ci, cj]
                in_degree[ni, nj] -= 1
                if in_degree[ni, nj] == 0:
                    queue.append((ni, nj))

    return acc


# ────────────────────────────────────────────────────────
# Watershed Delineation (Reverse BFS)
# ────────────────────────────────────────────────────────

def delineate_catchment(flow_dir: np.ndarray, pour_row: int, pour_col: int) -> np.ndarray:
    """
    Delineate the watershed/catchment draining to a given pour point
    by performing a reverse BFS on the D8 flow graph.

    A cell (ni, nj) is upstream of (ci, cj) if (ni, nj) has flow direction
    pointing exactly towards (ci, cj).

    Parameters:
        flow_dir:  D8 flow direction grid
        pour_row:  Row index of the pour/outlet point
        pour_col:  Column index of the pour/outlet point

    Returns:
        Boolean mask (True = inside catchment).
    """
    rows, cols = flow_dir.shape
    mask = np.zeros((rows, cols), dtype=bool)
    mask[pour_row, pour_col] = True

    queue = deque([(pour_row, pour_col)])

    while queue:
        ci, cj = queue.popleft()
        # Check all 8 neighbours: does any of them flow INTO (ci, cj)?
        for d in range(8):
            ni, nj = ci + DR[d], cj + DC[d]
            if 0 <= ni < rows and 0 <= nj < cols and not mask[ni, nj]:
                # If neighbour (ni, nj) flows in the *opposite* direction of d,
                # it drains towards (ci, cj).
                opposite = (d + 4) % 8
                if flow_dir[ni, nj] == opposite:
                    mask[ni, nj] = True
                    queue.append((ni, nj))

    return mask


# ────────────────────────────────────────────────────────
# Find Pour Point (highest-accumulation or lowest-elevation)
# ────────────────────────────────────────────────────────

def find_pour_point(
    dem: np.ndarray,
    flow_acc: np.ndarray,
    valid_mask: Optional[np.ndarray] = None
) -> Tuple[int, int]:
    """
    Find the best pour point (outlet) for watershed delineation.

    Strategy: pick the cell with the highest flow accumulation.
    If valid_mask is provided, only consider cells within that mask.
    If there are ties, pick the one with the lowest elevation (natural drain).

    Returns:
        (row, col) of the pour point.
    """
    rows, cols = dem.shape
    
    acc = flow_acc.copy()
    if valid_mask is not None and np.any(valid_mask):
        # Mask out everything outside the valid polygon
        acc[~valid_mask] = -1
    else:
        # Default: consider only interior cells
        acc[0, :] = -1
        acc[-1, :] = -1
        acc[:, 0] = -1
        acc[:, -1] = -1
        
    best_idx = np.unravel_index(np.argmax(acc), acc.shape)
    return best_idx[0], best_idx[1]


def polygon_to_mask(polygon_raw: List[Dict[str, float]], lat_array: np.ndarray, lng_array: np.ndarray) -> np.ndarray:
    """Convert a geographic polygon to a boolean mask on the DEM grid."""
    rows, cols = len(lat_array), len(lng_array)
    mask = np.zeros((rows, cols), dtype=np.uint8)
    if not polygon_raw:
        return mask.astype(bool)
        
    lat_max, lat_min = lat_array[0], lat_array[-1]
    lng_min, lng_max = lng_array[0], lng_array[-1]
    
    pts = []
    for p in polygon_raw:
        x = (p["lng"] - lng_min) / (lng_max - lng_min) * (cols - 1)
        # lat_array is descending
        y = (lat_max - p["lat"]) / (lat_max - lat_min) * (rows - 1)
        pts.append([int(round(x)), int(round(y))])
        
    pts = np.array([pts], dtype=np.int32)
    cv2.fillPoly(mask, pts, 1)
    
    # If the polygon was very small and no pixels were filled, pick the centroid
    if np.sum(mask) == 0:
        cx = sum(p[0] for p in pts[0]) / len(pts[0])
        cy = sum(p[1] for p in pts[0]) / len(pts[0])
        r, c = int(round(cy)), int(round(cx))
        if 0 <= r < rows and 0 <= c < cols:
            mask[r, c] = 1
            
    return mask.astype(bool)



def find_lowest_point(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Tuple[float, float, float]:
    """
    Find the lowest elevation point, optionally constrained to a boolean mask.

    Returns:
        (lat, lng, elevation) of the lowest point.
    """
    if mask is not None:
        masked_dem = np.where(mask, dem, np.inf)
    else:
        masked_dem = dem

    min_idx = np.unravel_index(np.argmin(masked_dem), masked_dem.shape)
    row, col = min_idx
    return float(lat_array[row]), float(lng_array[col]), float(dem[row, col])


# ────────────────────────────────────────────────────────
# Catchment Boundary → Polygon (via OpenCV)
# ────────────────────────────────────────────────────────

def extract_catchment_boundary(
    mask: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
) -> List[Dict[str, float]]:
    """
    Convert a boolean catchment mask into a lat/lng polygon
    using OpenCV contour detection.

    The mask is upscaled for smoother boundaries before contour extraction.

    Returns:
        List of {"lat": ..., "lng": ...} dicts forming the polygon.
    """
    rows, cols = mask.shape
    mask_u8 = (mask.astype(np.uint8)) * 255

    # Upscale for smoother polygon edges
    scale = 4
    mask_up = cv2.resize(mask_u8, (cols * scale, rows * scale), interpolation=cv2.INTER_NEAREST)
    # Apply slight blur to smooth jagged edges
    mask_up = cv2.GaussianBlur(mask_up, (3, 3), 0)
    _, mask_up = cv2.threshold(mask_up, 127, 255, cv2.THRESH_BINARY)

    contours_cv, _ = cv2.findContours(mask_up, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours_cv:
        return []

    # Pick the largest contour
    largest = max(contours_cv, key=cv2.contourArea)

    # Simplify the contour to reduce point count
    epsilon = 0.01 * cv2.arcLength(largest, True)
    largest = cv2.approxPolyDP(largest, epsilon, True)

    up_rows, up_cols = mask_up.shape
    polygon = []
    for point in largest:
        px, py = point[0]  # OpenCV: x = column, y = row
        lat = lat_array[0] + (lat_array[-1] - lat_array[0]) * py / (up_rows - 1)
        lng = lng_array[0] + (lng_array[-1] - lng_array[0]) * px / (up_cols - 1)
        polygon.append({"lat": float(lat), "lng": float(lng)})

    return polygon


# ────────────────────────────────────────────────────────
# Contour Extraction (via OpenCV thresholding)
# ────────────────────────────────────────────────────────

def extract_contours(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    num_levels: int = 6,
) -> List[Dict]:
    """
    Extract contour lines from the DEM at evenly-spaced elevation levels.

    Process:
    1. Upscale the DEM using bilinear interpolation for smoother lines.
    2. For each elevation level, threshold the DEM and run cv2.findContours.
    3. Convert pixel coords back to geographic coordinates.

    Returns:
        List of {"elevation": float, "points": [{"lat":..., "lng":...}, ...]}
    """
    min_elev = float(np.nanmin(dem))
    max_elev = float(np.nanmax(dem))
    relief = max_elev - min_elev

    if relief < 1.0:
        logger.info("Terrain is nearly flat (relief=%.1fm), skipping contours", relief)
        return []

    # Upscale the DEM for smoother contour lines
    rows, cols = dem.shape
    scale = 8
    dem_up = cv2.resize(
        dem.astype(np.float32),
        (cols * scale, rows * scale),
        interpolation=cv2.INTER_LINEAR,
    )
    dem_up = cv2.GaussianBlur(dem_up, (5, 5), 0)
    up_rows, up_cols = dem_up.shape

    # Choose contour levels evenly spaced between min and max (exclude extremes)
    levels = np.linspace(min_elev, max_elev, num_levels + 2)[1:-1]

    contour_data = []
    for level in levels:
        binary = (dem_up >= level).astype(np.uint8) * 255
        contours_cv, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours_cv:
            if len(contour) < 5:
                continue

            # Simplify to reduce point count
            epsilon = 0.005 * cv2.arcLength(contour, True)
            contour = cv2.approxPolyDP(contour, epsilon, True)

            if len(contour) < 3:
                continue

            points = []
            for pt in contour:
                px, py = pt[0]
                lat = lat_array[0] + (lat_array[-1] - lat_array[0]) * py / (up_rows - 1)
                lng = lng_array[0] + (lng_array[-1] - lng_array[0]) * px / (up_cols - 1)
                points.append({"lat": float(lat), "lng": float(lng)})

            contour_data.append({
                "elevation": round(float(level), 1),
                "points": points,
            })

    logger.info("Extracted %d contour segments across %d levels", len(contour_data), len(levels))
    return contour_data


# ────────────────────────────────────────────────────────
# Polygon Area Calculation (Shoelace Formula)
# ────────────────────────────────────────────────────────

def polygon_area_sqm(coords: List[Dict[str, float]]) -> float:
    """
    Calculate the area of a geographic polygon in square metres.

    Uses the Shoelace formula after converting lat/lng to a local
    flat-Earth projection (accurate for small areas < 50 km).

    Parameters:
        coords: List of {"lat": ..., "lng": ...} forming a closed polygon.

    Returns:
        Area in square metres.
    """
    if len(coords) < 3:
        return 0.0

    # Compute centroid for local projection reference
    avg_lat = sum(c["lat"] for c in coords) / len(coords)
    avg_lng = sum(c["lng"] for c in coords) / len(coords)

    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(avg_lat))

    # Project to local Cartesian metres
    points_m = []
    for c in coords:
        x = (c["lng"] - avg_lng) * m_per_deg_lng
        y = (c["lat"] - avg_lat) * m_per_deg_lat
        points_m.append((x, y))

    # Shoelace formula
    n = len(points_m)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points_m[i][0] * points_m[j][1]
        area -= points_m[j][0] * points_m[i][1]

    return abs(area) / 2.0


# ────────────────────────────────────────────────────────
# Runoff Estimation (Rational Method)
# ────────────────────────────────────────────────────────

def calculate_runoff(
    catchment_area_sqm: float,
    annual_rainfall_mm: float,
    runoff_coefficient: float = 0.3,
) -> float:
    """
    Estimate annual runoff volume using the Rational Method.

    Formula:  V = C × A × P
        V = runoff volume in m³
        C = runoff coefficient (0–1, depends on land cover)
        A = catchment area in m²
        P = rainfall depth in metres

    Parameters:
        catchment_area_sqm:  Catchment area in square metres
        annual_rainfall_mm:  Average annual rainfall in millimetres
        runoff_coefficient:  Dimensionless (default 0.3 for mixed rural)

    Returns:
        Estimated annual runoff volume in cubic metres.
    """
    rainfall_m = annual_rainfall_mm / 1000.0
    volume_m3 = runoff_coefficient * catchment_area_sqm * rainfall_m
    return volume_m3


# ────────────────────────────────────────────────────────
# Pond Dimension Recommendation
# ────────────────────────────────────────────────────────

def recommend_pond_dimensions(volume_m3: float) -> Tuple[float, float, float]:
    """
    Recommend pond depth, capacity, and surface area based on available runoff.

    Assumptions:
        - Target capture efficiency: 80% of estimated annual runoff.
        - Depth selection based on volume (continuous interpolation):
            < 5,000 m³  → 2.0 m
            5,000–50,000 → linearly interpolated between 2.0 and 4.0 m
            > 50,000 m³  → 4.0 m
        - Surface area = capacity / depth.

    Returns:
        (depth_m, capacity_m3, surface_area_sqm)
    """
    capture_efficiency = 0.80
    capacity = volume_m3 * capture_efficiency

    # Continuous depth interpolation instead of 3 discrete tiers
    if capacity <= 5_000:
        depth = 2.0
    elif capacity >= 50_000:
        depth = 4.0
    else:
        # Linear interpolation between 2.0m and 4.0m
        depth = 2.0 + (capacity - 5_000) / (50_000 - 5_000) * 2.0

    surface_area = capacity / depth if depth > 0 else 0.0

    return round(depth, 2), round(capacity, 2), round(surface_area, 2)


# ────────────────────────────────────────────────────────
# Full Terrain Analysis Pipeline
# ────────────────────────────────────────────────────────

def run_terrain_analysis(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    gov_land_polygon: Optional[List[Dict[str, float]]] = None,
) -> Dict:
    """
    Run the complete terrain analysis pipeline on a DEM grid.

    Steps:
    1. Compute D8 flow directions
    2. Compute flow accumulation
    3. Find pour point (highest accumulation)
    4. Delineate catchment watershed
    5. Extract catchment boundary polygon
    6. Calculate catchment area (Shoelace)
    7. Extract contour lines
    8. Find lowest point (for pond placement)
    9. Compute elevation statistics

    Returns:
        dict with keys: catchment_polygon, contours, catchment_area_sqm,
                        pond_lat, pond_lng, elevation_stats
    """
    logger.info("Running D8 flow direction analysis...")
    flow_dir = d8_flow_direction(dem)

    logger.info("Computing flow accumulation...")
    flow_acc = flow_accumulation(flow_dir)

    logger.info("Finding pour point (constrained to available land)...")
    valid_mask = polygon_to_mask(gov_land_polygon, lat_array, lng_array) if gov_land_polygon else None
    pour_row, pour_col = find_pour_point(dem, flow_acc, valid_mask)
    logger.info("Pour point at row=%d, col=%d (elev=%.1f m)", pour_row, pour_col, dem[pour_row, pour_col])

    logger.info("Delineating catchment...")
    catchment_mask = delineate_catchment(flow_dir, pour_row, pour_col)
    catchment_cells = int(np.sum(catchment_mask))
    logger.info("Catchment contains %d cells", catchment_cells)

    # If catchment is too small (< 10% of grid), use a broader approach:
    # find the overall lowest point and expand the catchment
    total_cells = dem.shape[0] * dem.shape[1]
    if catchment_cells < total_cells * 0.10:
        logger.warning("Catchment too small (%d cells), using overall lowest point", catchment_cells)
        min_idx = np.unravel_index(np.argmin(dem), dem.shape)
        pour_row, pour_col = int(min_idx[0]), int(min_idx[1])
        catchment_mask = delineate_catchment(flow_dir, pour_row, pour_col)
        catchment_cells = int(np.sum(catchment_mask))

    # If still too small, expand the catchment to a reasonable area
    if catchment_cells < total_cells * 0.05:
        logger.warning("Still small, falling back to circular catchment")
        rows, cols = dem.shape
        center_r, center_c = rows // 2, cols // 2
        Y, X = np.ogrid[:rows, :cols]
        radius = min(rows, cols) * 0.35
        catchment_mask = ((Y - center_r)**2 + (X - center_c)**2) <= radius**2

    logger.info("Extracting catchment boundary polygon...")
    catchment_polygon = extract_catchment_boundary(catchment_mask, lat_array, lng_array)

    logger.info("Calculating catchment area (Shoelace formula)...")
    catchment_area_sqm = polygon_area_sqm(catchment_polygon) if len(catchment_polygon) >= 3 else 0.0

    logger.info("Extracting contour lines...")
    contours = extract_contours(dem, lat_array, lng_array, num_levels=6)

    logger.info("Finding lowest point for pond placement...")
    pond_lat, pond_lng, pond_elev = find_lowest_point(dem, lat_array, lng_array, catchment_mask)

    # Elevation statistics
    min_elev = float(np.nanmin(dem))
    max_elev = float(np.nanmax(dem))
    mean_elev = float(np.nanmean(dem))
    relief = max_elev - min_elev

    return {
        "catchment_polygon": catchment_polygon,
        "contours": contours,
        "catchment_area_sqm": catchment_area_sqm,
        "pond_lat": pond_lat,
        "pond_lng": pond_lng,
        "pond_elevation": pond_elev,
        "elevation_stats": {
            "min_elevation": round(min_elev, 1),
            "max_elevation": round(max_elev, 1),
            "mean_elevation": round(mean_elev, 1),
            "relief": round(relief, 1),
        },
    }
