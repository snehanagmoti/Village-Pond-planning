"""Policy-aware explicit place search using the public Nominatim endpoint."""

import asyncio
import logging
import time
from typing import Dict, List

from config import get_settings, valid_geocoding_user_agent
from services.cache import TTLCache
from services.http_client import get_with_retries
from services.quality import UpstreamDataError

logger = logging.getLogger(__name__)
settings = get_settings()
_cache: TTLCache[list[dict]] = TTLCache(maxsize=256, ttl_seconds=max(86400, settings.cache_ttl_seconds))
_request_lock = asyncio.Lock()
_last_request_at = 0.0


async def search_village(query: str, country_code: str = "in", limit: int = 5) -> List[Dict]:
    normalized = " ".join(query.split()).strip()
    if len(normalized) < 2 or len(normalized) > 120:
        return []
    if not valid_geocoding_user_agent(settings.geocoding_user_agent):
        raise UpstreamDataError(
            "geocoding", "Place search is disabled until an operator contact is configured"
        )
    cache_key = (normalized.casefold(), country_code, min(limit, 5))
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    global _last_request_at
    async with _request_lock:
        wait_for = settings.geocoding_min_interval_seconds - (time.monotonic() - _last_request_at)
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        try:
            response = await get_with_retries(
                settings.geocoding_url,
                params={
                    "q": normalized,
                    "format": "jsonv2",
                    "limit": min(limit, 5),
                    "countrycodes": country_code,
                    "addressdetails": 0,
                },
                headers={"User-Agent": settings.geocoding_user_agent},
            )
        except Exception as exc:
            raise UpstreamDataError(
                "geocoding", "The place-search provider is temporarily unavailable"
            ) from exc
        finally:
            _last_request_at = time.monotonic()

    if response.status_code != 200:
        logger.warning("geocoding_failed status=%d", response.status_code)
        raise UpstreamDataError(
            "geocoding", f"The place-search provider returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamDataError("geocoding", "The place-search provider returned invalid JSON") from exc
    if not isinstance(payload, list):
        raise UpstreamDataError("geocoding", "The place-search provider returned an invalid response")
    results = []
    for item in payload:
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        display_name = str(item.get("display_name", "")).strip()[:500]
        if display_name and -85 <= lat <= 85 and -180 <= lng <= 180:
            results.append({"display_name": display_name, "lat": lat, "lng": lng})
    _cache.set(cache_key, results)
    return results
