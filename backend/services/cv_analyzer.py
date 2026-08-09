"""
Computer Vision Land Analyzer
------------------------------
Uses OpenCV to analyze satellite imagery for barren/available land suitable
for pond excavation.

Pipeline:
1. Download a satellite tile from Esri World Imagery (free, same tiles used by the map)
2. Convert to HSV colour space
3. Threshold for barren land colours (brown, tan, grey, dry earth)
4. Apply morphological operations to clean up noise
5. Calculate barren land ratio → adjust the runoff coefficient
6. Extract the largest barren region as a polygon

The barren-land ratio directly influences the runoff coefficient:
    - More barren land → higher runoff (less water absorbed by vegetation)
    - More vegetated → lower runoff
"""

import cv2
import numpy as np
import httpx
import math
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Esri World Imagery tile server — same free tiles used by the frontend map
TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def _lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
    """Convert geographic coordinates to Slippy Map tile coordinates."""
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_bounds(x: int, y: int, z: int) -> Tuple[float, float, float, float]:
    """Get geographic bounds (lat_min, lat_max, lng_min, lng_max) of a tile."""
    n = 2 ** z
    lng_min = x / n * 360.0 - 180.0
    lng_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lat_min, lat_max, lng_min, lng_max


async def download_satellite_tile(lat: float, lng: float, zoom: int = 14) -> Optional[np.ndarray]:
    """
    Download a satellite imagery tile from the Esri tile server.

    Parameters:
        lat:  Latitude of the centre point
        lng:  Longitude of the centre point
        zoom: Zoom level (14 gives ~10m/pixel, covering ~1.5 km per tile)

    Returns:
        BGR image as a NumPy array, or None on failure.
    """
    tx, ty = _lat_lng_to_tile(lat, lng, zoom)
    url = TILE_URL.format(z=zoom, y=ty, x=tx)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=15.0)
            if response.status_code == 200:
                img_bytes = np.frombuffer(response.content, np.uint8)
                img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
                if img is not None:
                    logger.info("Satellite tile downloaded: zoom=%d, tile=(%d,%d), shape=%s", zoom, tx, ty, img.shape)
                return img
            else:
                logger.warning("Tile download returned status %d", response.status_code)
        except Exception as exc:
            logger.error("Tile download error: %s", exc)

    return None


def analyze_satellite_image(img: np.ndarray) -> Dict:
    """
    Analyze a satellite image to detect barren/available land.

    Uses HSV colour-space thresholding to identify:
    - Brown/tan earth (typical barren land)
    - Grey/dry soil
    - Light rocky terrain

    Returns:
        Dict containing:
            - barren_ratio: float (0 to 1)
            - adjusted_runoff_coeff: float (runoff coefficient based on land cover)
            - barren_contour: largest barren region contour (pixel coords), or None
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # --- Colour ranges for barren land ---
    # Range 1: Brown/tan (typical dry earth, ploughed fields)
    lower_brown = np.array([8, 30, 50])
    upper_brown = np.array([30, 255, 255])
    mask_brown = cv2.inRange(hsv, lower_brown, upper_brown)

    # Range 2: Grey/dry soil
    lower_grey = np.array([0, 0, 80])
    upper_grey = np.array([180, 50, 200])
    mask_grey = cv2.inRange(hsv, lower_grey, upper_grey)

    # Range 3: Light tan / sandy
    lower_sand = np.array([15, 20, 120])
    upper_sand = np.array([35, 150, 255])
    mask_sand = cv2.inRange(hsv, lower_sand, upper_sand)

    # Combine all barren masks
    mask = cv2.bitwise_or(mask_brown, mask_grey)
    mask = cv2.bitwise_or(mask, mask_sand)

    # Morphological operations to reduce noise and fill small holes
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # fill small gaps
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # remove small noise

    total_pixels = img.shape[0] * img.shape[1]
    barren_pixels = cv2.countNonZero(mask)
    barren_ratio = barren_pixels / float(total_pixels)

    # Adjust runoff coefficient based on land cover
    # More barren → less infiltration → higher runoff
    # Fully vegetated: C ≈ 0.15,  Fully barren: C ≈ 0.55
    adjusted_c = 0.15 + barren_ratio * 0.40

    # Find the largest barren region contour
    contours_cv, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest_contour = None
    if contours_cv:
        largest_contour = max(contours_cv, key=cv2.contourArea)

    logger.info(
        "Land analysis: barren_ratio=%.2f, adjusted_C=%.2f, regions=%d",
        barren_ratio, adjusted_c, len(contours_cv),
    )

    return {
        "barren_ratio": round(barren_ratio, 3),
        "adjusted_runoff_coeff": round(adjusted_c, 3),
        "barren_contour": largest_contour,
    }


def barren_contour_to_polygon(
    contour: np.ndarray,
    center_lat: float,
    center_lng: float,
    img_shape: Tuple[int, int],
    zoom: int = 14,
) -> List[Dict[str, float]]:
    """
    Convert a pixel-coordinate contour from a satellite tile to geographic coords.

    Uses the tile's known geographic bounds to map pixels → lat/lng.

    Returns:
        List of {"lat": ..., "lng": ...} forming the barren-land polygon.
    """
    tx, ty = _lat_lng_to_tile(center_lat, center_lng, zoom)
    lat_min, lat_max, lng_min, lng_max = _tile_bounds(tx, ty, zoom)

    h, w = img_shape[:2]

    # Simplify the contour
    epsilon = 0.015 * cv2.arcLength(contour, True)
    contour = cv2.approxPolyDP(contour, epsilon, True)

    polygon = []
    for pt in contour:
        px, py = pt[0]
        # Pixel (0,0) = top-left = (lat_max, lng_min)
        lat = lat_max - (lat_max - lat_min) * py / (h - 1)
        lng = lng_min + (lng_max - lng_min) * px / (w - 1)
        polygon.append({"lat": float(lat), "lng": float(lng)})

    return polygon
