"""Turning a box on a camera into a place on the map.

A detection is worth much less if the only answer to "where?" is "somewhere near the
rover". Range comes from apparent height -- a 1.7 m person filling a known fraction of a
frame with a known vertical field of view is a solvable triangle -- and bearing comes
from how far off-centre the box sits. Both are estimates and are reported as such.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

HFOV_DEG = 62.0          # typical Pi camera module, horizontal
VFOV_DEG = 48.8          # same module, vertical
PERSON_H_M = 1.70
MIN_RANGE_M, MAX_RANGE_M = 0.6, 14.0

# Assumed real-world height of each thing we detect, in metres. Rough, but the ranking
# of "close" against "far" is what the map needs, not survey accuracy.
OBJECT_H_M = {
    "person": PERSON_H_M,
    "fire": 1.20,
    "smoke": 2.60,
    "debris": 0.80,
    "obstacle": 0.80,
}


def range_from_box(bbox: List[float], cls: str = "person") -> float:
    """Distance to an object of known typical height from the height of its box."""
    h = max(1e-3, bbox[3])
    half = math.tan(math.radians(VFOV_DEG / 2.0))
    obj_h = OBJECT_H_M.get(cls, PERSON_H_M)
    return max(MIN_RANGE_M, min(MAX_RANGE_M, obj_h / (2.0 * h * half)))


def bearing_from_box(bbox: List[float]) -> float:
    """Degrees off the rover's nose, positive to the left of frame centre."""
    cx = bbox[0] + bbox[2] / 2.0
    return -(cx - 0.5) * HFOV_DEG


def project(pose_x: float, pose_y: float, heading_deg: float, bbox: List[float],
            cls: str = "person") -> Dict[str, float]:
    rng = range_from_box(bbox, cls)
    bearing = bearing_from_box(bbox)
    theta = math.radians(heading_deg + bearing)
    return {
        "x": pose_x + rng * math.cos(theta),
        "y": pose_y + rng * math.sin(theta),
        "range_m": round(rng, 1),
        "bearing_deg": round(bearing, 1),
    }
