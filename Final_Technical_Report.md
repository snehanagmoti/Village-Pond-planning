# Final Technical Report: AI-based Village Pond Planning System

---

## 1. Introduction

Water conservation is a critical challenge in rural India, where communities depend heavily on monsoon rainfall for agriculture and domestic use. One proven solution is the construction of percolation ponds at strategic locations to harvest and store rainwater. However, selecting the optimal site requires analysis of terrain elevation, drainage patterns, catchment area, land availability, and historical rainfall — tasks traditionally done manually with significant effort and expertise.

This project presents an **AI-driven, full-stack web application** that automates the site selection process. Given a user-selected village location, the system fetches real geospatial data, performs hydrological modelling, analyses satellite imagery for land suitability, and recommends pond dimensions — all through an interactive map-based interface.

---

## 2. System Architecture

The system follows a **three-tier client-server architecture**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                      │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │ SearchBar│  │ MapView  │  │ StatsPanel │  │ RainfallChart   │  │
│  │(Nominatim│  │(Leaflet) │  │ (Sidebar)  │  │ (SVG bar chart) │  │
│  └────┬─────┘  └────┬─────┘  └──────┬─────┘  └────────┬────────┘  │
│       └──────────────┴───────────────┴─────────────────┘            │
│                              │  HTTP/JSON                           │
├──────────────────────────────┼──────────────────────────────────────┤
│                        BACKEND (FastAPI)                            │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ Elevation │  │  Terrain  │  │ Rainfall  │  │  CV Analyzer   │  │
│  │ Service   │  │  Service  │  │ Service   │  │  (OpenCV)      │  │
│  │(Open-Meteo│  │ (D8/BFS)  │  │(Open-Meteo│  │  (HSV thresh)  │  │
│  │ Elev API) │  │           │  │ Archive)  │  │                │  │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └───────┬────────┘  │
│        └──────────────┴──────────────┴────────────────┘            │
│                              │  SQLAlchemy ORM                      │
├──────────────────────────────┼──────────────────────────────────────┤
│                        DATABASE (PostgreSQL)                        │
│                    ┌─────────────────────────┐                      │
│                    │    pond_analysis table   │                      │
│                    │  (JSON columns for       │                      │
│                    │   polygons & contours)   │                      │
│                    └─────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Frontend
- **React 19** with Vite for fast development builds
- **react-leaflet** with Esri World Imagery satellite tiles for the interactive map
- **Component-based architecture**: `SearchBar`, `MapLegend`, `RainfallChart` components
- **Vanilla CSS** with a dark glassmorphism design system using CSS custom properties

### 2.2 Backend
- **FastAPI** RESTful service with 3 endpoints (`/analyze`, `/search-village`, `/history`)
- **Service-oriented architecture**: independent modules for elevation, terrain, rainfall, CV analysis, and geocoding
- **Structured logging** throughout the analysis pipeline for debugging

### 2.3 Database
- **PostgreSQL** with SQLAlchemy ORM
- JSON columns for complex spatial data (polygons, contour lines, monthly rainfall)
- Environment-variable-based configuration via `python-dotenv`

---

## 3. Methodology & Algorithms

### 3.1 Elevation Data Acquisition

The system fetches a real **Digital Elevation Model (DEM)** from the **Open-Meteo Elevation API**, which provides SRTM-based elevation data at approximately **90-metre resolution** worldwide. For each analysis:

- A 25×25 grid of geographic points is generated within a 2 km radius of the selected location
- Elevation values are fetched in batches of 100 via HTTP (respecting API rate limits)
- NaN values (e.g., over water) are filled using neighbour-averaged interpolation

This produces a real elevation grid that drives all subsequent hydrological analysis.

### 3.2 D8 Flow Direction Algorithm

The **D8 (deterministic eight-neighbour)** algorithm is the foundation of the hydrological analysis. For each interior cell in the DEM:

1. Examine all 8 neighbours (N, NE, E, SE, S, SW, W, NW)
2. Compute the slope to each neighbour: `slope = (elev_current − elev_neighbour) / distance`
   - Cardinal distance = 1 cell, diagonal = √2 cells
3. Assign the flow direction to the **steepest descent** neighbour
4. If no neighbour is lower, mark the cell as a **pit** (potential outlet)

**Time complexity**: O(n) where n = number of grid cells.

### 3.3 Flow Accumulation (Topological Sort)

Flow accumulation counts the number of upstream cells draining through each point. This is computed using **Kahn's algorithm** (topological sort on the D8 flow graph):

1. Build an in-degree array: for each cell, count how many cells flow into it
2. Seed a queue with all cells having in-degree = 0 (headwater cells)
3. Process cells in topological order, propagating each cell's accumulation to its downstream neighbour

The cell with the **highest accumulation** becomes the **pour point** (drainage outlet) for watershed delineation.

### 3.4 Watershed Delineation (Reverse BFS)

From the pour point, a **reverse breadth-first search** identifies all cells that drain to it:

1. Start at the pour point, mark it as part of the catchment
2. For each marked cell, check all 8 neighbours
3. If a neighbour's flow direction points *toward* the current cell (i.e., it is upstream), mark it and enqueue it
4. Continue until no more upstream cells are found

The result is a boolean mask representing the **catchment area** — all land whose rainfall eventually flows to the pour point.

### 3.5 Contour Line Extraction

Contour lines are extracted from the real DEM using OpenCV:

1. **Upscale** the 25×25 DEM to 200×200 using bilinear interpolation for smoother lines
2. **Gaussian blur** to remove grid artefacts
3. For each elevation level (6 evenly-spaced levels between min and max):
   - Binary threshold the DEM at that level
   - Run `cv2.findContours` to extract iso-elevation boundaries
   - Simplify using `cv2.approxPolyDP` (Ramer-Douglas-Peucker algorithm)
4. Convert pixel coordinates back to geographic lat/lng

### 3.6 Catchment Area Calculation (Shoelace Formula)

The catchment boundary polygon's area is computed using the **Shoelace formula**:

1. Project lat/lng coordinates to a local Cartesian system (metres) using the cosine correction:
   - `x = (lng − avg_lng) × 111320 × cos(avg_lat)`
   - `y = (lat − avg_lat) × 111320`
2. Apply the Shoelace formula: `A = ½ |Σ(xᵢyᵢ₊₁ − xᵢ₊₁yᵢ)|`

This is accurate for areas under ~50 km where Earth curvature is negligible.

### 3.7 OpenCV Satellite Image Analysis

The system downloads a satellite tile from the Esri World Imagery server and runs computer vision analysis:

1. Convert the BGR image to **HSV colour space**
2. Apply three colour range thresholds:
   - Brown/tan (H: 8–30, S: 30–255, V: 50–255) — ploughed/bare soil
   - Grey/dry (H: 0–180, S: 0–50, V: 80–200) — rocky/dry ground
   - Sandy (H: 15–35, S: 20–150, V: 120–255) — sandy terrain
3. Combine masks using bitwise OR
4. Apply **morphological close** (fill small gaps) and **open** (remove noise) with an elliptical kernel
5. Calculate the **barren ratio** = barren pixels / total pixels
6. Extract the largest barren contour as the "available land" polygon
7. **Adjust the runoff coefficient**: `C = 0.15 + barren_ratio × 0.40`
   - Fully vegetated (0% barren) → C = 0.15
   - Fully barren (100%) → C = 0.55

#### 3.7.1 Government / Available Land Identification

The assignment requires identifying "available land suitable for pond excavation" (Requirement 3). In practice, government land records for Indian villages are maintained by state revenue departments and are **not available via any free, publicly accessible API**. Therefore, this system uses **barren/unused land detected via satellite image analysis as a proxy** for potentially available excavation sites. The rationale is:

- Barren, unvegetated land is more likely to be common/waste land (often government-owned in Indian villages)
- Such land has no standing crops or structures, making it practically suitable for excavation
- The detected barren polygon is displayed on the map as "Available Land (Detected via CV)" so the user can cross-reference with local land records

This approach is consistent with how remote sensing is used in real-world rural planning — satellite-based land-use classification serves as a first screening tool before ground verification with official records.



### 3.8 Historical Rainfall Integration

Historical precipitation data for 2013–2023 (11 years) is queried from the **Open-Meteo Archive API**:

- Daily precipitation sums are aggregated by month across all years
- Monthly averages are computed by dividing each month's total by 11
- The annual average is the sum of all 12 monthly averages
- A fallback monsoon distribution is provided if the API is unreachable

### 3.9 Runoff Estimation (Rational Method)

Annual runoff volume is estimated using the **Rational Method**:

```
V = C × A × P
```

Where:
- **V** = Runoff volume (m³)
- **C** = Runoff coefficient (from OpenCV land analysis, typically 0.15–0.55)
- **A** = Catchment area (m²) (from Shoelace formula on watershed polygon)
- **P** = Annual rainfall depth (m) (from Open-Meteo historical average)

### 3.10 Pond Dimension Recommendation

Based on the estimated runoff volume:

1. **Capture efficiency**: Target 80% of annual runoff
2. **Depth selection**: Continuous interpolation between 2.0m (< 5000 m³) and 4.0m (> 50000 m³)
3. **Surface area**: `A = Capacity / Depth`
4. **Location**: Placed at the **lowest elevation point** within the catchment (found from the DEM)

---

## 4. External APIs Used

All APIs are **completely free** with no API keys required:

| API | Purpose | Rate Limits |
|:----|:--------|:------------|
| Open-Meteo Elevation | DEM grid (~90m SRTM) | Generous, ~100 req/min |
| Open-Meteo Archive | 11-year daily precipitation | Generous, ~100 req/min |
| Nominatim (OpenStreetMap) | Village name geocoding | 1 req/sec |
| Esri World Imagery | Satellite tiles (map + CV input) | Fair use |

---

## 5. Frontend Design

The frontend uses a **dark glassmorphism** design with:

- Full-screen satellite map with interactive click-to-analyse
- **Village search bar** with debounced geocoding and dropdown results
- **Statistics dashboard** with categorised panels: Elevation, Hydrology, Land Cover
- **Monthly rainfall bar chart** (pure SVG, no external charting library)
- **Map legend** overlay explaining all layer colours
- **Contour tooltips** showing elevation values on hover
- Responsive layout adapting to mobile viewports

---

## 6. Database Schema

```sql
CREATE TABLE pond_analysis (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT NOW(),
    village_name    VARCHAR,
    center_lat      FLOAT NOT NULL,
    center_lng      FLOAT NOT NULL,
    min_elevation   FLOAT,
    max_elevation   FLOAT,
    mean_elevation  FLOAT,
    relief          FLOAT,
    catchment_area_sqm FLOAT,
    annual_rainfall_mm FLOAT,
    runoff_coefficient FLOAT,
    estimated_volume_m3 FLOAT,
    barren_ratio    FLOAT,
    pond_lat        FLOAT,
    pond_lng        FLOAT,
    depth_m         FLOAT,
    capacity_m3     FLOAT,
    surface_area_sqm FLOAT,
    catchment_polygon   JSON,
    government_land_polygon JSON,
    contours        JSON,
    monthly_rainfall JSON
);
```

---

## 7. Evaluation and Results

The system was tested with multiple Indian village locations:

- **Terrain analysis** correctly identifies topographic depressions and drainage patterns from real SRTM elevation data
- **Contour lines** align with the actual elevation gradient visible on satellite imagery
- **Rainfall values** match published IMD statistics for the test regions
- **OpenCV barren-land detection** successfully distinguishes agricultural/barren land from forested/vegetated areas
- **Pond recommendations** place the pond at the lowest point in the catchment — the natural drainage outlet

---

## 8. Conclusion

By combining Python's robust data science ecosystem (NumPy, OpenCV, httpx) with modern web technologies (React, Leaflet, FastAPI, PostgreSQL), this application provides a complete, data-driven tool for village pond planning. All geospatial algorithms operate on real elevation and satellite data, and all external services are freely available — making the system practical for deployment in resource-constrained rural settings.
