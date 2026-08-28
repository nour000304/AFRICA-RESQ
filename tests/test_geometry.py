"""Putting a box on a camera onto the map."""
from __future__ import annotations

import math

from server import geometry, grid


def test_a_bigger_box_is_closer():
    near = geometry.range_from_box([0.4, 0.1, 0.2, 0.80], "person")
    far = geometry.range_from_box([0.4, 0.4, 0.05, 0.10], "person")
    assert near < far


def test_range_is_clamped_to_a_believable_window():
    assert geometry.range_from_box([0, 0, 1, 1.0], "person") >= geometry.MIN_RANGE_M
    assert geometry.range_from_box([0, 0, 0.01, 0.0001], "person") <= geometry.MAX_RANGE_M


def test_bearing_is_zero_dead_ahead_and_positive_to_the_left():
    assert abs(geometry.bearing_from_box([0.45, 0.3, 0.10, 0.4])) < 1e-9
    assert geometry.bearing_from_box([0.05, 0.3, 0.10, 0.4]) > 0     # left of frame
    assert geometry.bearing_from_box([0.85, 0.3, 0.10, 0.4]) < 0     # right of frame


def test_object_height_changes_the_range_estimate():
    """Smoke is assumed taller than a person, so the same box means it is further off."""
    box = [0.4, 0.2, 0.2, 0.4]
    assert (geometry.range_from_box(box, "smoke")
            > geometry.range_from_box(box, "person")
            > geometry.range_from_box(box, "debris"))


def test_projection_places_the_object_ahead_of_the_rover_not_on_it():
    fix = geometry.project(10.5, 1.5, 90.0, [0.45, 0.3, 0.10, 0.4], "person")
    assert fix["y"] > 1.5                       # heading 90 is north
    assert abs(fix["x"] - 10.5) < 0.5
    # The fix sits exactly range_m away from the rover, along the reported bearing.
    assert abs(math.hypot(fix["x"] - 10.5, fix["y"] - 1.5) - fix["range_m"]) < 0.1


def test_heading_rotates_the_fix():
    box = [0.45, 0.3, 0.10, 0.4]
    east = geometry.project(10.0, 10.0, 0.0, box)
    north = geometry.project(10.0, 10.0, 90.0, box)
    assert east["x"] > 10.0 and abs(east["y"] - 10.0) < 0.5
    assert north["y"] > 10.0 and abs(north["x"] - 10.0) < 0.5


def test_the_survivor_gets_its_own_cell_not_the_rovers():
    """The README's claim: 'not near the rover'."""
    fix = geometry.project(*grid.center_of("A1"), 90.0, [0.45, 0.1, 0.10, 0.15], "person")
    assert grid.zone_of(fix["x"], fix["y"]) != "A1"
