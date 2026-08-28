"""Hydrologic screening algorithms with explicit quality gates."""

import heapq
import logging
import math
from collections import deque
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from config import get_settings
from services.quality import AnalysisValidationError

logger = logging.getLogger(__name__)
settings = get_settings()
DR = [-1, -1, 0, 1, 1, 1, 0, -1]
DC = [0, 1, 1, 1, 0, -1, -1, -1]
DIST = [1.0, math.sqrt(2), 1.0, math.sqrt(2), 1.0, math.sqrt(2), 1.0, math.sqrt(2)]


def d8_flow_direction(dem: np.ndarray) -> np.ndarray:
    """Assign each interior cell to its steepest lower D8 neighbor."""
    rows, cols = dem.shape
    flow_dir = np.full((rows, cols), -1, dtype=np.int32)
    for row in range(1, rows - 1):
        for col in range(1, cols - 1):
            best_slope = 0.0
            best_direction = -1
            for direction in range(8):
                next_row = row + DR[direction]
                next_col = col + DC[direction]
                slope = (dem[row, col] - dem[next_row, next_col]) / DIST[direction]
                if slope > best_slope:
                    best_slope = slope
                    best_direction = direction
            flow_dir[row, col] = best_direction
    return flow_dir


def fill_depressions(dem: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Priority-flood depression filling; returns filled DEM and fill depth."""
    if dem.ndim != 2 or min(dem.shape) < 3 or not np.isfinite(dem).all():
        raise AnalysisValidationError("DEM must be a finite two-dimensional grid")
    rows, cols = dem.shape
    filled = dem.astype(np.float64).copy()
    visited = np.zeros_like(filled, dtype=bool)
    heap: list[tuple[float, int, int]] = []
    for row in range(rows):
        for col in (0, cols - 1):
            if not visited[row, col]:
                heapq.heappush(heap, (filled[row, col], row, col))
                visited[row, col] = True
    for col in range(cols):
        for row in (0, rows - 1):
            if not visited[row, col]:
                heapq.heappush(heap, (filled[row, col], row, col))
                visited[row, col] = True
    while heap:
        elevation, row, col = heapq.heappop(heap)
        for direction in range(8):
            next_row, next_col = row + DR[direction], col + DC[direction]
            if not (0 <= next_row < rows and 0 <= next_col < cols) or visited[next_row, next_col]:
                continue
            visited[next_row, next_col] = True
            if filled[next_row, next_col] < elevation:
                filled[next_row, next_col] = elevation
            heapq.heappush(heap, (filled[next_row, next_col], next_row, next_col))
    return filled, filled - dem


def resolve_flats(dem: np.ndarray) -> np.ndarray:
    """Add a sub-millimetre gradient across equal-elevation plateaus toward outlets."""
    rows, cols = dem.shape
    adjusted = dem.copy()
    visited = np.zeros((rows, cols), dtype=bool)
    epsilon = 1e-5
    for start_row in range(rows):
        for start_col in range(cols):
            if visited[start_row, start_col]:
                continue
            level = dem[start_row, start_col]
            plateau = []
            queue = deque([(start_row, start_col)])
            visited[start_row, start_col] = True
            outlets = []
            while queue:
                row, col = queue.popleft()
                plateau.append((row, col))
                is_boundary = row in (0, rows - 1) or col in (0, cols - 1)
                has_lower = False
                for direction in range(8):
                    next_row, next_col = row + DR[direction], col + DC[direction]
                    if not (0 <= next_row < rows and 0 <= next_col < cols):
                        continue
                    neighbor = dem[next_row, next_col]
                    if neighbor < level - 1e-9:
                        has_lower = True
                    elif abs(neighbor - level) <= 1e-9 and not visited[next_row, next_col]:
                        visited[next_row, next_col] = True
                        queue.append((next_row, next_col))
                if is_boundary or has_lower:
                    outlets.append((row, col))
            if len(plateau) <= 1 or not outlets:
                continue
            distances = {cell: 0 for cell in outlets}
            queue = deque(outlets)
            plateau_set = set(plateau)
            while queue:
                row, col = queue.popleft()
                for direction in range(8):
                    neighbor = (row + DR[direction], col + DC[direction])
                    if neighbor in plateau_set and neighbor not in distances:
                        distances[neighbor] = distances[(row, col)] + 1
                        queue.append(neighbor)
            for (row, col), distance in distances.items():
                adjusted[row, col] += distance * epsilon
    return adjusted


def flow_accumulation(flow_dir: np.ndarray) -> np.ndarray:
    rows, cols = flow_dir.shape
    accumulation = np.ones((rows, cols), dtype=np.int64)
    in_degree = np.zeros((rows, cols), dtype=np.int32)
    for row in range(rows):
        for col in range(cols):
            direction = flow_dir[row, col]
            if direction >= 0:
                in_degree[row + DR[direction], col + DC[direction]] += 1
    queue = deque(zip(*np.where(in_degree == 0), strict=False))
    while queue:
        row, col = queue.popleft()
        direction = flow_dir[row, col]
        if direction < 0:
            continue
        next_row, next_col = row + DR[direction], col + DC[direction]
        accumulation[next_row, next_col] += accumulation[row, col]
        in_degree[next_row, next_col] -= 1
        if in_degree[next_row, next_col] == 0:
            queue.append((next_row, next_col))
    return accumulation


def delineate_catchment(flow_dir: np.ndarray, pour_row: int, pour_col: int) -> np.ndarray:
    rows, cols = flow_dir.shape
    if not (0 <= pour_row < rows and 0 <= pour_col < cols):
        raise AnalysisValidationError("Pour point is outside the DEM")
    mask = np.zeros((rows, cols), dtype=bool)
    mask[pour_row, pour_col] = True
    queue = deque([(pour_row, pour_col)])
    while queue:
        row, col = queue.popleft()
        for direction in range(8):
            upstream_row, upstream_col = row + DR[direction], col + DC[direction]
            if not (0 <= upstream_row < rows and 0 <= upstream_col < cols):
                continue
            if mask[upstream_row, upstream_col]:
                continue
            if flow_dir[upstream_row, upstream_col] == (direction + 4) % 8:
                mask[upstream_row, upstream_col] = True
                queue.append((upstream_row, upstream_col))
    return mask


def find_pour_point(
    dem: np.ndarray,
    flow_acc: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> Tuple[int, int]:
    candidates = np.ones(dem.shape, dtype=bool) if valid_mask is None else valid_mask.astype(bool)
    if not np.any(candidates):
        raise AnalysisValidationError("No valid pour-point cells are available")
    maximum = int(np.max(flow_acc[candidates]))
    rows, cols = np.where(candidates & (flow_acc == maximum))
    elevations = dem[rows, cols]
    winner = int(np.argmin(elevations))
    return int(rows[winner]), int(cols[winner])


def polygon_to_mask(
    polygon_raw: List[Dict[str, float]],
    lat_array: np.ndarray,
    lng_array: np.ndarray,
) -> np.ndarray:
    rows, cols = len(lat_array), len(lng_array)
    mask = np.zeros((rows, cols), dtype=np.uint8)
    if len(polygon_raw) < 3:
        return mask.astype(bool)
    lat_min, lat_max = float(lat_array[0]), float(lat_array[-1])
    lng_min, lng_max = float(lng_array[0]), float(lng_array[-1])
    points = []
    for point in polygon_raw:
        x = (point["lng"] - lng_min) / (lng_max - lng_min) * (cols - 1)
        y = (point["lat"] - lat_min) / (lat_max - lat_min) * (rows - 1)
        points.append([int(round(x)), int(round(y))])
    cv2.fillPoly(mask, np.asarray([points], dtype=np.int32), 1)
    return mask.astype(bool)


def find_lowest_point(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Tuple[float, float, float]:
    valid = np.ones(dem.shape, dtype=bool) if mask is None else mask.astype(bool)
    if not np.any(valid):
        raise AnalysisValidationError("No valid cells are available for pond placement")
    masked = np.where(valid, dem, np.inf)
    row, col = np.unravel_index(np.argmin(masked), masked.shape)
    return float(lat_array[row]), float(lng_array[col]), float(dem[row, col])


def extract_catchment_boundary(mask: np.ndarray, lat_array: np.ndarray, lng_array: np.ndarray) -> List[Dict[str, float]]:
    source = mask.astype(np.uint8) * 255
    scale = 4
    upscaled = cv2.resize(source, (source.shape[1] * scale, source.shape[0] * scale), interpolation=cv2.INTER_NEAREST)
    contours, _ = cv2.findContours(upscaled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    largest = max(contours, key=cv2.contourArea)
    largest = cv2.approxPolyDP(largest, 0.005 * cv2.arcLength(largest, True), True)
    up_rows, up_cols = upscaled.shape
    return [
        {
            "lat": float(lat_array[0] + (lat_array[-1] - lat_array[0]) * point[0][1] / max(1, up_rows - 1)),
            "lng": float(lng_array[0] + (lng_array[-1] - lng_array[0]) * point[0][0] / max(1, up_cols - 1)),
        }
        for point in largest
    ]


def extract_contours(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    num_levels: int = 6,
) -> List[Dict]:
    minimum, maximum = float(np.min(dem)), float(np.max(dem))
    if maximum - minimum < 1.0:
        return []
    rows, cols = dem.shape
    scale = max(2, min(8, int(200 / max(rows, cols))))
    upscaled = cv2.resize(dem.astype(np.float32), (cols * scale, rows * scale), interpolation=cv2.INTER_LINEAR)
    upscaled = cv2.GaussianBlur(upscaled, (5, 5), 0)
    up_rows, up_cols = upscaled.shape
    output = []
    for level in np.linspace(minimum, maximum, num_levels + 2)[1:-1]:
        binary = (upscaled >= level).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if len(contour) < 5:
                continue
            simplified = cv2.approxPolyDP(contour, 0.004 * cv2.arcLength(contour, True), True)
            if len(simplified) < 3:
                continue
            points = [
                {
                    "lat": float(lat_array[0] + (lat_array[-1] - lat_array[0]) * point[0][1] / max(1, up_rows - 1)),
                    "lng": float(lng_array[0] + (lng_array[-1] - lng_array[0]) * point[0][0] / max(1, up_cols - 1)),
                }
                for point in simplified
            ]
            output.append({"elevation": round(float(level), 1), "points": points})
    return output


def _distance_from_mask_boundary(mask: np.ndarray, cell_size_m: float) -> np.ndarray:
    """Return distance inside a mask, with boundary cells defined as zero metres."""
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant", constant_values=0)
    pixel_distance = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
    return np.maximum(0.0, pixel_distance - 1.0) * cell_size_m


def trace_downstream_path(
    flow_direction: np.ndarray,
    start_row: int,
    start_col: int,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
) -> List[Dict[str, float]]:
    """Trace a bounded D8 path from a candidate cell to its terminal outlet."""
    rows, cols = flow_direction.shape
    row, col = start_row, start_col
    visited: set[tuple[int, int]] = set()
    path: List[Dict[str, float]] = []
    for _ in range(rows * cols):
        if (row, col) in visited:
            break
        visited.add((row, col))
        path.append({"lat": float(lat_array[row]), "lng": float(lng_array[col])})
        direction = int(flow_direction[row, col])
        if direction < 0:
            break
        next_row, next_col = row + DR[direction], col + DC[direction]
        if not (0 <= next_row < rows and 0 <= next_col < cols):
            break
        row, col = next_row, next_col
    return path


def polygon_area_sqm(coords: List[Dict[str, float]]) -> float:
    if len(coords) < 3:
        return 0.0
    average_lat = sum(point["lat"] for point in coords) / len(coords)
    average_lng = sum(point["lng"] for point in coords) / len(coords)
    meters_lng = 111_320.0 * math.cos(math.radians(average_lat))
    projected = [
        ((point["lng"] - average_lng) * meters_lng, (point["lat"] - average_lat) * 111_320.0)
        for point in coords
    ]
    return abs(sum(
        projected[index][0] * projected[(index + 1) % len(projected)][1]
        - projected[(index + 1) % len(projected)][0] * projected[index][1]
        for index in range(len(projected))
    )) / 2.0


def calculate_runoff(catchment_area_sqm: float, annual_rainfall_mm: float, runoff_coefficient: float = 0.3) -> float:
    if catchment_area_sqm < 0 or annual_rainfall_mm < 0 or not 0 <= runoff_coefficient <= 1:
        raise ValueError("Runoff inputs must be non-negative and coefficient must be between 0 and 1")
    return runoff_coefficient * catchment_area_sqm * annual_rainfall_mm / 1000.0


def calculate_peak_discharge(catchment_area_sqm: float, rainfall_intensity_mm_h: float, runoff_coefficient: float) -> float:
    """Rational Method peak flow Q=C×i×A/3.6 for A in km² and i in mm/h."""
    area_km2 = catchment_area_sqm / 1_000_000.0
    return runoff_coefficient * rainfall_intensity_mm_h * area_km2 / 3.6


def _frustum_geometry(bottom_width: float, depth: float, ratio: float, slope: float) -> dict:
    bottom_length = ratio * bottom_width
    top_width = bottom_width + 2 * slope * depth
    top_length = bottom_length + 2 * slope * depth
    bottom_area = bottom_width * bottom_length
    top_area = top_width * top_length
    volume = depth / 3.0 * (bottom_area + top_area + math.sqrt(bottom_area * top_area))
    return {
        "volume": volume,
        "bottom_width": bottom_width,
        "bottom_length": bottom_length,
        "top_width": top_width,
        "top_length": top_length,
        "bottom_area": bottom_area,
        "top_area": top_area,
    }


def recommend_pond_geometry(volume_m3: float, available_surface_area_sqm: Optional[float] = None) -> dict:
    if volume_m3 <= 0:
        raise AnalysisValidationError("Positive runoff volume is required for pond sizing")
    target_capacity = volume_m3 * settings.capture_efficiency
    interpolation = min(1.0, max(0.0, (target_capacity - 5_000.0) / 45_000.0))
    depth = settings.pond_min_water_depth_m + interpolation * (
        settings.pond_max_water_depth_m - settings.pond_min_water_depth_m
    )
    ratio = settings.pond_length_width_ratio
    slope = settings.pond_side_slope_h_to_v
    excavation_depth = depth + settings.pond_freeboard_m
    constrained = False

    if available_surface_area_sqm is not None:
        minimum_footprint_area = (2 * slope * excavation_depth) ** 2
        if available_surface_area_sqm <= minimum_footprint_area:
            raise AnalysisValidationError("Detected candidate land is too small for configured depth and side slopes")
        low, high = 0.0, math.sqrt(available_surface_area_sqm / ratio)
        for _ in range(60):
            mid = (low + high) / 2
            if _frustum_geometry(mid, excavation_depth, ratio, slope)["top_area"] <= available_surface_area_sqm:
                low = mid
            else:
                high = mid
        maximum_water = _frustum_geometry(low, depth, ratio, slope)
        if maximum_water["volume"] < target_capacity:
            target_capacity = maximum_water["volume"]
            constrained = True

    low, high = 0.0, max(10.0, math.sqrt(target_capacity / max(depth, 0.1)))
    while _frustum_geometry(high, depth, ratio, slope)["volume"] < target_capacity:
        high *= 2
    for _ in range(60):
        mid = (low + high) / 2
        if _frustum_geometry(mid, depth, ratio, slope)["volume"] < target_capacity:
            low = mid
        else:
            high = mid
    water_geometry = _frustum_geometry(high, depth, ratio, slope)
    excavation_geometry = _frustum_geometry(high, excavation_depth, ratio, slope)
    if (
        available_surface_area_sqm is not None
        and excavation_geometry["top_area"] > available_surface_area_sqm + 0.01
    ):
        raise AnalysisValidationError("Computed excavation footprint exceeds detected candidate land")
    return {
        "water_depth_m": round(depth, 2),
        "excavation_depth_m": round(excavation_depth, 2),
        "freeboard_m": round(settings.pond_freeboard_m, 2),
        "capacity_m3": round(water_geometry["volume"], 2),
        "water_surface_area_sqm": round(water_geometry["top_area"], 2),
        "excavation_footprint_area_sqm": round(excavation_geometry["top_area"], 2),
        "excavation_volume_m3": round(excavation_geometry["volume"], 2),
        "water_length_m": round(water_geometry["top_length"], 2),
        "water_width_m": round(water_geometry["top_width"], 2),
        "bottom_area_sqm": round(water_geometry["bottom_area"], 2),
        "crest_length_m": round(excavation_geometry["top_length"], 2),
        "crest_width_m": round(excavation_geometry["top_width"], 2),
        "bottom_length_m": round(water_geometry["bottom_length"], 2),
        "bottom_width_m": round(water_geometry["bottom_width"], 2),
        "side_slope_h_to_v": round(slope, 2),
        "capture_efficiency": round(settings.capture_efficiency, 3),
        "constrained_by_available_area": constrained,
    }


def recommend_pond_dimensions(volume_m3: float) -> Tuple[float, float, float]:
    """Compatibility wrapper returning water depth, capacity and top area."""
    result = recommend_pond_geometry(volume_m3)
    return result["water_depth_m"], result["capacity_m3"], result["water_surface_area_sqm"]


def run_terrain_analysis(
    dem: np.ndarray,
    lat_array: np.ndarray,
    lng_array: np.ndarray,
    candidate_land_polygon: Optional[List[Dict[str, float]]] = None,
    analysis_mask: Optional[np.ndarray] = None,
    candidate_land_mask: Optional[np.ndarray] = None,
    candidate_exclusion_mask: Optional[np.ndarray] = None,
    candidate_boundary_setback_m: float = 75.0,
) -> Dict:
    if dem.ndim != 2 or dem.shape != (len(lat_array), len(lng_array)):
        raise AnalysisValidationError("DEM shape must match the latitude and longitude axes")
    if len(lat_array) < 3 or len(lng_array) < 3:
        raise AnalysisValidationError("Terrain analysis requires at least a 3 by 3 grid")
    valid_mask = (
        np.ones(dem.shape, dtype=bool)
        if analysis_mask is None
        else np.asarray(analysis_mask, dtype=bool)
    )
    if valid_mask.shape != dem.shape or int(np.sum(valid_mask)) < 3:
        raise AnalysisValidationError("Analysis mask must match the DEM and contain valid cells")
    filled, fill_depth = fill_depressions(dem)
    flow_surface = resolve_flats(filled)
    flow_direction = d8_flow_direction(flow_surface)
    if analysis_mask is not None:
        # Cells on the supplied study boundary are possible outlets. Outside
        # cells must never contribute to a watershed inside that boundary.
        eroded = cv2.erode(valid_mask.astype(np.uint8), np.ones((3, 3), np.uint8))
        study_boundary = valid_mask & ~eroded.astype(bool)
        flow_direction[~valid_mask | study_boundary] = -1
    accumulation = flow_accumulation(flow_direction)

    outlet_mask = (flow_direction < 0) & valid_mask
    pour_row, pour_col = find_pour_point(dem, accumulation, outlet_mask)
    catchment_mask = delineate_catchment(flow_direction, pour_row, pour_col) & valid_mask
    catchment_cells = int(np.sum(catchment_mask))
    if catchment_cells < 3:
        raise AnalysisValidationError("Computed watershed contains fewer than three cells")
    catchment_ratio = catchment_cells / int(np.sum(valid_mask))
    if catchment_ratio < 0.02:
        raise AnalysisValidationError("Computed watershed is too small for a defensible recommendation")

    lat_cell_m = abs(float(lat_array[1] - lat_array[0])) * 111_320.0
    lng_cell_m = abs(float(lng_array[1] - lng_array[0])) * 111_320.0 * math.cos(math.radians(float(np.mean(lat_array))))
    cell_area_sqm = lat_cell_m * lng_cell_m
    catchment_area_sqm = catchment_cells * cell_area_sqm
    catchment_polygon = extract_catchment_boundary(catchment_mask, lat_array, lng_array)
    if len(catchment_polygon) < 3:
        raise AnalysisValidationError("Computed watershed boundary is invalid")

    if candidate_land_mask is None:
        land_mask = polygon_to_mask(candidate_land_polygon or [], lat_array, lng_array)
    else:
        land_mask = np.asarray(candidate_land_mask, dtype=bool)
        if land_mask.shape != dem.shape:
            raise AnalysisValidationError("Candidate land mask must match the DEM")
    exclusions = np.zeros(dem.shape, dtype=bool)
    if candidate_exclusion_mask is not None:
        exclusions = np.asarray(candidate_exclusion_mask, dtype=bool)
        if exclusions.shape != dem.shape:
            raise AnalysisValidationError("Candidate exclusion mask must match the DEM")

    raw_candidate_mask = catchment_mask & land_mask & ~exclusions
    boundary_distance_m = _distance_from_mask_boundary(valid_mask, math.sqrt(cell_area_sqm))
    candidate_mask = (
        raw_candidate_mask
        & (flow_direction >= 0)
        & (boundary_distance_m >= max(0.0, candidate_boundary_setback_m))
    )
    candidate_cells = int(np.sum(candidate_mask))
    pond_location = None
    drainage_path: List[Dict[str, float]] = []
    if candidate_cells > 0:
        # Prefer drainage concentration only after removing outlets, excluded
        # surfaces and the configured analysis-edge setback.
        candidate_accumulation = np.where(candidate_mask, accumulation, -1)
        maximum = np.max(candidate_accumulation)
        rows, cols = np.where(candidate_mask & (accumulation == maximum))
        winner = int(np.argmin(dem[rows, cols]))
        row, col = int(rows[winner]), int(cols[winner])
        pond_location = {
            "lat": float(lat_array[row]),
            "lng": float(lng_array[col]),
            "elevation": float(dem[row, col]),
            "boundary_distance_m": float(boundary_distance_m[row, col]),
        }
        drainage_path = trace_downstream_path(flow_direction, row, col, lat_array, lng_array)

    warnings = []
    filled_ratio = float(np.mean(fill_depth[valid_mask] > 1e-6))
    maximum_fill = float(np.max(fill_depth[valid_mask]))
    if filled_ratio > 0.10 or maximum_fill > 5.0:
        warnings.append(
            f"DEM depression filling modified {filled_ratio * 100:.1f}% of cells (maximum {maximum_fill:.1f} m); field validation is required."
        )
    if int(np.sum(raw_candidate_mask)) > 0 and candidate_cells == 0:
        warnings.append(
            "Candidate land overlaps the watershed, but no cell remains after water/exclusion masks and the analysis-boundary setback."
        )
    elif candidate_cells == 0:
        warnings.append("No eligible candidate land overlaps the computed watershed; no pond location was produced.")

    return {
        "catchment_polygon": catchment_polygon,
        "contours": extract_contours(dem, lat_array, lng_array),
        "catchment_area_sqm": catchment_area_sqm,
        "catchment_cells": catchment_cells,
        "catchment_ratio": catchment_ratio,
        "candidate_area_sqm": candidate_cells * cell_area_sqm,
        "pond_location": pond_location,
        "outlet_location": {
            "lat": float(lat_array[pour_row]),
            "lng": float(lng_array[pour_col]),
            "elevation": float(dem[pour_row, pour_col]),
            "contributing_cells": int(accumulation[pour_row, pour_col]),
        },
        "drainage_path": drainage_path,
        "candidate_boundary_setback_m": max(0.0, float(candidate_boundary_setback_m)),
        "warnings": warnings,
        "elevation_stats": {
            "min_elevation": round(float(np.min(dem)), 1),
            "max_elevation": round(float(np.max(dem)), 1),
            "mean_elevation": round(float(np.mean(dem)), 1),
            "relief": round(float(np.max(dem) - np.min(dem)), 1),
            "grid_size": int(dem.shape[0]),
            "cell_size_m": round(math.sqrt(cell_area_sqm), 1),
        },
    }
