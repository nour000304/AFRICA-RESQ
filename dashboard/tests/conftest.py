"""Builders for the objects the tests need.

Every helper defaults to *nothing measured*. A test that cares about a sensor says so
explicitly, which means no test can accidentally pass because a fixture quietly supplied
a plausible reading -- the exact failure this system is built to avoid.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import config                     # noqa: E402
from server.schemas import RoverFrame          # noqa: E402


@pytest.fixture(autouse=True)
def _record_into_a_tmpdir(tmp_path, monkeypatch):
    """No test writes a ledger into the working tree.

    The server records by default, which is the right default for a rescue board and the
    wrong one for a suite: without this every run would leave an africa_resq.db in the
    repository and each test would read the last one's rows.
    """
    monkeypatch.setattr(config, "RECORD_DIR", str(tmp_path / "record"))


def frame(
    detections: Optional[List[Dict[str, Any]]] = None,
    atmosphere: Optional[Dict[str, Any]] = None,
    thermal: Optional[Dict[str, Any]] = None,
    ranges: Optional[Dict[str, Any]] = None,
    robot: Optional[Dict[str, Any]] = None,
    zone: str = "D1",
    x: float = 10.5,
    y: float = 1.5,
    heading: float = 90.0,
    seq: int = 1,
) -> RoverFrame:
    return RoverFrame.parse({
        "mission_id": "TEST-001",
        "seq": seq,
        "t": 1_700_000_000.0 + seq,
        "mode": "assisted",
        "pose": {"x": x, "y": y, "heading": heading, "zone": zone},
        "robot": robot or {"status": "searching"},
        "atmosphere": atmosphere or {},
        "detections": detections or [],
        "thermal": thermal if thermal is not None else {"available": False, "blobs": []},
        "ranges": ranges or {},
    })


def person(conf: float = 0.9, bbox: Optional[List[float]] = None,
           track_id: str = "P1") -> Dict[str, Any]:
    return {"cls": "person", "conf": conf, "bbox": bbox or [0.44, 0.38, 0.17, 0.42],
            "track_id": track_id}


def blob(peak_c: float = 36.4, human_like: float = 0.95,
         bbox: Optional[List[float]] = None) -> Dict[str, Any]:
    return {"peak_c": peak_c, "human_like": human_like,
            "bbox": bbox or [0.45, 0.37, 0.16, 0.43]}


CLEAN_AIR = {"temp_c": 22.0, "humidity_pct": 40.0, "co_ppm": 2.0,
             "lel_pct": 0.0, "o2_pct": 20.9, "pm25_ugm3": 10.0}
OPEN_RANGES = {"front_m": 3.0, "left_m": 3.0, "right_m": 3.0, "rear_m": 3.0}


@pytest.fixture
def fake_detector():
    """A Detector wired to a stub model, so perception is testable without ultralytics.

    Importing ultralytics would pull in torch; the conversion arithmetic under test does
    not need either, and a test suite that needs a 200 MB dependency does not get run.
    """
    import numpy as np
    from rover.perception import Detector, _Tracker

    class Box:
        def __init__(self, xyxy, conf, cls):
            self.xyxy = [np.array(xyxy, dtype=float)]
            self.conf = [conf]
            self.cls = [cls]

    class Result:
        def __init__(self, boxes):
            self.boxes = boxes

        def plot(self):
            return np.zeros((480, 640, 3), np.uint8)

    class Model:
        names = {0: "fire", 1: "smoke", 2: "chair"}

        def __init__(self):
            self.boxes: List[Box] = []

        def __call__(self, frame, **kw):
            floor = kw.get("conf", 0.0)
            return [Result([b for b in self.boxes if b.conf[0] >= floor])]

    def build(mapping=None, floor=0.30):
        model = Model()
        d = Detector.__new__(Detector)
        d.imgsz, d.device, d._tracker = 416, "cpu", _Tracker()
        d._loaded = [(model, floor, mapping or {"fire": "fire", "smoke": "smoke"})]
        return d, model, Box

    return build
