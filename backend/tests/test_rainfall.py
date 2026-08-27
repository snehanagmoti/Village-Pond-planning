from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services import rainfall
from services.quality import UpstreamDataError


class FakeResponse:
    def __init__(self, daily=None, *, payload=None, status_code=200):
        self.daily = daily
        self.payload = payload
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        if self.payload is not None:
            return self.payload
        return {"daily": self.daily}


@pytest.mark.anyio
async def test_rainfall_rejects_incomplete_series(monkeypatch):
    async def fake_get(url, params=None, headers=None):
        del url, params, headers
        return FakeResponse({"time": ["2020-01-01"], "precipitation_sum": [1.0]})

    monkeypatch.setattr(rainfall, "get_with_retries", fake_get)
    monkeypatch.setattr(rainfall.settings, "rainfall_fallback_enabled", False)
    rainfall._cache.clear()
    with pytest.raises(UpstreamDataError, match="Fewer than three"):
        await rainfall.get_rainfall_data(18.5, 73.8)


@pytest.mark.anyio
async def test_rainfall_uses_only_complete_calendar_years(monkeypatch):
    days = []
    current = date(2020, 1, 1)
    end = date(2022, 12, 31)
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)

    async def fake_get(url, params=None, headers=None):
        del url, params, headers
        return FakeResponse({"time": days, "precipitation_sum": [1.0] * len(days)})

    monkeypatch.setattr(rainfall, "get_with_retries", fake_get)
    monkeypatch.setattr(
        rainfall,
        "settings",
        SimpleNamespace(
            rainfall_start_year=2020,
            rainfall_end_year=2022,
            rainfall_model="era5_land",
            rainfall_min_valid_years=3,
            rainfall_api_url="https://example.test/archive",
            rainfall_max_response_bytes=5 * 1024 * 1024,
            open_meteo_api_key=None,
        ),
    )
    rainfall._cache.clear()
    result = await rainfall.get_rainfall_data(18.5, 73.8)
    assert result.valid_years == 3
    assert result.annual_avg_mm == pytest.approx((366 + 365 + 365) / 3, abs=0.01)
    assert len(result.monthly) == 12
    assert result.source.status == "reliable"


@pytest.mark.anyio
async def test_rainfall_uses_nasa_power_fallback(monkeypatch):
    values = {}
    current = date(2020, 1, 1)
    end = date(2022, 12, 31)
    while current <= end:
        values[current.strftime("%Y%m%d")] = 1.0
        current += timedelta(days=1)

    async def fake_get(url, params=None, headers=None):
        del params, headers
        if "example.test/archive" in url:
            return FakeResponse(status_code=429)
        return FakeResponse(
            payload={"properties": {"parameter": {"PRECTOTCORR": values}}}
        )

    monkeypatch.setattr(rainfall, "get_with_retries", fake_get)
    monkeypatch.setattr(
        rainfall,
        "settings",
        SimpleNamespace(
            rainfall_start_year=2020,
            rainfall_end_year=2022,
            rainfall_model="era5_land",
            rainfall_min_valid_years=3,
            rainfall_api_url="https://example.test/archive",
            rainfall_fallback_enabled=True,
            rainfall_fallback_url="https://example.test/power",
            rainfall_max_response_bytes=5 * 1024 * 1024,
            open_meteo_api_key=None,
        ),
    )
    rainfall._cache.clear()

    result = await rainfall.get_rainfall_data(21.24, 81.29)

    assert result.valid_years == 3
    assert result.annual_avg_mm == pytest.approx((366 + 365 + 365) / 3, abs=0.01)
    assert result.source.name == "NASA POWER Daily API"
    assert result.source.status == "degraded"
    assert "used NASA POWER fallback" in result.source.message
