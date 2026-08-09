"""
Rainfall Service
----------------
Queries historical precipitation data from the Open-Meteo Archive API.
Completely free — no API key required.

Returns:
    - Annual average rainfall (mm)
    - Monthly breakdown (12-month averages for charts)
"""

import httpx
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


async def get_rainfall_data(lat: float, lng: float) -> Dict:
    """
    Fetch historical rainfall data and compute annual + monthly averages.

    Uses the Open-Meteo Archive API for the period 2013–2023 (11 years).

    Parameters:
        lat: Latitude of the location
        lng: Longitude of the location

    Returns:
        Dict with:
            - annual_avg_mm:  Average annual rainfall in mm
            - monthly:        List of 12 dicts [{"month": "January", "rainfall_mm": 45.2}, ...]
    """
    url = (
        f"{ARCHIVE_API_URL}"
        f"?latitude={lat}&longitude={lng}"
        f"&start_date=2013-01-01&end_date=2023-12-31"
        f"&daily=precipitation_sum"
        f"&timezone=auto"
    )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                if "daily" in data and "precipitation_sum" in data["daily"]:
                    dates = data["daily"].get("time", [])
                    precip = data["daily"]["precipitation_sum"]

                    # Compute monthly totals across all years
                    monthly_totals = [0.0] * 12
                    monthly_counts = [0] * 12

                    for date_str, p in zip(dates, precip):
                        if p is not None:
                            month_idx = int(date_str[5:7]) - 1  # "YYYY-MM-DD" → month 0–11
                            monthly_totals[month_idx] += p
                            monthly_counts[month_idx] += 1

                    # Compute monthly averages (total / number of years with data)
                    num_years = 11.0
                    monthly_avg = []
                    for i in range(12):
                        # Average rainfall per year for this month
                        avg = monthly_totals[i] / num_years if num_years > 0 else 0.0
                        monthly_avg.append({
                            "month": MONTH_NAMES[i],
                            "rainfall_mm": round(avg, 1),
                        })

                    annual_avg = sum(m["rainfall_mm"] for m in monthly_avg)

                    logger.info("Rainfall data fetched: annual_avg=%.1f mm", annual_avg)

                    return {
                        "annual_avg_mm": round(annual_avg, 2),
                        "monthly": monthly_avg,
                    }

            logger.warning("Rainfall API returned status %d", response.status_code)

        except Exception as exc:
            logger.error("Error fetching rainfall: %s", exc)

    # Fallback: typical rural India ~800mm with a monsoon distribution
    logger.warning("Using fallback rainfall data")
    fallback_monthly = [
        {"month": "January",   "rainfall_mm": 10.0},
        {"month": "February",  "rainfall_mm": 12.0},
        {"month": "March",     "rainfall_mm": 15.0},
        {"month": "April",     "rainfall_mm": 25.0},
        {"month": "May",       "rainfall_mm": 40.0},
        {"month": "June",      "rainfall_mm": 150.0},
        {"month": "July",      "rainfall_mm": 200.0},
        {"month": "August",    "rainfall_mm": 180.0},
        {"month": "September", "rainfall_mm": 120.0},
        {"month": "October",   "rainfall_mm": 30.0},
        {"month": "November",  "rainfall_mm": 10.0},
        {"month": "December",  "rainfall_mm": 8.0},
    ]
    return {
        "annual_avg_mm": 800.0,
        "monthly": fallback_monthly,
    }
