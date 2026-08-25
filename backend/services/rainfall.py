"""Historical rainfall climatology with explicit model and coverage accounting."""

import logging
from collections import defaultdict
from dataclasses import dataclass

from config import get_settings
from services.cache import TTLCache
from services.http_client import get_with_retries
from services.quality import SourceInfo, UpstreamDataError

logger = logging.getLogger(__name__)
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
settings = get_settings()
_cache: TTLCache["RainfallResult"] = TTLCache(maxsize=128, ttl_seconds=settings.cache_ttl_seconds)


@dataclass
class RainfallResult:
    annual_avg_mm: float
    valid_years: int
    monthly: list[dict]
    source: SourceInfo


async def get_rainfall_data(lat: float, lng: float) -> RainfallResult:
    cache_key = (
        round(lat, 4), round(lng, 4), settings.rainfall_start_year,
        settings.rainfall_end_year, settings.rainfall_model,
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        cached.source.message = "; ".join(
            filter(None, [cached.source.message, "served from in-process cache"])
        )
        return cached

    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": f"{settings.rainfall_start_year}-01-01",
        "end_date": f"{settings.rainfall_end_year}-12-31",
        "daily": "precipitation_sum",
        "timezone": "auto",
        "models": settings.rainfall_model,
        **({"apikey": settings.open_meteo_api_key} if settings.open_meteo_api_key else {}),
    }
    try:
        response = await get_with_retries(settings.rainfall_api_url, params=params)
    except Exception as exc:
        raise UpstreamDataError("rainfall", f"Rainfall source was unavailable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise UpstreamDataError("rainfall", f"Rainfall source returned HTTP {response.status_code}")
    data = response.json().get("daily", {})
    dates = data.get("time")
    precipitation = data.get("precipitation_sum")
    if not isinstance(dates, list) or not isinstance(precipitation, list) or len(dates) != len(precipitation):
        raise UpstreamDataError("rainfall", "Rainfall source returned an invalid daily series")

    totals: dict[int, list[float]] = defaultdict(lambda: [0.0] * 12)
    counts: dict[int, list[int]] = defaultdict(lambda: [0] * 12)
    for date_text, value in zip(dates, precipitation, strict=False):
        if value is None:
            continue
        year = int(date_text[:4])
        month = int(date_text[5:7]) - 1
        totals[year][month] += max(0.0, float(value))
        counts[year][month] += 1

    valid_years: list[int] = []
    for year in range(settings.rainfall_start_year, settings.rainfall_end_year + 1):
        expected_days = 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365
        if sum(counts[year]) == expected_days:
            valid_years.append(year)
    if len(valid_years) < 3:
        raise UpstreamDataError("rainfall", "Fewer than three sufficiently complete rainfall years were returned")

    monthly: list[dict] = []
    for month_index, month_name in enumerate(MONTH_NAMES):
        month_values = [totals[year][month_index] for year in valid_years]
        if not month_values:
            continue
        monthly.append({
            "month": month_name,
            "rainfall_mm": round(sum(month_values) / len(month_values), 1),
            "valid_years": len(month_values),
        })
    if len(monthly) != 12:
        raise UpstreamDataError("rainfall", "Rainfall coverage is incomplete for one or more months")

    annual_values = [sum(totals[year]) for year in valid_years]
    annual_avg = round(sum(annual_values) / len(annual_values), 2)
    status = "reliable" if len(valid_years) >= settings.rainfall_min_valid_years else "degraded"
    message = None if status == "reliable" else f"Only {len(valid_years)} complete years available"
    source = SourceInfo(
        name="Open-Meteo Historical Weather API",
        status=status,
        resolution=(
            "0.1° (approximately 11 km)"
            if settings.rainfall_model.casefold() == "era5_land"
            else "model dependent; see source documentation"
        ),
        period=f"{settings.rainfall_start_year}-{settings.rainfall_end_year}",
        model=settings.rainfall_model,
        coverage_ratio=round(len(valid_years) / (settings.rainfall_end_year - settings.rainfall_start_year + 1), 4),
        message=message,
        license_url="https://open-meteo.com/en/terms",
    )
    result = RainfallResult(annual_avg, len(valid_years), monthly, source)
    _cache.set(cache_key, result)
    return result
