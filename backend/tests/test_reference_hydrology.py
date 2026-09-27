"""Independent graph-walk oracle; not a substitute for surveyed field validation."""

import numpy as np
import pytest

from services.terrain import (
    d8_flow_direction,
    delineate_catchment,
    fill_depressions,
    flow_accumulation,
)


@pytest.mark.parametrize('seed', [3, 17, 42, 81])
def test_accumulation_and_catchment_match_independent_path_walk(seed):
    dem = np.random.default_rng(seed).uniform(0, 50, (9, 11))
    conditioned, _ = fill_depressions(dem)
    directions = d8_flow_direction(conditioned)
    offsets = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    oracle = np.zeros(dem.shape, dtype=int)
    paths = {}
    for origin in np.ndindex(dem.shape):
        path, cell = set(), origin
        while True:
            assert cell not in path, 'Flow routing contains a cycle'
            path.add(cell)
            oracle[cell] += 1
            direction = directions[cell]
            if direction < 0:
                break
            dr, dc = offsets[direction]
            cell = (cell[0] + dr, cell[1] + dc)
        paths[origin] = path
    np.testing.assert_array_equal(flow_accumulation(directions), oracle)
    outlet = np.unravel_index(np.argmax(oracle), dem.shape)
    expected = np.array([outlet in paths[origin] for origin in np.ndindex(dem.shape)]).reshape(dem.shape)
    np.testing.assert_array_equal(delineate_catchment(directions, *outlet), expected)
