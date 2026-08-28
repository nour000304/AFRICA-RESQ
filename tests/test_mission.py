"""Mission memory end to end: a frame in, a decision out."""
from __future__ import annotations

import time

from server import grid
from server.state import PROMOTE_AT, STALE_LINK_S, Mission

from conftest import CLEAN_AIR, OPEN_RANGES, blob, frame, person


def test_a_corroborated_person_becomes_a_survivor_on_the_board():
    m = Mission("TEST-001")
    m.ingest(frame(detections=[person(0.95)],
                   thermal={"available": True, "max_c": 36.4, "blobs": [blob()]},
                   atmosphere=CLEAN_AIR, ranges=OPEN_RANGES))
    snap = m.snapshot()
    assert len(snap["survivors"]) == 1
    s = snap["survivors"][0]
    assert s["confidence"] > PROMOTE_AT
    assert s["thermal_confirmed"] is True
    assert s["rank"] == 1


def test_a_weak_contact_is_logged_but_not_carried_as_a_survivor():
    """The README's 17-second beat: 'logged as an unconfirmed contact'."""
    m = Mission("TEST-001")
    m.ingest(frame(detections=[person(0.30)],
                   thermal={"available": True, "max_c": 24.0, "blobs": []}))
    snap = m.snapshot()
    assert snap["survivors"] == []
    assert any("contact" in e["text"].lower() for e in snap["events"])


def test_a_survivor_is_placed_at_its_own_cell_not_the_rovers():
    m = Mission("TEST-001")
    m.ingest(frame(zone="D1", x=10.5, y=1.5, heading=90.0,
                   detections=[person(0.95, bbox=[0.45, 0.30, 0.10, 0.20])],
                   thermal={"available": True, "max_c": 36.4,
                            "blobs": [blob(bbox=[0.45, 0.30, 0.10, 0.20])]},
                   atmosphere=CLEAN_AIR))
    s = m.snapshot()["survivors"][0]
    assert s["zone"] != "D1"
    assert s["range_m"] > 0


def test_two_tracked_people_stay_two_people():
    """Contract rule 3, at the level that matters: the board must not merge them."""
    m = Mission("TEST-001")
    m.ingest(frame(
        detections=[person(0.95, bbox=[0.20, 0.35, 0.12, 0.40], track_id="P1"),
                    person(0.92, bbox=[0.65, 0.35, 0.12, 0.40], track_id="P2")],
        thermal={"available": True, "max_c": 36.4,
                 "blobs": [blob(bbox=[0.20, 0.35, 0.12, 0.40]),
                           blob(bbox=[0.65, 0.35, 0.12, 0.40])]},
        atmosphere=CLEAN_AIR))
    assert len(m.snapshot()["survivors"]) == 2


def test_a_fire_lands_where_it_is_not_where_the_rover_stands():
    m = Mission("TEST-001")
    m.ingest(frame(zone="D1", x=10.5, y=1.5, heading=90.0,
                   detections=[{"cls": "fire", "conf": 0.9, "bbox": [0.45, 0.3, 0.2, 0.3]}]))
    hazards = m.snapshot()["hazards"]
    assert len(hazards) == 1
    assert hazards[0]["kind"] == "fire"
    assert hazards[0]["zone"] != "D1"


def test_a_gas_reading_lands_at_the_rover_because_that_is_where_it_was_sampled():
    m = Mission("TEST-001")
    m.ingest(frame(zone="D1", atmosphere={"lel_pct": 18.0}))
    gas = [h for h in m.snapshot()["hazards"] if h["kind"] == "gas"]
    assert gas and gas[0]["zone"] == "D1"


def test_a_hazard_the_camera_saw_records_the_confidence_behind_it():
    m = Mission("TEST-001")
    m.ingest(frame(detections=[{"cls": "fire", "conf": 0.83, "bbox": [0.4, 0.3, 0.2, 0.3]}]))
    fire = next(h for h in m.snapshot()["hazards"] if h["kind"] == "fire")
    assert fire["conf"] == 0.83


def test_a_hazard_the_camera_never_saw_has_no_confidence():
    """A gas reading is measured, not recognised. `conf` is None, never zero."""
    m = Mission("TEST-001")
    m.ingest(frame(atmosphere={"lel_pct": 18.0}))
    gas = next(h for h in m.snapshot()["hazards"] if h["kind"] == "gas")
    assert gas["conf"] is None


def test_a_blind_rover_is_told_to_treat_the_air_as_unknown():
    """The whole reason the null rule exists, asserted at the top of the stack."""
    m = Mission("TEST-001")
    m.ingest(frame(atmosphere={}, ranges={}))
    snap = m.snapshot()
    assert snap["risk"]["unknown_points"] > 0
    assert any("unknown" in a["text"].lower() for a in snap["actions"])


def test_a_measured_clean_scene_says_nothing_needs_a_decision():
    m = Mission("TEST-001")
    m.ingest(frame(atmosphere=CLEAN_AIR, ranges=OPEN_RANGES))
    snap = m.snapshot()
    assert snap["risk"]["score"] == 0.0
    assert snap["risk"]["entry_safe"] is True


def test_the_link_going_quiet_stops_the_screen_claiming_to_be_current():
    m = Mission("TEST-001")
    m.ingest(frame())
    assert m.snapshot()["connected"] is True
    m.last_frame_at = time.time() - (STALE_LINK_S + 1)
    snap = m.snapshot()
    assert snap["connected"] is False
    assert any("radio link" in a["text"].lower() for a in snap["actions"])


def test_an_estop_overrides_every_other_recommendation():
    m = Mission("TEST-001")
    m.ingest(frame(detections=[{"cls": "fire", "conf": 0.95, "bbox": [0.4, 0.3, 0.2, 0.3]}]))
    m.estop = True
    actions = m.snapshot()["actions"]
    assert len(actions) == 1, "a held rover gets one instruction, not a list of advice"
    assert "emergency stop" in actions[0]["text"].lower()


def test_swept_cells_accumulate_as_the_rover_moves():
    m = Mission("TEST-001")
    for i, zone in enumerate(("A1", "B1", "C1")):
        x, y = grid.center_of(zone)
        m.ingest(frame(seq=i + 1, zone=zone, x=x, y=y))
    assert set(m.snapshot()["swept"]) == {"A1", "B1", "C1"}


def test_a_malformed_frame_is_survivable():
    """A garbled radio frame must not end the mission."""
    m = Mission("TEST-001")
    m.ingest(frame())
    before = m.seq
    try:
        m.ingest(frame(seq=before + 1))
    except Exception as exc:                                   # pragma: no cover
        raise AssertionError("ingest raised: %s" % exc)
    assert m.seq == before + 1


def test_the_event_log_does_not_repeat_itself():
    m = Mission("TEST-001")
    m.log("info", "same thing")
    m.log("info", "same thing")
    assert sum(1 for e in m.events if e["text"] == "same thing") == 1


def test_no_rover_yet_renders_without_a_frame():
    snap = Mission("TEST-001").snapshot()
    assert snap["connected"] is False
    assert "grid" in snap
