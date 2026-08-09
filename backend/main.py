"""
AI-based Village Pond Planning System — FastAPI Application Entry Point
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import pond_planner
from models.database import init_db

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

# Initialize database tables on startup
init_db()

app = FastAPI(
    title="AI-based Village Pond Planning System API",
    description=(
        "A web application that analyzes terrain elevation, catchment areas, "
        "rainfall patterns, and satellite imagery to recommend optimal pond "
        "locations and dimensions for rural water conservation."
    ),
    version="1.0.0",
)

# CORS — allow frontend dev server access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pond_planner.router, prefix="/api", tags=["Pond Planning"])


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "Village Pond Planning System API is running"}
