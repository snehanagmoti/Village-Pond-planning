"""Typed application configuration loaded from environment variables."""

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()


def valid_geocoding_user_agent(value: str) -> bool:
    normalized = value.casefold()
    has_contact = any(marker in normalized for marker in ("mailto:", "http://", "https://"))
    is_placeholder = any(
        marker in normalized
        for marker in ("example.invalid", "example.org", "contact-not-configured")
    )
    return has_contact and not is_placeholder


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


class Settings:
    """Dependency-free settings object suitable for scripts and FastAPI."""

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "Village Pond Planning API")
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.cors_configured = "CORS_ORIGINS" in os.environ
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
        self.trusted_hosts_configured = "TRUSTED_HOSTS" in os.environ
        self.trusted_hosts = [
            host.strip()
            for host in os.getenv(
                "TRUSTED_HOSTS", "localhost,127.0.0.1,testserver"
            ).split(",")
            if host.strip()
        ]
        self.enable_api_docs = _bool("ENABLE_API_DOCS", not self.production)

        self.analysis_max_radius_km = _float("ANALYSIS_MAX_RADIUS_KM", 5.0, 0.5)
        self.elevation_grid_min = _int("ELEVATION_GRID_MIN", 23, 9)
        self.elevation_grid_max = _int("ELEVATION_GRID_MAX", 121, self.elevation_grid_min)
        self.elevation_public_grid_max = _int("ELEVATION_PUBLIC_GRID_MAX", 23, 9)
        self.elevation_concurrency = _int("ELEVATION_CONCURRENCY", 4, 1)
        self.elevation_min_interval_seconds = _float(
            "ELEVATION_MIN_INTERVAL_SECONDS", 0.25, 0.0
        )
        self.external_retry_count = _int("EXTERNAL_RETRY_COUNT", 2, 0)
        self.external_retry_max_delay_seconds = _float(
            "EXTERNAL_RETRY_MAX_DELAY_SECONDS", 30.0, 1.0
        )
        self.external_timeout_seconds = _float("EXTERNAL_TIMEOUT_SECONDS", 25.0, 1.0)
        self.cache_ttl_seconds = _int("SOURCE_CACHE_TTL_SECONDS", 3600, 0)
        self.elevation_api_url = os.getenv(
            "ELEVATION_API_URL", "https://api.open-meteo.com/v1/elevation"
        ).strip()
        self.elevation_fallback_enabled = _bool("ELEVATION_FALLBACK_ENABLED", True)
        self.elevation_tile_url = os.getenv(
            "ELEVATION_TILE_URL",
            "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
        ).strip()
        self.elevation_tile_zoom = min(15, _int("ELEVATION_TILE_ZOOM", 12, 8))
        self.elevation_tile_max_count = _int("ELEVATION_TILE_MAX_COUNT", 16, 1)
        self.elevation_tile_max_bytes = _int(
            "ELEVATION_TILE_MAX_BYTES", 2 * 1024 * 1024, 1024
        )
        self.rainfall_api_url = os.getenv(
            "RAINFALL_API_URL", "https://archive-api.open-meteo.com/v1/archive"
        ).strip()
        self.rainfall_fallback_enabled = _bool("RAINFALL_FALLBACK_ENABLED", True)
        self.rainfall_fallback_url = os.getenv(
            "RAINFALL_FALLBACK_URL",
            "https://power.larc.nasa.gov/api/temporal/daily/point",
        ).strip()
        self.rainfall_max_response_bytes = _int(
            "RAINFALL_MAX_RESPONSE_BYTES", 5 * 1024 * 1024, 1024
        )
        self.open_meteo_api_key = os.getenv("OPEN_METEO_API_KEY", "").strip() or None
        self.open_meteo_use_authorized = _bool("OPEN_METEO_USE_AUTHORIZED", False)

        self.rainfall_start_year = _int("RAINFALL_START_YEAR", 1991, 1940)
        self.rainfall_end_year = _int("RAINFALL_END_YEAR", 2025, self.rainfall_start_year)
        self.rainfall_model = os.getenv("RAINFALL_MODEL", "era5_land").strip()
        self.rainfall_min_valid_years = _int("RAINFALL_MIN_VALID_YEARS", 20, 3)

        self.geocoding_user_agent = os.getenv(
            "GEOCODING_USER_AGENT",
            "VillagePondPlanning/2.0 (contact-not-configured)",
        )
        self.geocoding_url = os.getenv(
            "GEOCODING_URL", "https://nominatim.openstreetmap.org/search"
        ).strip()
        self.geocoding_min_interval_seconds = _float(
            "GEOCODING_MIN_INTERVAL_SECONDS", 1.05, 1.0
        )

        self.history_enabled = _bool("HISTORY_ENABLED", False)
        self.history_api_key = os.getenv("HISTORY_API_KEY") or None
        self.rate_analyze_per_minute = _int("RATE_ANALYZE_PER_MINUTE", 6, 1)
        self.rate_contour_per_minute = _int("RATE_CONTOUR_PER_MINUTE", 6, 1)
        self.rate_search_per_minute = _int("RATE_SEARCH_PER_MINUTE", 20, 1)
        self.rate_history_per_minute = _int("RATE_HISTORY_PER_MINUTE", 30, 1)

        self.contour_max_upload_bytes = _int(
            "CONTOUR_MAX_UPLOAD_BYTES", 15 * 1024 * 1024, 1024
        )
        self.contour_max_uncompressed_bytes = _int(
            "CONTOUR_MAX_UNCOMPRESSED_BYTES", 30 * 1024 * 1024, 1024
        )
        self.contour_kmz_max_entries = _int("CONTOUR_KMZ_MAX_ENTRIES", 50, 1)
        self.contour_max_lines = _int("CONTOUR_MAX_LINES", 20_000, 3)
        self.contour_max_points = _int("CONTOUR_MAX_POINTS", 1_000_000, 100)
        self.contour_grid_min = _int("CONTOUR_GRID_MIN", 49, 17)
        self.contour_grid_max = _int(
            "CONTOUR_GRID_MAX", 181, self.contour_grid_min
        )
        self.contour_interpolation_iterations = _int(
            "CONTOUR_INTERPOLATION_ITERATIONS", 800, 50
        )
        self.contour_candidate_boundary_setback_m = _float(
            "CONTOUR_CANDIDATE_BOUNDARY_SETBACK_M", 75.0, 0.0
        )
        self.contour_detected_water_setback_m = _float(
            "CONTOUR_DETECTED_WATER_SETBACK_M", 60.0, 0.0
        )
        self.contour_candidate_option_count = min(
            5, _int("CONTOUR_CANDIDATE_OPTION_COUNT", 3, 1)
        )

        self.capture_efficiency = min(1.0, _float("CAPTURE_EFFICIENCY", 0.80, 0.0))
        self.pond_min_water_depth_m = _float("POND_MIN_WATER_DEPTH_M", 2.0, 0.5)
        self.pond_max_water_depth_m = max(
            self.pond_min_water_depth_m,
            _float("POND_MAX_WATER_DEPTH_M", 4.0, self.pond_min_water_depth_m),
        )
        self.pond_freeboard_m = _float("POND_FREEBOARD_M", 0.5, 0.0)
        self.pond_side_slope_h_to_v = _float("POND_SIDE_SLOPE_H_TO_V", 2.0, 0.0)
        self.pond_length_width_ratio = _float("POND_LENGTH_WIDTH_RATIO", 1.5, 1.0)
        self.approved_runoff_coefficient = self._optional_float(
            "APPROVED_RUNOFF_COEFFICIENT"
        )
        if (
            self.approved_runoff_coefficient is not None
            and self.approved_runoff_coefficient > 1.0
        ):
            self.approved_runoff_coefficient = None
        self.approved_runoff_coefficient_source = (
            os.getenv("APPROVED_RUNOFF_COEFFICIENT_SOURCE", "").strip() or None
        )
        self.design_rainfall_intensity_mm_h = self._optional_float(
            "DESIGN_RAINFALL_INTENSITY_MM_H"
        )

        self.imagery_tile_url = os.getenv(
            "IMAGERY_TILE_URL",
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ).strip()
        self.imagery_source_name = os.getenv(
            "IMAGERY_SOURCE_NAME", "Esri World Imagery"
        ).strip()
        self.imagery_license_url = os.getenv(
            "IMAGERY_LICENSE_URL",
            "https://www.esri.com/en-us/legal/terms/full-master-agreement",
        ).strip()
        self.imagery_use_authorized = _bool("IMAGERY_USE_AUTHORIZED", False)

        database_url = os.getenv("DATABASE_URL")
        database_password = os.getenv("DB_PASSWORD")
        self.database_credentials_configured = bool(
            database_url or (database_password and database_password != "postgres")
        )
        if database_url:
            self.database_url: str | URL = database_url
        else:
            self.database_url = URL.create(
                drivername="postgresql+psycopg2",
                username=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
                host=os.getenv("DB_HOST", "localhost"),
                port=_int("DB_PORT", 5432, 1),
                database=os.getenv("DB_NAME", "village_pond"),
            )

    @staticmethod
    def _optional_float(name: str) -> Optional[float]:
        value = os.getenv(name)
        if value is None or not value.strip():
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    def validation_errors(self) -> list[str]:
        """Return unsafe or internally inconsistent configuration findings."""
        errors: list[str] = []
        if self.rainfall_end_year < self.rainfall_start_year:
            errors.append("RAINFALL_END_YEAR must not precede RAINFALL_START_YEAR")
        requested_years = self.rainfall_end_year - self.rainfall_start_year + 1
        if self.rainfall_min_valid_years > requested_years:
            errors.append("RAINFALL_MIN_VALID_YEARS exceeds the configured period")
        if self.history_enabled and not self.history_api_key:
            errors.append("HISTORY_API_KEY is required when history is enabled")
        elif self.history_enabled and len(self.history_api_key or "") < 32:
            errors.append("HISTORY_API_KEY must contain at least 32 characters")
        if self.approved_runoff_coefficient is not None and not self.approved_runoff_coefficient_source:
            errors.append(
                "APPROVED_RUNOFF_COEFFICIENT_SOURCE is required with APPROVED_RUNOFF_COEFFICIENT"
            )
        if self.production:
            if not self.cors_configured:
                errors.append("CORS_ORIGINS must be explicitly configured in production")
            if not self.trusted_hosts_configured:
                errors.append("TRUSTED_HOSTS must be explicitly configured in production")
            if not valid_geocoding_user_agent(self.geocoding_user_agent):
                errors.append("GEOCODING_USER_AGENT must contain a real contact URL or email")
            if not self.geocoding_url.startswith("https://"):
                errors.append("GEOCODING_URL must use HTTPS in production")
            if "*" in self.cors_origins:
                errors.append("Wildcard CORS origins are not allowed in production")
            if not self.trusted_hosts or "*" in self.trusted_hosts:
                errors.append("TRUSTED_HOSTS must be explicit in production")
            if not self.imagery_use_authorized:
                errors.append(
                    "IMAGERY_USE_AUTHORIZED=true is required after confirming production imagery rights"
                )
            if not self.imagery_tile_url.startswith("https://"):
                errors.append("IMAGERY_TILE_URL must use HTTPS in production")
            if not all(token in self.imagery_tile_url for token in ("{z}", "{x}", "{y}")):
                errors.append("IMAGERY_TILE_URL must contain {z}, {x}, and {y} placeholders")
            if not self.open_meteo_use_authorized:
                errors.append(
                    "OPEN_METEO_USE_AUTHORIZED=true is required after confirming production data terms"
                )
            if not self.elevation_api_url.startswith("https://"):
                errors.append("ELEVATION_API_URL must use HTTPS in production")
            if self.elevation_fallback_enabled:
                if not self.elevation_tile_url.startswith("https://"):
                    errors.append("ELEVATION_TILE_URL must use HTTPS in production")
                if not all(
                    token in self.elevation_tile_url for token in ("{z}", "{x}", "{y}")
                ):
                    errors.append("ELEVATION_TILE_URL must contain {z}, {x}, and {y}")
            if not self.rainfall_api_url.startswith("https://"):
                errors.append("RAINFALL_API_URL must use HTTPS in production")
            if self.rainfall_fallback_enabled and not self.rainfall_fallback_url.startswith(
                "https://"
            ):
                errors.append("RAINFALL_FALLBACK_URL must use HTTPS in production")
            if self.history_enabled and not self.database_credentials_configured:
                errors.append(
                    "Non-default database credentials are required when production history is enabled"
                )
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
