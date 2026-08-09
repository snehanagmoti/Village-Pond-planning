"""
Geocoding Service
-----------------
Provides village/place name search using the Nominatim (OpenStreetMap) API.
Completely free, no API key required.

Nominatim Usage Policy requires:
- A descriptive User-Agent header
- Max 1 request per second
"""

import httpx
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "VillagePondPlanningSystem/1.0 (academic-project)"


async def search_village(query: str, country_code: str = "in", limit: int = 5) -> List[Dict]:
    """
    Search for a village or place by name using the Nominatim geocoder.

    Parameters:
        query:        The search string (e.g. "Ralegan Siddhi, Maharashtra")
        country_code: ISO 3166-1 alpha-2 code to limit results (default "in" for India)
        limit:        Maximum number of results to return

    Returns:
        A list of dicts, each containing:
            - display_name: Full name as returned by Nominatim
            - lat: Latitude
            - lng: Longitude
    """
    params = {
        "q": query,
        "format": "json",
        "limit": limit,
        "countrycodes": country_code,
    }

    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                NOMINATIM_URL, params=params, headers=headers, timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                results = []
                for item in data:
                    results.append({
                        "display_name": item.get("display_name", ""),
                        "lat": float(item.get("lat", 0)),
                        "lng": float(item.get("lon", 0)),
                    })
                logger.info("Geocoding '%s' returned %d results", query, len(results))
                return results
            else:
                logger.warning("Nominatim returned status %d", response.status_code)
        except Exception as exc:
            logger.error("Geocoding error: %s", exc)

    return []
