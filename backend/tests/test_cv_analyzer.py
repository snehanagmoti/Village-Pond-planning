import cv2
import numpy as np
import pytest

from services import cv_analyzer
from services.cv_analyzer import analyze_satellite_image, contour_to_polygon
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
