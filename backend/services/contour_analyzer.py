"""Parse uploaded contour KML/KMZ files and derive a screening DEM.

The input contours are observations, not a raster DEM.  This module preserves
the observed contour cells and uses harmonic interpolation between them before
passing the surface to the shared hydrology implementation.
"""

from __future__ import annotations

import math
import re
import statistics
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

import cv2
import numpy as np

from config import get_settings
from services.quality import AnalysisValidationError
from services.terrain import run_terrain_analysis

settings = get_settings()
_ELEVATION_KEYS = ("elev", "height", "altitude", "contour", "level", "z")
_NUMBER = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?:m|metres?|meters?)?\s*$")


class ContourFileError(ValueError):
    """A safe, user-correctable contour upload error."""


@dataclass(frozen=True)
class ContourLineData:
    elevation: float
    # KML coordinate order is longitude, latitude.
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ContourDataset:
    lines: tuple[ContourLineData, ...]
    boundary: tuple[tuple[float, float], ...]
    source_point_count: int
    polygon_count: int


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numeric_value(value: str | None) -> float | None:
    match = _NUMBER.fullmatch(value or "")
    if not match:
        return None
    parsed = float(match.group(1))
    return parsed if math.isfinite(parsed) else None


def _coordinates(text: str | None) -> list[tuple[float, float, float | None]]:
    points: list[tuple[float, float, float | None]] = []
    for token in (text or "").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            longitude = float(parts[0])
            latitude = float(parts[1])
            altitude = float(parts[2]) if len(parts) >= 3 and parts[2] else None
        except ValueError as exc:
            raise ContourFileError("The KML contains a non-numeric coordinate") from exc
        if not (
            math.isfinite(longitude)
            and math.isfinite(latitude)
            and -180.0 <= longitude <= 180.0
            and -85.0 <= latitude <= 85.0
            and (altitude is None or math.isfinite(altitude))
        ):
            raise ContourFileError("The KML contains an invalid or unsupported coordinate")
        points.append((longitude, latitude, altitude))
    return points


def _placemark_elevation(placemark: ElementTree.Element) -> float | None:
    direct_name = next(
        (
            child.text
            for child in placemark
            if _local_name(child.tag) == "name"
        ),
        None,
    )
    named_value = _numeric_value(direct_name)
    if named_value is not None:
        return named_value
    if direct_name and any(marker in direct_name.casefold() for marker in _ELEVATION_KEYS):
        embedded_numbers = re.findall(
            r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?",
            direct_name,
        )
        if len(embedded_numbers) == 1:
            embedded_value = _numeric_value(embedded_numbers[0])
            if embedded_value is not None:
                return embedded_value
    for element in placemark.iter():
        if _local_name(element.tag) not in {"SimpleData", "Data"}:
            continue
        key = (element.attrib.get("name") or "").casefold()
        if any(marker in key for marker in _ELEVATION_KEYS):
            value_text = element.text
            if _local_name(element.tag) == "Data":
                value_text = next(
                    (
                        child.text
                        for child in element.iter()
                        if _local_name(child.tag) == "value"
                    ),
                    value_text,
                )
            value = _numeric_value(value_text)
            if value is not None:
                return value
    return None


def _line_elevation(
    placemark: ElementTree.Element,
    points: list[tuple[float, float, float | None]],
) -> float | None:
    # Explicit KML attributes/names take precedence because many exporters add
    # a constant zero altitude even when the contour elevation is stored as a
    # Placemark property.
    placemark_value = _placemark_elevation(placemark)
    if placemark_value is not None:
        return placemark_value
    altitudes = [point[2] for point in points if point[2] is not None]
    if len(altitudes) == len(points) and altitudes:
        spread = max(altitudes) - min(altitudes)
        if spread <= max(0.01, abs(statistics.fmean(altitudes)) * 1e-6):
            return float(statistics.fmean(altitudes))
    return None


def _signed_area(points: Iterable[tuple[float, float]]) -> float:
    sequence = list(points)
    if len(sequence) < 3:
        return 0.0
    return 0.5 * sum(
        sequence[index][0] * sequence[(index + 1) % len(sequence)][1]
        - sequence[(index + 1) % len(sequence)][0] * sequence[index][1]
        for index in range(len(sequence))
    )


def _extract_kml(document: bytes, filename: str) -> tuple[bytes, str]:
    suffix = Path(filename).suffix.casefold()
    is_zip = document.startswith(b"PK\x03\x04") or suffix == ".kmz"
    if not is_zip:
        if suffix not in {".kml", ".xml", ""}:
            raise ContourFileError("Upload a .kml or .kmz contour file")
        return document, "kml"

    try:
        with zipfile.ZipFile(BytesIO(document)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.contour_kmz_max_entries:
                raise ContourFileError("The KMZ contains too many archive entries")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise ContourFileError("Encrypted KMZ files are not supported")
            total_size = sum(entry.file_size for entry in entries)
            if total_size > settings.contour_max_uncompressed_bytes:
                raise ContourFileError("The expanded KMZ exceeds the configured size limit")
            for entry in entries:
                if entry.file_size and entry.compress_size == 0:
                    raise ContourFileError("The KMZ has an unsafe compression ratio")
                if entry.compress_size and entry.file_size / entry.compress_size > 200:
                    raise ContourFileError("The KMZ has an unsafe compression ratio")
            candidates = [entry for entry in entries if entry.filename.casefold().endswith(".kml")]
            if not candidates:
                raise ContourFileError("The KMZ does not contain a KML document")
            selected = next(
                (entry for entry in candidates if Path(entry.filename).name.casefold() == "doc.kml"),
                candidates[0],
            )
            return archive.read(selected), "kmz"
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ContourFileError("The KMZ archive is invalid") from exc


def parse_contour_document(document: bytes, filename: str) -> tuple[ContourDataset, str]:
    """Parse contour lines and the largest optional study-area polygon."""
    kml, input_format = _extract_kml(document, filename)
    if not kml.strip():
        raise ContourFileError("The uploaded contour file is empty")
    upper_prefix = kml[:4096].upper()
    if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
        raise ContourFileError("DTD and entity declarations are not supported")
    try:
        root = ElementTree.fromstring(kml)
    except (ElementTree.ParseError, RecursionError) as exc:
        raise ContourFileError("The uploaded KML is not well-formed XML") from exc

    lines: list[ContourLineData] = []
    boundaries: list[tuple[tuple[float, float], ...]] = []
    source_point_count = 0
    for placemark in (element for element in root.iter() if _local_name(element.tag) == "Placemark"):
        for geometry in placemark.iter():
            geometry_type = _local_name(geometry.tag)
            if geometry_type == "LineString":
                coordinate_element = next(
                    (child for child in geometry.iter() if _local_name(child.tag) == "coordinates"),
                    None,
                )
                points = _coordinates(coordinate_element.text if coordinate_element is not None else None)
                if len(points) < 2:
                    continue
                elevation = _line_elevation(placemark, points)
                if elevation is None:
                    continue
                source_point_count += len(points)
                if source_point_count > settings.contour_max_points:
                    raise ContourFileError("The contour file contains too many coordinate points")
                lines.append(
                    ContourLineData(
                        elevation=elevation,
                        points=tuple((point[0], point[1]) for point in points),
                    )
                )
                if len(lines) > settings.contour_max_lines:
                    raise ContourFileError("The contour file contains too many contour lines")
            elif geometry_type == "Polygon":
                coordinate_element = next(
                    (child for child in geometry.iter() if _local_name(child.tag) == "coordinates"),
                    None,
                )
                points = _coordinates(coordinate_element.text if coordinate_element is not None else None)
                boundary = tuple((point[0], point[1]) for point in points)
                if len(boundary) >= 3:
                    boundaries.append(boundary)

    levels = sorted({round(line.elevation, 6) for line in lines})
    if len(lines) < 3 or len(levels) < 3:
        raise ContourFileError("At least three contour lines at three distinct elevations are required")
    if levels[-1] - levels[0] < 0.5:
        raise ContourFileError("The contour elevation range is too small for terrain analysis")
    largest_boundary = max(boundaries, key=lambda item: abs(_signed_area(item)), default=())
    return (
        ContourDataset(
            lines=tuple(lines),
            boundary=largest_boundary,
            source_point_count=source_point_count,
            polygon_count=len(boundaries),
        ),
        input_format,
    )


def _grid_geometry(dataset: ContourDataset) -> tuple[np.ndarray, np.ndarray, float, float]:
    longitudes = [point[0] for line in dataset.lines for point in line.points]
    latitudes = [point[1] for line in dataset.lines for point in line.points]
    if dataset.boundary:
        longitudes.extend(point[0] for point in dataset.boundary)
        latitudes.extend(point[1] for point in dataset.boundary)
    minimum_lng, maximum_lng = min(longitudes), max(longitudes)
    minimum_lat, maximum_lat = min(latitudes), max(latitudes)
    if maximum_lng - minimum_lng > 180:
        raise ContourFileError("Contour files crossing the antimeridian are not supported")
    mean_latitude = statistics.fmean(latitudes)
    width_m = (maximum_lng - minimum_lng) * 111_320.0 * math.cos(math.radians(mean_latitude))
    height_m = (maximum_lat - minimum_lat) * 111_320.0
    if min(width_m, height_m) < 20.0:
        raise ContourFileError("The contour coverage is too small for catchment analysis")
    target_cell_m = max(width_m, height_m) / (settings.contour_grid_max - 1)
    columns = max(settings.contour_grid_min, int(round(width_m / target_cell_m)) + 1)
    rows = max(settings.contour_grid_min, int(round(height_m / target_cell_m)) + 1)
    columns = min(columns, settings.contour_grid_max)
    rows = min(rows, settings.contour_grid_max)
    latitude_axis = np.linspace(minimum_lat, maximum_lat, rows, dtype=np.float64)
    longitude_axis = np.linspace(minimum_lng, maximum_lng, columns, dtype=np.float64)
    latitude_cell_m = height_m / max(1, rows - 1)
    longitude_cell_m = width_m / max(1, columns - 1)
    return latitude_axis, longitude_axis, latitude_cell_m, longitude_cell_m


def _pixels(
    points: Iterable[tuple[float, float]],
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    minimum_lat, maximum_lat = float(latitudes[0]), float(latitudes[-1])
    minimum_lng, maximum_lng = float(longitudes[0]), float(longitudes[-1])
    columns = len(longitudes)
    rows = len(latitudes)
    return np.asarray(
        [
            [
                int(round((longitude - minimum_lng) / (maximum_lng - minimum_lng) * (columns - 1))),
                int(round((latitude - minimum_lat) / (maximum_lat - minimum_lat) * (rows - 1))),
            ]
            for longitude, latitude in points
        ],
        dtype=np.int32,
    )


def interpolate_contour_dem(
    dataset: ContourDataset,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, float | int | bool],
]:
    """Rasterize contour observations and harmonically interpolate gaps."""
    latitudes, longitudes, lat_cell_m, lng_cell_m = _grid_geometry(dataset)
    shape = (len(latitudes), len(longitudes))
    observed = np.zeros(shape, dtype=np.float32)
    known = np.zeros(shape, dtype=np.uint8)
    for line in dataset.lines:
        pixels = _pixels(line.points, latitudes, longitudes)
        cv2.polylines(observed, [pixels], False, float(line.elevation), 1, cv2.LINE_8)
        cv2.polylines(known, [pixels], False, 1, 1, cv2.LINE_8)

    analysis_mask = np.ones(shape, dtype=np.uint8)
    if dataset.boundary:
        analysis_mask.fill(0)
        cv2.fillPoly(
            analysis_mask,
            [_pixels(dataset.boundary, latitudes, longitudes)],
            1,
        )
        if int(np.sum(analysis_mask)) < max(25, int(0.05 * analysis_mask.size)):
            raise ContourFileError("The KML study-area polygon is invalid or too small")
    known = known & analysis_mask
    if int(np.sum(known)) < 20:
        raise ContourFileError("Too few contour cells remain inside the study area")

    unknown = (known == 0).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(
        unknown,
        cv2.DIST_L2,
        cv2.DIST_MASK_5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    label_values = np.zeros(int(labels.max()) + 1, dtype=np.float32)
    assigned_labels = np.zeros(int(labels.max()) + 1, dtype=bool)
    known_pixels = known.astype(bool)
    label_values[labels[known_pixels]] = observed[known_pixels]
    assigned_labels[labels[known_pixels]] = True
    if not np.all(assigned_labels[labels[analysis_mask.astype(bool)]]):
        raise ContourFileError("Contour interpolation could not label the complete study grid")
    dem = label_values[labels]

    unknown_inside = analysis_mask.astype(bool) & ~known.astype(bool)
    kernel = np.asarray([[0.0, 0.25, 0.0], [0.25, 0.0, 0.25], [0.0, 0.25, 0.0]], dtype=np.float32)
    converged = False
    iterations = 0
    for iteration in range(1, settings.contour_interpolation_iterations + 1):
        iterations = iteration
        neighbor_mean = cv2.filter2D(dem, -1, kernel, borderType=cv2.BORDER_REPLICATE)
        maximum_change = float(np.max(np.abs(neighbor_mean[unknown_inside] - dem[unknown_inside])))
        dem[unknown_inside] = neighbor_mean[unknown_inside]
        dem[known.astype(bool)] = observed[known.astype(bool)]
        if maximum_change < 0.002:
            converged = True
            break

    valid_dem = dem[analysis_mask.astype(bool)]
    source_min = min(line.elevation for line in dataset.lines)
    source_max = max(line.elevation for line in dataset.lines)
    if not np.isfinite(valid_dem).all():
        raise ContourFileError("Contour interpolation produced invalid elevations")
    dem = np.clip(dem, source_min, source_max).astype(np.float64)
    metadata: dict[str, float | int | bool] = {
        "rows": int(shape[0]),
        "columns": int(shape[1]),
        "cell_size_m": round(math.sqrt(lat_cell_m * lng_cell_m), 2),
        "observed_cell_ratio": round(float(np.sum(known)) / float(np.sum(analysis_mask)), 5),
        "interpolation_iterations": iterations,
        "interpolation_converged": converged,
    }
    return dem, latitudes, longitudes, analysis_mask.astype(bool), metadata


def _contour_interval(levels: list[float]) -> float | None:
    differences = [
        later - earlier
        for earlier, later in zip(levels, levels[1:], strict=False)
        if later > earlier
    ]
    return round(float(statistics.median(differences)), 3) if differences else None


def analyze_contour_file(document: bytes, filename: str) -> dict:
    """Return structured catchment information derived only from the upload."""
    dataset, input_format = parse_contour_document(document, filename)
    dem, latitudes, longitudes, analysis_mask, grid = interpolate_contour_dem(dataset)
    study_boundary_source = "uploaded_polygon" if dataset.boundary else "derived_extent"
    if dataset.boundary:
        site_polygon = [
            {"lng": longitude, "lat": latitude}
            for longitude, latitude in dataset.boundary
        ]
    else:
        site_polygon = [
            {"lat": float(latitudes[0]), "lng": float(longitudes[0])},
            {"lat": float(latitudes[0]), "lng": float(longitudes[-1])},
            {"lat": float(latitudes[-1]), "lng": float(longitudes[-1])},
            {"lat": float(latitudes[-1]), "lng": float(longitudes[0])},
        ]
    try:
        terrain = run_terrain_analysis(
            dem,
            latitudes,
            longitudes,
            site_polygon,
            analysis_mask=analysis_mask,
        )
    except AnalysisValidationError as exc:
        raise ContourFileError(str(exc)) from exc
    if terrain["pond_location"] is None:
        raise ContourFileError("No terrain-based pond point could be identified")

    levels = sorted({round(line.elevation, 6) for line in dataset.lines})
    warnings = [
        "The elevation grid is interpolated from uploaded contour lines; verify the result against the original survey or DEM.",
        "The uploaded polygon is used as an analysis extent, not as proof that every enclosed cell is buildable or suitable for a pond.",
        "The interior pond point is selected from terrain drainage concentration only; rivers, permanent water, ownership, soils, structures and excavation suitability are not verified by a contour-only upload.",
        "The catchment is limited to the uploaded contour coverage and may omit drainage from outside the map boundary.",
    ]
    if not dataset.boundary:
        warnings.append("No study-area polygon was supplied, so the contour bounding rectangle was used.")
    if dataset.polygon_count > 1:
        warnings.append("Multiple polygons were supplied; the largest polygon was used as the study boundary.")
    if not grid["interpolation_converged"]:
        warnings.append("Harmonic interpolation reached its iteration limit before the strict convergence threshold.")
    warnings.extend(terrain["warnings"])
    warnings = list(dict.fromkeys(warnings))

    pond = terrain["pond_location"]
    outlet = terrain["outlet_location"]
    safe_filename = Path(filename).name or "upload.kml"
    if len(safe_filename) > 255:
        suffix = Path(safe_filename).suffix[-15:]
        safe_filename = f"{safe_filename[: 255 - len(suffix)]}{suffix}"
    return {
        "analysis_status": "degraded",
        "input_file": safe_filename,
        "input_format": input_format,
        "contour_summary": {
            "contour_count": len(dataset.lines),
            "source_point_count": dataset.source_point_count,
            "elevation_level_count": len(levels),
            "minimum_elevation_m": round(levels[0], 3),
            "maximum_elevation_m": round(levels[-1], 3),
            "median_contour_interval_m": _contour_interval(levels),
        },
        "grid": {
            **grid,
            "method": "Contour rasterization with fixed-observation harmonic interpolation",
        },
        "pond_location": {
            "lat": round(float(pond["lat"]), 6),
            "lng": round(float(pond["lng"]), 6),
            "elevation_m": round(float(pond["elevation"]), 3),
            "boundary_distance_m": round(float(pond["boundary_distance_m"]), 2),
            "selection_method": (
                "Highest D8 contributing area after excluding the hydrologic outlet and "
                f"the first {terrain['candidate_boundary_setback_m']:.0f} m inside the analysis boundary; "
                "lower elevation is the tie-breaker"
            ),
        },
        "outlet_location": {
            "lat": round(float(outlet["lat"]), 6),
            "lng": round(float(outlet["lng"]), 6),
            "elevation_m": round(float(outlet["elevation"]), 3),
            "contributing_cells": int(outlet["contributing_cells"]),
        },
        "catchment": {
            "area_sqm": round(float(terrain["catchment_area_sqm"]), 2),
            "area_hectares": round(float(terrain["catchment_area_sqm"]) / 10_000.0, 4),
            "cell_count": int(terrain["catchment_cells"]),
            "study_grid_fraction": round(float(terrain["catchment_ratio"]), 5),
            "boundary": terrain["catchment_polygon"],
        },
        "contours": terrain["contours"],
        "drainage_path": terrain["drainage_path"],
        "study_area_boundary": site_polygon,
        "study_boundary_source": study_boundary_source,
        "candidate_boundary_setback_m": terrain["candidate_boundary_setback_m"],
        "quality": {
            "status": "degraded",
            "screening_only": True,
            "sources": {
                "contours": {
                    "name": "Uploaded contour map",
                    "status": "degraded",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "resolution": f"{_contour_interval(levels) or 'unknown'} m median contour interval",
                    "coverage_ratio": 1.0,
                    "message": "Terrain was reconstructed from contour geometry rather than a native raster DEM.",
                }
            },
            "warnings": warnings,
        },
    }
