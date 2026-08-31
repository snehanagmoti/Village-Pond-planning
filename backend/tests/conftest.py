import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def deterministic_application_settings(monkeypatch):
    """Keep API tests independent from a developer's ignored local .env file."""
    from routers import pond_planner

    monkeypatch.setattr(pond_planner.settings, "approved_runoff_coefficient", None)
    monkeypatch.setattr(pond_planner.settings, "approved_runoff_coefficient_source", None)
    monkeypatch.setattr(pond_planner.settings, "design_rainfall_intensity_mm_h", None)
    monkeypatch.setattr(pond_planner.settings, "history_enabled", False)
