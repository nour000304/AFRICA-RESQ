"""Where the grid is on Earth.

The claims: the anchor is configuration and never a guess, the transform is invertible,
a bearing is a true bearing, and a coordinate outside the region is refused rather than
answered with the nearest shelter on another continent.
"""
from __future__ import annotations

import math

import pytest

from server import config, geo, grid


@pytest.fixture
def anchored(monkeypatch):
    """A known origin, grid north on true north, so the arithmetic is checkable by hand."""
    monkeypatch.setattr(config, "ORIGIN_LAT", 30.0444)
    monkeypatch.setattr(config, "ORIGIN_LON", 31.2357)
    monkeypatch.setattr(config, "GRID_BEARING", 0.0)


def test_the_origin_corner_is_the_configured_point(anchored):
    lat, lon = geo.latlon_of(0.0, 0.0)
    assert (round(lat, 9), round(lon, 9)) == (30.0444, 31.2357)


def test_north_in_the_grid_is_north_on_earth(anchored):
    """+y is the grid's north edge. With no grid bearing it must raise the latitude only."""
    lat, lon = geo.latlon_of(0.0, 111.32)          # 111.32 m = 0.001 deg of latitude
    assert lat == pytest.approx(30.0454, abs=1e-6)
    assert lon == pytest.approx(31.2357, abs=1e-9)


def test_east_in_the_grid_is_east_on_earth(anchored):
    lat, lon = geo.latlon_of(100.0, 0.0)
    assert lat == pytest.approx(30.0444, abs=1e-9)
    assert lon > 31.2357


def test_a_rotated_grid_sends_its_north_edge_where_it_was_laid_out(anchored, monkeypatch):
    """A grid laid out facing east: walking up its rows walks east, not north."""
    monkeypatch.setattr(config, "GRID_BEARING", 90.0)
    lat, lon = geo.latlon_of(0.0, 100.0)
    assert lat == pytest.approx(30.0444, abs=1e-9), "grid north must no longer raise latitude"
    assert lon > 31.2357, "it must now increase longitude instead"


def test_the_distance_between_two_cells_is_the_distance_on_the_ground(anchored):
    """A1 to H1 is seven cells of 3 m. On Earth it must still be 21 m."""
    a = geo.latlon_of_zone("A1")
    h = geo.latlon_of_zone("H1")
    assert geo.haversine_km(a[0], a[1], h[0], h[1]) * 1000 == pytest.approx(21.0, abs=0.1)


def test_a_cell_lands_where_the_grid_says_it_does(anchored):
    """The whole grid is 24 x 18 m, so no cell centre may be more than 30 m from the corner."""
    for zone in grid.all_zones():
        lat, lon = geo.latlon_of_zone(zone)
        assert geo.haversine_km(config.ORIGIN_LAT, config.ORIGIN_LON, lat, lon) * 1000 < 30.0


def test_bearing_is_measured_clockwise_from_true_north():
    assert geo.bearing_deg(30.0, 31.0, 31.0, 31.0) == pytest.approx(0.0, abs=0.01)   # due north
    assert geo.bearing_deg(0.0, 31.0, 0.0, 32.0) == pytest.approx(90.0, abs=0.01)    # due east
    assert geo.bearing_deg(31.0, 31.0, 30.0, 31.0) == pytest.approx(180.0, abs=0.01) # due south
    assert geo.bearing_deg(0.0, 32.0, 0.0, 31.0) == pytest.approx(270.0, abs=0.01)   # due west


def test_compass_point_is_something_you_can_say_over_a_radio():
    assert geo.compass_point(0.0) == "N"
    assert geo.compass_point(90.0) == "E"
    assert geo.compass_point(180.0) == "S"
    assert geo.compass_point(270.0) == "W"
    assert geo.compass_point(45.0) == "NE"
    assert geo.compass_point(360.0) == "N", "a full turn is still north"


def test_haversine_against_a_known_pair():
    """Cairo city centre to Cairo International Stadium: a shade under 8 km."""
    km = geo.haversine_km(30.0444, 31.2357, 30.069113, 31.312407)
    assert 7.5 < km < 8.2


def test_the_same_point_is_zero_away_from_itself():
    assert geo.haversine_km(30.0444, 31.2357, 30.0444, 31.2357) == pytest.approx(0.0, abs=1e-9)


def test_estimates_are_estimates_but_they_are_ordered():
    assert geo.walk_minutes(5.0) > geo.drive_minutes(5.0)
    assert geo.walk_minutes(0.0) == 0


def test_a_coordinate_outside_the_region_is_refused():
    assert geo.in_region(30.0, 31.0) is True
    assert geo.in_region(48.8566, 2.3522) is False, "Paris is not in the shelter dataset"
    assert geo.describe(48.8566, 2.3522)["valid"] is False
    assert geo.describe(30.0, 31.0)["valid"] is True


def test_a_missing_coordinate_is_not_a_valid_one():
    """Rule 1 of this codebase: absent is not zero, and it is certainly not the origin."""
    assert geo.in_region(None, 31.0) is False
    assert geo.in_region(30.0, None) is False
    assert geo.describe(None, None)["valid"] is False
