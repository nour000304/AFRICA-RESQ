"""The REST shape Didi's backend published, projected from this server's state.

The point of these tests is backward compatibility. A client written against
morerayad/AFRICA-RESQ reads `fire.detected`, `risk.score`, `risk.level`,
`survivor.location`. If any of those keys or their types drift, that client breaks
silently -- it will read `None` and render "no fire" on a burning building.
"""
from __future__ import annotations

from server import compat
from server.state import Mission

from conftest import CLEAN_AIR, OPEN_RANGES, blob, frame, person


def _mission_with(**kw) -> dict:
    m = Mission("TEST-001")
    m.ingest(frame(**kw))
    return m.snapshot()


# ------------------------------------------------------------- upstream key shape

def test_detection_carries_the_upstream_keys_and_types():
    snap = _mission_with(detections=[{"cls": "fire", "conf": 0.9, "bbox": [0.4, 0.3, 0.2, 0.4]}])
    d = compat.detection(snap)
    assert set(d) >= {"fire", "smoke", "survivor"}
    for block in ("fire", "smoke"):
        assert isinstance(d[block]["detected"], bool)
        assert isinstance(d[block]["confidence"], (int, float))
    assert set(d["survivor"]) >= {"detected", "confidence", "location"}


def test_risk_reports_an_integer_score_and_a_level_string():
    r = compat.risk(_mission_with(atmosphere=CLEAN_AIR, ranges=OPEN_RANGES))
    assert isinstance(r["score"], int)
    assert r["level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_full_carries_every_upstream_top_level_key():
    snap = _mission_with()
    full = compat.full(snap)
    assert set(full) >= {"fire", "smoke", "survivor", "risk", "priority", "route",
                         "recommendation"}


def test_status_stays_online_whenever_the_api_answers():
    """Upstream `/api/status` meant 'the API is up'. It still does."""
    assert compat.status(_mission_with())["status"] == "online"
    assert compat.status(Mission("T").snapshot())["status"] == "online"


def test_whether_a_rover_is_reporting_is_its_own_field():
    assert compat.status(Mission("T").snapshot())["rover"] == "waiting"
    assert compat.status(_mission_with())["rover"] == "connected"


# ----------------------------------------------------------------- the semantics

def test_fire_detected_reflects_the_board_not_the_last_frame():
    """A rover that turns away has not put the fire out.

    Reporting only the current frame would tell a polling client the fire stops and
    starts every time the camera pans -- which is what the upstream 15-frame hold was
    trying to paper over.
    """
    m = Mission("TEST-001")
    m.ingest(frame(seq=1, detections=[{"cls": "fire", "conf": 0.9, "bbox": [0.4, 0.3, 0.2, 0.4]}]))
    seen = compat.detection(m.snapshot())["fire"]
    assert seen["detected"] is True and seen["in_view"] is True

    m.ingest(frame(seq=2, detections=[]))                    # camera looks elsewhere
    still = compat.detection(m.snapshot())["fire"]
    assert still["detected"] is True
    assert still["in_view"] is False
    assert still["confidence"] > 0, "the confidence of the last real sighting survives"


def test_a_scene_with_no_fire_reports_no_fire():
    d = compat.detection(_mission_with(atmosphere=CLEAN_AIR))
    assert d["fire"]["detected"] is False
    assert d["fire"]["confidence"] == 0
    assert d["fire"]["zone"] is None


def test_survivor_location_is_a_survey_cell():
    snap = _mission_with(
        detections=[person(0.95)],
        thermal={"available": True, "max_c": 36.4, "blobs": [blob()]},
        atmosphere=CLEAN_AIR)
    s = compat.detection(snap)["survivor"]
    assert s["detected"] is True
    assert isinstance(s["location"], str) and len(s["location"]) >= 2


def test_route_is_a_list_of_cells_not_index_pairs():
    """Upstream returned (row, col) tuples. This server speaks the radio's vocabulary."""
    snap = _mission_with(
        detections=[person(0.95)],
        thermal={"available": True, "max_c": 36.4, "blobs": [blob()]},
        atmosphere=CLEAN_AIR)
    route = compat.full(snap)["route"]
    assert all(isinstance(z, str) for z in route)


def test_the_risk_score_is_the_same_number_on_both_transports():
    """One engine, two shapes. A REST client and the dashboard cannot disagree."""
    snap = _mission_with(atmosphere={"co_ppm": 300.0}, ranges=OPEN_RANGES)
    assert compat.risk(snap)["score"] == int(round(snap["risk"]["score"]))
    assert compat.risk(snap)["level"] == snap["risk"]["band"]


def test_the_risk_block_carries_its_reasons():
    r = compat.risk(_mission_with(atmosphere={}, ranges={}))
    assert r["causes"], "a score with no causes is the thing this project refuses to ship"
    assert all({"label", "points", "reading"} <= set(c) for c in r["causes"])


def test_recommendation_uses_the_upstream_action_vocabulary():
    snap = _mission_with(atmosphere=CLEAN_AIR, ranges=OPEN_RANGES)
    rec = compat.recommendation(snap)
    assert rec["action"] in {compat.ACTION_HOLD, compat.ACTION_APPROACH,
                             compat.ACTION_CONFIRM, compat.ACTION_LINK, compat.ACTION_SWEEP}
    assert rec["operator_override_allowed"] is True


def test_an_estopped_rover_recommends_holding():
    m = Mission("TEST-001")
    m.ingest(frame())
    m.estop = True
    assert compat.recommendation(m.snapshot())["action"] == compat.ACTION_HOLD


# ------------------------------------------------------------------- degenerate

def test_no_rover_yet_does_not_crash_any_endpoint():
    snap = Mission("TEST-001").snapshot()
    assert compat.detection(snap)["fire"]["detected"] is False
    assert compat.risk(snap)["score"] == 0
    assert compat.recommendation(snap) is None
    assert compat.full(snap)["connected"] is False
