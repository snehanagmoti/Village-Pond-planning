import cv2
import numpy as np
import pytest

from services import cv_analyzer
from services.cv_analyzer import (
    analyze_satellite_image,
    contour_to_polygon,
    raster_mask_to_terrain_grid,
)
from services.quality import UpstreamDataError


def test_blank_imagery_is_rejected():
    with pytest.raises(UpstreamDataError, match="blank"):
        analyze_satellite_image(np.zeros((256, 256, 3), dtype=np.uint8))


def test_bare_surface_contour_maps_to_bounds():
    image = np.zeros((128, 128, 3), dtype=np.uint8)
    image[:] = (80, 130, 180)
    cv2.rectangle(image, (20, 20), (100, 100), (60, 110, 170), -1)
    result = analyze_satellite_image(image)
    assert result.status == "degraded"
    if result.candidate_contour is not None:
        polygon = contour_to_polygon(result.candidate_contour, (18.0, 18.1, 73.0, 73.1), image.shape)
        assert len(polygon) >= 3
        assert all(18.0 <= point["lat"] <= 18.1 for point in polygon)


def test_detected_water_is_buffered_out_of_candidate_mask():
    image = np.full((256, 256, 3), (70, 120, 175), dtype=np.uint8)
    cv2.line(image, (128, 0), (128, 255), (150, 55, 20), 12)

    result = analyze_satellite_image(image)

    assert result.water_mask is not None
    assert cv2.countNonZero(result.water_mask) > 0
    if result.candidate_mask is not None:
        buffered_water = cv2.dilate(
            result.water_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        )
        assert cv2.countNonZero(cv2.bitwise_and(result.candidate_mask, buffered_water)) == 0


def test_imagery_mask_is_flipped_to_dem_latitude_order():
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[0, :] = 255

    grid = raster_mask_to_terrain_grid(mask, (3, 3))

    assert np.all(grid[-1, :])
    assert not np.any(grid[0, :])


@pytest.mark.anyio
async def test_mosaic_download_crops_to_requested_study_bounds(monkeypatch):
    async def tile(_, x, y, zoom):
        return x, y, np.full((256, 256, 3), 120, dtype=np.uint8)

    cv_analyzer._cache.clear()
    monkeypatch.setattr(cv_analyzer, "_download_tile", tile)
    result = await cv_analyzer.download_satellite_mosaic(18.5, 73.8, 0.5)
    assert result.image.shape[0] >= 32
    assert result.image.shape[1] >= 32
    assert result.source.coverage_ratio == 1.0
    assert result.bounds[0] < 18.5 < result.bounds[1]
    assert result.bounds[2] < 73.8 < result.bounds[3]


def test_study_area_crossing_antimeridian_is_rejected():
    with pytest.raises(UpstreamDataError):
        cv_analyzer._study_bounds(0.0, 179.999, 5.0)
