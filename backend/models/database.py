"""SQLAlchemy models and thread-contained persistence helpers."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine, func, text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import get_settings

settings = get_settings()
engine_options: dict[str, Any] = {"pool_pre_ping": True}
if str(settings.database_url).startswith("postgresql"):
    engine_options.update(pool_size=5, max_overflow=5)
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PondAnalysis(Base):
    __tablename__ = "pond_analysis"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    analysis_status = Column(String, nullable=False, default="incomplete")
    village_name = Column(String(200), nullable=True)
    center_lat = Column(Float, nullable=False)
    center_lng = Column(Float, nullable=False)
    min_elevation = Column(Float)
    max_elevation = Column(Float)
    mean_elevation = Column(Float)
    relief = Column(Float)
    catchment_area_sqm = Column(Float)
    annual_rainfall_mm = Column(Float)
    runoff_coefficient = Column(Float)
    estimated_volume_m3 = Column(Float)
    bare_surface_ratio = Column(Float)
    pond_lat = Column(Float)
    pond_lng = Column(Float)
    depth_m = Column(Float)
    capacity_m3 = Column(Float)
    surface_area_sqm = Column(Float)
    catchment_polygon = Column(JSON)
    candidate_land_polygon = Column(JSON)
    contours = Column(JSON)
    monthly_rainfall = Column(JSON)
    source_metadata = Column(JSON)
    warnings = Column(JSON)


def check_database() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def save_analysis(values: dict[str, Any]) -> int:
    with SessionLocal() as session:
        record = PondAnalysis(**values)
        session.add(record)
        session.commit()
        session.refresh(record)
        return int(record.id)


def fetch_history(limit: int) -> list[PondAnalysis]:
    with SessionLocal() as session:
        records = (
            session.query(PondAnalysis)
            .order_by(PondAnalysis.created_at.desc())
            .limit(limit)
            .all()
        )
        session.expunge_all()
        return records
