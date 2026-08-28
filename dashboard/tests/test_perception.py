"""Camera perception: the conversions between YOLO's world and the wire contract.

These run without ultralytics or torch. The arithmetic under test does not need a neural
network, and a suite that pulls 200 MB of wheels is a suite nobody runs.
"""
from __future__ import annotations

import numpy as np
import pytest

from rover.perception import CONTRACT_CLASSES, IOU_MATCH, TRACK_TTL_S, Detector, _iou, _Tracker

FRAME = np.zeros((480, 640, 3), np.uint8)


# ------------------------------------------------------------------ box conversion

def test_pixel_corners_become_normalised_left_top_width_height(fake_detector):
    """The conversion `server/geometry.py` depends on. Wrong units move the hazard."""
    d, model, Box = fake_detector()
    model.boxes = [Box([320, 120, 480, 360], 0.87, 0)]
    dets = d.detect(FRAME)
    assert dets[0]["bbox"] == [0.5, 0.25, 0.25, 0.5]


def test_the_contract_key_is_conf_not_confidence(fake_detector):
    """A dict carrying `confidence` parses to conf=0.0 and vanishes downstream."""
    d, model, Box = fake_detector()
    model.boxes = [Box([100, 100, 200, 200], 0.9, 0)]
    dets = d.detect(FRAME)
    assert "conf" in dets[0] and "confidence" not in dets[0]
    assert set(dets[0]) == {"cls", "conf", "bbox", "track_id"}


def test_a_box_running_off_the_edge_is_clamped_not_inverted(fake_detector):
    """A negative width would invert the range solution and put the hazard behind us."""
    d, model, Box = fake_detector()
    model.boxes = [Box([-40, 400, 100, 600], 0.8, 1)]
    dets = d.detect(FRAME)
    x, y, w, h = dets[0]["bbox"]
    assert x == 0.0 and w > 0 and h > 0
    assert x + w <= 1.0 and y + h <= 1.0


def test_a_zero_area_box_is_dropped(fake_detector):
    d, model, Box = fake_detector()
    model.boxes = [Box([300, 300, 300, 300], 0.9, 0)]
    assert d.detect(FRAME) == []


# -------------------------------------------------------------- class vocabulary

def test_classes_the_server_cannot_score_are_dropped(fake_detector):
    """COCO has 80 classes. A chair is not evidence; it is noise on a radio link."""
    d, model, Box = fake_detector()
    model.boxes = [Box([10, 10, 50, 50], 0.9, 2)]        # "chair", unmapped
    assert d.detect(FRAME) == []


def test_every_emitted_class_is_one_the_risk_engine_understands(fake_detector):
    d, model, Box = fake_detector()
    model.boxes = [Box([10, 10, 50, 50], 0.9, 0), Box([60, 60, 90, 90], 0.8, 1)]
    dets = d.detect(FRAME)
    assert len(dets) == 2
    assert all(x["cls"] in CONTRACT_CLASSES for x in dets)


def test_a_mapping_to_an_unscoreable_class_fails_at_load_not_at_runtime():
    with pytest.raises(ValueError, match="cannot score"):
        Detector(models=[("models/fire_smoke.pt", 0.3, {"fire": "flames"})])


def test_the_confidence_floor_is_the_models_own(fake_detector):
    d, model, Box = fake_detector(floor=0.30)
    model.boxes = [Box([10, 10, 50, 50], 0.10, 0)]
    assert d.detect(FRAME) == []


# --------------------------------------------------------------------- tracking

def test_iou_of_identical_and_disjoint_boxes():
    assert _iou([0, 0, 0.5, 0.5], [0, 0, 0.5, 0.5]) == 1.0
    assert _iou([0, 0, 0.2, 0.2], [0.8, 0.8, 0.2, 0.2]) == 0.0


def test_a_drifting_object_keeps_its_identity(fake_detector):
    """Contract rule 3. Without it two people in one cell become one survivor."""
    d, model, Box = fake_detector()
    model.boxes = [Box([300, 200, 400, 400], 0.9, 0)]
    first = d.detect(FRAME)[0]["track_id"]
    model.boxes = [Box([308, 205, 408, 405], 0.9, 0)]
    assert d.detect(FRAME)[0]["track_id"] == first


def test_a_second_object_gets_its_own_identity(fake_detector):
    d, model, Box = fake_detector()
    model.boxes = [Box([300, 200, 400, 400], 0.9, 0), Box([20, 20, 80, 80], 0.9, 0)]
    ids = {x["track_id"] for x in d.detect(FRAME)}
    assert len(ids) == 2


def test_identities_do_not_cross_classes():
    t = _Tracker()
    box = [0.4, 0.3, 0.2, 0.3]
    assert t.assign("fire", box, 100.0) != t.assign("smoke", box, 100.0)


def test_an_identity_is_retired_once_it_is_stale():
    t = _Tracker()
    box = [0.4, 0.3, 0.2, 0.3]
    first = t.assign("fire", box, 100.0)
    assert t.assign("fire", box, 100.0 + TRACK_TTL_S + 1) != first


def test_only_boxes_seen_this_frame_are_emitted(fake_detector):
    """An identity may outlive an occlusion. A bounding box may not -- that is invention."""
    d, model, Box = fake_detector()
    model.boxes = [Box([300, 200, 400, 400], 0.9, 0)]
    assert len(d.detect(FRAME)) == 1
    model.boxes = []
    assert d.detect(FRAME) == []


def test_boxes_too_far_apart_are_not_the_same_object():
    t = _Tracker()
    a = t.assign("fire", [0.0, 0.0, 0.2, 0.2], 100.0)
    b = t.assign("fire", [0.5, 0.5, 0.2, 0.2], 100.0)
    assert a != b
    assert _iou([0.0, 0.0, 0.2, 0.2], [0.5, 0.5, 0.2, 0.2]) < IOU_MATCH


# ------------------------------------------------------------------- resilience

def test_a_model_that_throws_does_not_take_the_telemetry_stream_down(fake_detector):
    """A rover that stops sending frames reads as a lost link. That is worse."""
    d, model, Box = fake_detector()

    def boom(*a, **k):
        raise RuntimeError("CUDA out of memory")

    d._loaded = [(type("M", (), {"names": {}, "__call__": staticmethod(boom)})(), 0.3, {})]
    assert d.detect(FRAME) == []
