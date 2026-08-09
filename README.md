# AI-Based Village Pond Planning System

## Overview
A full-stack web application that assists village administrators in identifying suitable locations for pond construction to harvest rainwater. The system integrates **real geospatial analysis**, **historical rainfall data**, and **OpenCV-based satellite image segmentation** to recommend optimal pond dimensions and storage capacity.

## Technology Stack

| Layer        | Technology                                              |
|:-------------|:--------------------------------------------------------|
| **Backend**  | Python 3.9+, FastAPI, SQLAlchemy ORM                    |
| **Database** | PostgreSQL 15+                                          |
| **Frontend** | React 19 (Vite), react-leaflet, Vanilla CSS             |
| **CV/ML**    | OpenCV (HSV segmentation, morphological ops)            |
| **APIs**     | Open-Meteo Elevation & Archive (free), Nominatim (free), Esri Imagery (free) |

## Key Algorithms

| Algorithm | Purpose |
|:----------|:--------|
| **D8 Flow Direction** | Determines drainage direction for each DEM cell (8-neighbour steepest descent) |
| **Flow Accumulation** | Topological sort to count upstream cells draining through each point |
| **Watershed Delineation** | Reverse BFS from pour point to identify all cells in the catchment |
| **Contour Extraction** | OpenCV threshold + findContours on upscaled DEM grid |
| **Shoelace Formula** | Polygon area calculation in m² from lat/lng coordinates |
| **Rational Method** | Runoff estimation: `V = C × A × P` |
| **HSV Segmentation** | OpenCV barren-land detection from satellite imagery |

## Installation Guide

### Prerequisites
1. **Python 3.9+** — [python.org](https://python.org)
2. **Node.js 18+** — [nodejs.org](https://nodejs.org)
3. **PostgreSQL 15+** — running on port 5432

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure database credentials
# Edit .env file (copy from .env.example if needed)
cp .env.example .env
# Update DB_PASSWORD in .env

# Create the database
python create_db.py

# Start the backend server
uvicorn main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

### Accessing the Application
- **Frontend**: http://localhost:5173
- **Backend API Docs (Swagger)**: http://localhost:8000/docs
- **Backend API (ReDoc)**: http://localhost:8000/redoc

## API Documentation

### `POST /api/analyze`
Perform full terrain, rainfall, and land-cover analysis.

**Request Body:**
```json
{
  "center": { "lat": 18.5204, "lng": 73.8567 },
  "radius_km": 2.0
}
```

**Response:** Complete analysis including elevation stats, catchment polygon, contour lines, rainfall data (annual + monthly), land analysis (barren ratio, adjusted runoff coefficient), runoff estimation, and pond recommendation.

### `GET /api/search-village?q=<name>`
Geocode a village name using Nominatim. Returns up to 5 matching locations.

### `GET /api/history?limit=20`
Retrieve past analysis records from the database.

## Project Structure

```
village_pond_planning/
├── backend/
│   ├── .env                    # Database credentials (git-ignored)
│   ├── .env.example            # Template for .env
│   ├── requirements.txt        # Python dependencies
│   ├── main.py                 # FastAPI application entry point
│   ├── create_db.py            # Database creation script
│   ├── models/
│   │   ├── database.py         # SQLAlchemy models + connection
│   │   └── schemas.py          # Pydantic request/response schemas
│   ├── routers/
│   │   └── pond_planner.py     # API endpoints
│   └── services/
│       ├── elevation.py        # DEM fetching (Open-Meteo API)
│       ├── terrain.py          # D8 watershed + contour algorithms
│       ├── cv_analyzer.py      # OpenCV satellite image analysis
│       ├── rainfall.py         # Historical rainfall (Open-Meteo)
│       └── geocoding.py        # Village search (Nominatim)
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── App.jsx             # Main application component
│       ├── index.css           # Global styles
│       ├── main.jsx            # React entry point
│       └── components/
│           ├── SearchBar.jsx   # Village geocoding search
│           ├── MapLegend.jsx   # Map layer legend
│           └── RainfallChart.jsx  # SVG monthly rainfall chart
├── README.md                   # This file
└── Final_Technical_Report.md   # Detailed technical report
```

## All APIs are Free
This project uses **only free, no-API-key-required services**:
- **Open-Meteo Elevation API** — SRTM-based DEM data (~90m resolution)
- **Open-Meteo Archive API** — 11 years of daily precipitation data
- **Nominatim (OpenStreetMap)** — Geocoding / village name search
- **Esri World Imagery** — Satellite imagery tiles (display + CV analysis)
