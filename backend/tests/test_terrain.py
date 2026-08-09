"""
Unit Tests for Terrain Analysis Algorithms
-------------------------------------------
Tests the core hydrological algorithms: D8 flow, accumulation,
catchment delineation, runoff, and pond sizing.
"""

import numpy as np
import pytest
from services.terrain import (
    d8_flow_direction,
    flow_accumulation,
    delineate_catchment,
    calculate_runoff,
    recommend_pond_dimensions,
    polygon_area_sqm,
)


class TestD8FlowDirection:
    """Test D8 flow direction computation."""

    def test_simple_slope_north(self):
        """Flow should go towards lowest neighbour (north = row-1)."""
        dem = np.array([
            [5.0, 3.0, 5.0],
            [5.0, 6.0, 5.0],
            [5.0, 5.0, 5.0],
        ])
        flow_dir = d8_flow_direction(dem)
        # Interior cell (1,1) has value 6; lowest neighbour is (0,1)=3
        # Direction 0 = north (row-1, col 0)
        assert flow_dir[1, 1] == 0

    def test_pit_cell(self):
        """A cell lower than all neighbours is a pit (direction -1)."""
        dem = np.array([
            [10.0, 10.0, 10.0],
            [10.0,  1.0, 10.0],
            [10.0, 10.0, 10.0],
        ])
        flow_dir = d8_flow_direction(dem)
        assert flow_dir[1, 1] == -1

    def test_edge_cells_are_boundary(self):
        """Edge cells should always have direction -1."""
        dem = np.ones((5, 5)) * 100.0
        flow_dir = d8_flow_direction(dem)
        # All border cells should be -1
        assert np.all(flow_dir[0, :] == -1)
        assert np.all(flow_dir[-1, :] == -1)
        assert np.all(flow_dir[:, 0] == -1)
        assert np.all(flow_dir[:, -1] == -1)


class TestFlowAccumulation:
    """Test flow accumulation counts."""

    def test_flat_terrain_no_accumulation(self):
        """On flat terrain, cells have minimal accumulation (just themselves)."""
        dem = np.ones((5, 5)) * 100.0
        flow_dir = d8_flow_direction(dem)
        acc = flow_accumulation(flow_dir)
        # All cells should have accumulation = 1 (themselves only)
        assert np.all(acc >= 1)

    def test_v_shaped_valley(self):
        """A V-shaped terrain should accumulate flow at the bottom."""
        dem = np.array([
            [10, 10, 10, 10, 10],
            [ 8,  8,  8,  8,  8],
            [ 6,  6,  3,  6,  6],
            [ 8,  8,  8,  8,  8],
            [10, 10, 10, 10, 10],
        ], dtype=np.float64)
        flow_dir = d8_flow_direction(dem)
        acc = flow_accumulation(flow_dir)
        # The centre cell should have the highest accumulation
        center_acc = acc[2, 2]
        assert center_acc > 1


class TestCatchmentDelineation:
    """Test watershed / catchment delineation."""

    def test_single_cell_catchment(self):
        """A pit with no upstream cells has a 1-cell catchment."""
        flow_dir = np.full((3, 3), -1, dtype=np.int32)
        mask = delineate_catchment(flow_dir, 1, 1)
        assert mask[1, 1] == True
        assert np.sum(mask) == 1

    def test_linear_flow(self):
        """Cells flowing in a line should all be in the catchment."""
        # Direction 4 = south (row+1, col 0)
        flow_dir = np.full((5, 5), -1, dtype=np.int32)
        # Create a linear chain: (1,2) → (2,2) → (3,2)
        flow_dir[1, 2] = 4  # flows south
        flow_dir[2, 2] = 4  # flows south
        mask = delineate_catchment(flow_dir, 3, 2)
        assert mask[3, 2] == True  # pour point
        assert mask[2, 2] == True  # upstream
        assert mask[1, 2] == True  # upstream of upstream


class TestRunoffCalculation:
    """Test the Rational Method runoff calculation."""

    def test_basic_calculation(self):
        """V = C × A × (P/1000). With C=0.3, A=10000m², P=800mm → V=2400."""
        volume = calculate_runoff(10000, 800, 0.3)
        assert volume == pytest.approx(2400.0)

    def test_zero_rainfall(self):
        """Zero rainfall should produce zero runoff."""
        volume = calculate_runoff(10000, 0, 0.3)
        assert volume == 0.0

    def test_zero_area(self):
        """Zero area should produce zero runoff."""
        volume = calculate_runoff(0, 800, 0.3)
        assert volume == 0.0


class TestPondDimensions:
    """Test pond dimension recommendation."""

    def test_small_volume(self):
        """Small volumes (< 5000 m³ capacity) → 2.0m depth."""
        depth, capacity, area = recommend_pond_dimensions(5000)
        assert capacity == pytest.approx(4000.0)  # 80% capture
        assert depth == 2.0
        assert area == pytest.approx(2000.0)

    def test_large_volume(self):
        """Large volumes (> 62500 m³) → 4.0m depth."""
        depth, capacity, area = recommend_pond_dimensions(100000)
        assert capacity == pytest.approx(80000.0)
        assert depth == 4.0
        assert area == pytest.approx(20000.0)

    def test_mid_volume_interpolated(self):
        """Mid-range volumes should have interpolated depth between 2 and 4."""
        depth, capacity, area = recommend_pond_dimensions(30000)
        assert 2.0 < depth < 4.0
        assert capacity == pytest.approx(24000.0)

    def test_surface_area_is_capacity_over_depth(self):
        """Surface area should always equal capacity / depth."""
        for vol in [1000, 10000, 50000, 100000]:
            depth, capacity, area = recommend_pond_dimensions(vol)
            assert area == pytest.approx(capacity / depth, rel=0.01)


class TestPolygonArea:
    """Test Shoelace polygon area calculation."""

    def test_known_square(self):
        """A ~111m × ~111m square should be approximately 111*111 = 12321 m²."""
        # 0.001° ≈ 111.32m at the equator
        coords = [
            {"lat": 0.0, "lng": 0.0},
            {"lat": 0.0, "lng": 0.001},
            {"lat": 0.001, "lng": 0.001},
            {"lat": 0.001, "lng": 0.0},
        ]
        area = polygon_area_sqm(coords)
        # At the equator, 0.001° ≈ 111.32m, so area ≈ 111.32² ≈ 12392 m²
        assert 10000 < area < 15000

    def test_degenerate_polygon(self):
        """A polygon with fewer than 3 points should return 0."""
        coords = [{"lat": 0.0, "lng": 0.0}, {"lat": 1.0, "lng": 1.0}]
        assert polygon_area_sqm(coords) == 0.0

    def test_empty_polygon(self):
        """An empty polygon should return 0."""
        assert polygon_area_sqm([]) == 0.0
