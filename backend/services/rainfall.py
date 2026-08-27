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


def _summarize_daily(
    dates: list[str],
    precipitation: list[float | None],
    *,
    source_name: str,
    resolution: str,
    model: str,
    license_url: str,
    forced_message: str | None = None,
) -> RainfallResult:
    if len(dates) != len(precipitation):
        raise UpstreamDataError("rainfall", "Rainfall source returned an invalid daily series")
    totals: dict[int, list[float]] = defaultdict(lambda: [0.0] * 12)
    counts: dict[int, list[int]] = defaultdict(lambda: [0] * 12)
    for date_text, value in zip(dates, precipitation, strict=True):
        if value is None:
            continue
        try:
            year = int(date_text[:4])
            month = int(date_text[5:7]) - 1
            parsed_value = float(value)
        except (TypeError, ValueError) as exc:
            raise UpstreamDataError("rainfall", "Rainfall source returned invalid values") from exc
        if month < 0 or month > 11 or parsed_value <= -900.0:
            continue
        totals[year][month] += max(0.0, parsed_value)
        counts[year][month] += 1

    valid_years: list[int] = []
    for year in range(settings.rainfall_start_year, settings.rainfall_end_year + 1):
        expected_days = 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365
        if sum(counts[year]) == expected_days:
            valid_years.append(year)
    if len(valid_years) < 3:
        raise UpstreamDataError(
            "rainfall", "Fewer than three sufficiently complete rainfall years were returned"
        )

    monthly: list[dict] = []
    for month_index, month_name in enumerate(MONTH_NAMES):
        month_values = [totals[year][month_index] for year in valid_years]
        monthly.append({
            "month": month_name,
            "rainfall_mm": round(sum(month_values) / len(month_values), 1),
            "valid_years": len(month_values),
        })

    annual_values = [sum(totals[year]) for year in valid_years]
    annual_avg = round(sum(annual_values) / len(annual_values), 2)
    status = (
        "degraded"
        if forced_message or len(valid_years) < settings.rainfall_min_valid_years
        else "reliable"
    )
    message = forced_message
    if message is None and status == "degraded":
        message = f"Only {len(valid_years)} complete years available"
    source = SourceInfo(
        name=source_name,
        status=status,
        resolution=resolution,
        period=f"{settings.rainfall_start_year}-{settings.rainfall_end_year}",
        model=model,
        coverage_ratio=round(
            len(valid_years) / (settings.rainfall_end_year - settings.rainfall_start_year + 1),
            4,
        ),
        message=message,
        license_url=license_url,
    )
    return RainfallResult(annual_avg, len(valid_years), monthly, source)


async def _fetch_open_meteo(lat: float, lng: float) -> RainfallResult:
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
    if len(response.content) > settings.rainfall_max_response_bytes:
        raise UpstreamDataError("rainfall", "Rainfall source response exceeded the size limit")
    data = response.json().get("daily", {})
    dates = data.get("time")
    precipitation = data.get("precipitation_sum")
    if not isinstance(dates, list) or not isinstance(precipitation, list):
        raise UpstreamDataError("rainfall", "Rainfall source returned an invalid daily series")
    return _summarize_daily(
        dates,
        precipitation,
        source_name="Open-Meteo Historical Weather API",
        resolution=(
            "0.1° (approximately 11 km)"
            if settings.rainfall_model.casefold() == "era5_land"
            else "model dependent; see source documentation"
        ),
        model=settings.rainfall_model,
        license_url="https://open-meteo.com/en/terms",
    )


async def _fetch_nasa_power(lat: float, lng: float, primary_failure: str) -> RainfallResult:
    params = {
        "parameters": "PRECTOTCORR",
        "community": "AG",
        "longitude": lng,
        "latitude": lat,
        "start": f"{settings.rainfall_start_year}0101",
        "end": f"{settings.rainfall_end_year}1231",
        "format": "JSON",
    }
    try:
        response = await get_with_retries(settings.rainfall_fallback_url, params=params)
    except Exception as exc:
        raise UpstreamDataError(
            "rainfall", f"NASA POWER rainfall fallback was unavailable: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise UpstreamDataError(
            "rainfall", f"NASA POWER rainfall fallback returned HTTP {response.status_code}"
        )
    if len(response.content) > settings.rainfall_max_response_bytes:
        raise UpstreamDataError("rainfall", "NASA POWER rainfall response exceeded the size limit")
    values = (
        response.json()
        .get("properties", {})
        .get("parameter", {})
        .get("PRECTOTCORR")
    )
    if not isinstance(values, dict):
        raise UpstreamDataError("rainfall", "NASA POWER returned an invalid daily series")
    dates: list[str] = []
    precipitation: list[float | None] = []
    for date_key, value in sorted(values.items()):
        if len(date_key) != 8 or not date_key.isdigit():
            raise UpstreamDataError("rainfall", "NASA POWER returned an invalid date key")
        dates.append(f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}")
        precipitation.append(value)
    return _summarize_daily(
        dates,
        precipitation,
        source_name="NASA POWER Daily API",
        resolution="0.5° latitude x 0.625° longitude MERRA-2 grid",
        model="MERRA-2 corrected precipitation (PRECTOTCORR)",
        license_url="https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
        forced_message=(
            f"{primary_failure}; used NASA POWER fallback. Grid rainfall is not a village gauge"
        ),
    )


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

    try:
        result = await _fetch_open_meteo(lat, lng)
    except UpstreamDataError as primary_error:
        if not settings.rainfall_fallback_enabled:
            raise
        try:
            result = await _fetch_nasa_power(lat, lng, primary_error.message)
        except UpstreamDataError as fallback_error:
            logger.warning("rainfall_fallback_failed error_type=%s", type(fallback_error).__name__)
            raise UpstreamDataError(
                "rainfall", f"{primary_error.message}; rainfall fallback was also unavailable"
            ) from fallback_error
    _cache.set(cache_key, result)
    return result
