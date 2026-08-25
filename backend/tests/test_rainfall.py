from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services import rainfall
from services.quality import UpstreamDataError


class FakeResponse:
    status_code = 200

    def __init__(self, daily):
        self.daily = daily

    def json(self):
        return {"daily": self.daily}


@pytest.mark.anyio
async def test_rainfall_rejects_incomplete_series(monkeypatch):
    async def fake_get(url, params=None, headers=None):
        del url, params, headers
        return FakeResponse({"time": ["2020-01-01"], "precipitation_sum": [1.0]})

    monkeypatch.setattr(rainfall, "get_with_retries", fake_get)
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
            open_meteo_api_key=None,
        ),
    )
    rainfall._cache.clear()
    result = await rainfall.get_rainfall_data(18.5, 73.8)
    assert result.valid_years == 3
    assert result.annual_avg_mm == pytest.approx((366 + 365 + 365) / 3, abs=0.01)
    assert len(result.monthly) == 12
    assert result.source.status == "reliable"
