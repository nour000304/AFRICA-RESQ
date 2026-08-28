"""The survey grid and the two routes."""
from __future__ import annotations

from server import grid, pathing


def _hazard(zone, severity=95.0, reach=7.0, kind="fire"):
    return {"kind": kind, "label": kind.title(), "zone": zone,
            "severity": severity, "reach_m": reach}


# ---------------------------------------------------------------------------- grid

def test_zone_names_round_trip():
    for zone in ("A1", "D3", "H6"):
        assert grid.zone_of(*grid.center_of(zone)) == zone


def test_out_of_bounds_clamps_to_an_edge_cell():
    assert grid.zone_of(-99.0, -99.0) == "A1"
    assert grid.zone_of(9999.0, 9999.0) == "H6"


def test_an_unknown_cell_name_does_not_crash():
    assert grid.index_of("") == (0, 0)
    assert grid.index_of("Z9") == (0, 0)


def test_routes_are_described_as_turns_not_diagonals():
    assert (1, 1) not in grid.neighbors(0, 0)


# ------------------------------------------------------------------------- pathing

def test_two_routes_are_always_offered():
    plan = pathing.plan("A1", "H1", [_hazard("D1")])
    assert plan["reachable"]
    assert plan["fastest"] and plan["safest"]
    assert plan["recommended"] in (plan["fastest"], plan["safest"])


def test_the_safest_route_is_never_more_dangerous_than_the_fastest():
    plan = pathing.plan("A1", "H1", [_hazard("D1"), _hazard("E1")])
    assert plan["safest"]["peak_risk"] <= plan["fastest"]["peak_risk"]


def test_an_impassable_cell_is_removed_from_the_safe_route():
    plan = pathing.plan("A1", "H1", [_hazard("D1", severity=100.0, reach=3.0)])
    assert "D1" not in plan["safest"]["path"]


def test_a_route_walled_off_completely_is_reported_unreachable():
    wall = [_hazard("%s%d" % (c, r), severity=100.0, reach=4.0)
            for c in "D" for r in range(1, grid.ROWS + 1)]
    plan = pathing.plan("A1", "H1", wall)
    assert plan["safest"] is None or "D" not in "".join(plan["safest"]["path"])


def test_a_route_always_starts_where_the_rover_is_and_ends_at_the_goal():
    plan = pathing.plan("B2", "F5", [])
    rec = plan["recommended"]
    assert rec["path"][0] == "B2" and rec["path"][-1] == "F5"


def test_with_no_hazards_both_routes_are_the_same_and_it_says_so():
    plan = pathing.plan("A1", "C1", [])
    assert plan["identical"] is True
    assert plan["chosen"] == "A"


def test_distance_is_reported_in_metres_of_grid():
    plan = pathing.plan("A1", "D1", [])
    assert plan["recommended"]["distance_m"] == 3 * grid.CELL_M


def test_hazard_severity_falls_off_with_distance():
    field = pathing.hazard_field([_hazard("D3", severity=100.0, reach=9.0)])
    assert field["D3"] > field["C3"] > field["A3"]
    assert field["A1"] == 0.0
