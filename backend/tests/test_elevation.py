import numpy as np
import pytest

from services import elevation
from services.quality import UpstreamDataError


class FakeResponse:
    status_code = 200

    def __init__(self, values):
        self.values = values

    def json(self):
        return {"elevation": self.values}


@pytest.mark.anyio
async def test_elevation_rejects_empty_source(monkeypatch):
    async def fake_get(url, params=None, headers=None):
        del url, headers
        count = len(params["latitude"].split(","))
        return FakeResponse([None] * count)

    monkeypatch.setattr(elevation, "get_with_retries", fake_get)
    elevation._cache.clear()
    with pytest.raises(UpstreamDataError, match="No valid elevation"):
        await elevation.fetch_elevation_grid(18.5, 73.8, 0.5, grid_size=9)


@pytest.mark.anyio
async def test_elevation_interpolates_small_gap_and_reports_quality(monkeypatch):
    call = 0

    async def fake_get(url, params=None, headers=None):
        nonlocal call
        del url, headers
        count = len(params["latitude"].split(","))
        values = [100 + index for index in range(count)]
        if call == 0:
            values[0] = None
        call += 1
        return FakeResponse(values)

    monkeypatch.setattr(elevation, "get_with_retries", fake_get)
    elevation._cache.clear()
    result = await elevation.fetch_elevation_grid(18.5, 73.8, 0.5, grid_size=9)
    assert np.isfinite(result.dem).all()
    assert result.source.status == "degraded"
    assert result.missing_ratio > 0


@pytest.mark.anyio
async def test_elevation_batch_starts_are_paced(monkeypatch):
    clock = [100.0]
    starts = []

    async def fake_sleep(delay):
        clock[0] += delay

    async def fake_get(url, params=None, headers=None):
        del url, headers
        starts.append(clock[0])
        count = len(params["latitude"].split(","))
        return FakeResponse([100.0] * count)

    monkeypatch.setattr(elevation.settings, "elevation_min_interval_seconds", 0.25)
    monkeypatch.setattr(elevation.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(elevation.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(elevation, "get_with_retries", fake_get)
    monkeypatch.setattr(elevation, "_last_batch_started_at", None)
    elevation._cache.clear()

    await elevation.fetch_elevation_grid(18.5, 73.8, 0.5, grid_size=11)

    assert starts == [100.0, 100.25]


@pytest.mark.anyio
async def test_public_endpoint_uses_quota_safe_grid_and_reports_degradation(monkeypatch):
    calls = []

    async def fake_get(url, params=None, headers=None):
        del url, headers
        count = len(params["latitude"].split(","))
        calls.append(count)
        return FakeResponse([100.0] * count)

    monkeypatch.setattr(elevation.settings, "elevation_api_url", "https://api.open-meteo.com/v1/elevation")
    monkeypatch.setattr(elevation.settings, "open_meteo_api_key", None)
    monkeypatch.setattr(elevation.settings, "elevation_grid_min", 23)
    monkeypatch.setattr(elevation.settings, "elevation_grid_max", 121)
    monkeypatch.setattr(elevation.settings, "elevation_public_grid_max", 23)
    monkeypatch.setattr(elevation.settings, "elevation_min_interval_seconds", 0.0)
    monkeypatch.setattr(elevation, "get_with_retries", fake_get)
    elevation._cache.clear()

    result = await elevation.fetch_elevation_grid(18.5, 73.8, 2.0)

    assert result.dem.shape == (23, 23)
    assert calls == [100, 100, 100, 100, 100, 29]
    assert result.source.status == "degraded"
    assert "Public API quota limited" in result.source.message
