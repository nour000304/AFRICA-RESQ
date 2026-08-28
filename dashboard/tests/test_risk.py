"""The risk ledger. Its one inviolable rule: unknown never lowers the score."""
from __future__ import annotations

from server.risk import assess
from server.schemas import Atmosphere, Detection, Ranges, Robot

from conftest import CLEAN_AIR, OPEN_RANGES


def _assess(atmo=None, dets=None, ranges=None, robot=None, survivors=None):
    return assess(
        Atmosphere.parse(atmo or {}),
        [Detection.parse(d) for d in (dets or [])],
        Ranges.parse(ranges or {}),
        Robot.parse(robot or {}),
        survivors or [],
    )


def _keys(r):
    return {c["key"] for c in r["causes"]}


def test_a_blind_rover_scores_higher_than_a_clean_measured_scene():
    measured = _assess(CLEAN_AIR, ranges=OPEN_RANGES)
    blind = _assess({}, ranges={})
    assert blind["score"] > measured["score"]
    assert measured["score"] == 0.0


def test_every_unmeasured_sensor_becomes_an_unknown_cause():
    r = _assess({}, ranges={})
    assert {"lel_unknown", "co_unknown", "o2_unknown", "range_unknown"} <= _keys(r)
    assert all(c["points"] > 0 for c in r["causes"] if c["kind"] == "unknown")


def test_unknown_never_reduces_the_score():
    """Adding ignorance to a scene must never make it look safer."""
    known = _assess(CLEAN_AIR, ranges=OPEN_RANGES)
    partial = _assess(dict(CLEAN_AIR, o2_pct=None), ranges=OPEN_RANGES)
    assert partial["score"] >= known["score"]


def test_entry_is_never_declared_safe_while_a_sensor_is_blind():
    r = _assess(dict(CLEAN_AIR, co_ppm=None), ranges=OPEN_RANGES)
    assert r["entry_safe"] is False


def test_entry_can_be_safe_when_everything_reads_clean():
    assert _assess(CLEAN_AIR, ranges=OPEN_RANGES)["entry_safe"] is True


def test_published_thresholds_are_the_ones_reported():
    """10 % LEL evacuation, 35 ppm CO, 19.5 % oxygen. These are not tunable opinions."""
    lel = _assess(dict(CLEAN_AIR, lel_pct=12.0), ranges=OPEN_RANGES)
    assert "10%" in next(c for c in lel["causes"] if c["key"] == "lel")["threshold"]
    co = _assess(dict(CLEAN_AIR, co_ppm=120.0), ranges=OPEN_RANGES)
    assert "35" in next(c for c in co["causes"] if c["key"] == "co")["threshold"]
    o2 = _assess(dict(CLEAN_AIR, o2_pct=18.0), ranges=OPEN_RANGES)
    assert "19.5" in next(c for c in o2["causes"] if c["key"] == "o2")["threshold"]


def test_oxygen_is_dangerous_in_both_directions():
    assert "o2" in _keys(_assess(dict(CLEAN_AIR, o2_pct=17.0), ranges=OPEN_RANGES))
    assert "o2_rich" in _keys(_assess(dict(CLEAN_AIR, o2_pct=25.0), ranges=OPEN_RANGES))


def test_fire_below_the_acting_threshold_is_not_scored():
    quiet = _assess(CLEAN_AIR, [{"cls": "fire", "conf": 0.20}], OPEN_RANGES)
    loud = _assess(CLEAN_AIR, [{"cls": "fire", "conf": 0.90}], OPEN_RANGES)
    assert "fire" not in _keys(quiet)
    assert "fire" in _keys(loud)


def test_a_survivor_is_urgency_not_hazard():
    """A person in there is a reason to go in, not a reason the air is worse."""
    r = _assess(CLEAN_AIR, ranges=OPEN_RANGES,
                survivors=[{"id": "A", "zone": "C3", "confidence": 0.9}])
    urgency = [c for c in r["causes"] if c["kind"] == "urgency"]
    assert urgency and r["urgency_points"] > 0
    assert r["hazard_points"] == 0.0


def test_score_is_capped_at_one_hundred():
    r = _assess({"temp_c": 200.0, "co_ppm": 5000.0, "lel_pct": 90.0, "o2_pct": 5.0,
                 "pm25_ugm3": 5000.0},
                [{"cls": "fire", "conf": 0.99}, {"cls": "smoke", "conf": 0.99}],
                {"front_m": 0.1},
                {"tilt_deg": 40.0, "battery_pct": 2.0, "link_quality": 0.05},
                [{"id": "A", "zone": "C3", "confidence": 0.99}])
    assert r["score"] == 100.0
    assert r["band"] == "CRITICAL"


def test_bands_follow_the_score():
    assert _assess(CLEAN_AIR, ranges=OPEN_RANGES)["band"] == "LOW"
    assert _assess({}, ranges={})["band"] in {"MEDIUM", "HIGH"}


def test_causes_are_ordered_biggest_first():
    r = _assess({}, [{"cls": "fire", "conf": 0.9}], {})
    points = [c["points"] for c in r["causes"]]
    assert points == sorted(points, reverse=True)


def test_every_cause_carries_its_reading_and_limit():
    """The meter is the explanation; a cause with no reading explains nothing."""
    r = _assess({"lel_pct": 12.0, "co_ppm": 120.0}, [{"cls": "fire", "conf": 0.9}], {})
    for c in r["causes"]:
        assert c["reading"] and c["threshold"], c
