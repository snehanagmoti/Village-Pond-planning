"""
Database Models and Connection
-------------------------------
Uses SQLAlchemy ORM with PostgreSQL.
Credentials are loaded from environment variables via python-dotenv.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Float, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env file
load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "village_pond")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class PondAnalysis(Base):
    """Stores the results of each analysis run for auditing and history."""
    __tablename__ = "pond_analysis"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Village / location info
    village_name = Column(String, nullable=True)
    center_lat = Column(Float, nullable=False)
    center_lng = Column(Float, nullable=False)

    # Elevation data
    min_elevation = Column(Float)
    max_elevation = Column(Float)
    mean_elevation = Column(Float)
    relief = Column(Float)

    # Runoff statistics
    catchment_area_sqm = Column(Float)
    annual_rainfall_mm = Column(Float)
    runoff_coefficient = Column(Float)
    estimated_volume_m3 = Column(Float)

    # Land analysis
    barren_ratio = Column(Float)

    # Pond recommendation
    pond_lat = Column(Float)
    pond_lng = Column(Float)
    depth_m = Column(Float)
    capacity_m3 = Column(Float)
    surface_area_sqm = Column(Float)

    # Complex spatial data stored as JSON
    catchment_polygon = Column(JSON)
    government_land_polygon = Column(JSON)
    contours = Column(JSON)
    monthly_rainfall = Column(JSON)


def init_db():
    """Create all tables that don't exist yet."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
