"""The explainable risk engine.

A number on its own ("risk 87") is not a decision an incident commander can act on or
defend. Every point in the score here comes from one named cause with its own reading,
threshold and weight, and the dashboard renders those causes as the shape of the meter.

Two kinds of cause are tracked separately and both feed the score, as the product brief
requires:
  hazard  -- the environment is dangerous to a person entering it
  urgency -- there is a reason to enter anyway (a survivor is in there)
A sensor that did not report becomes an `unknown` cause. Unknown never reduces risk.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import Atmosphere, Detection, Ranges, Robot

BANDS = (("LOW", 25), ("MEDIUM", 50), ("HIGH", 75), ("CRITICAL", 101))


def _ramp(value: float, lo: float, hi: float) -> float:
    """0 below lo, 1 above hi, linear between."""
    if hi == lo:
        return 1.0 if value >= hi else 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _cause(key, kind, label, weight, severity, reading, threshold):
    severity = max(0.0, min(1.0, severity))
    return {
        "key": key,
        "kind": kind,                 # hazard | urgency | unknown | platform
        "label": label,
        "weight": weight,
        "severity": round(severity, 3),
        "points": round(weight * severity, 1),
        "reading": reading,
        "threshold": threshold,
    }


def assess(
    atmosphere: Atmosphere,
    detections: List[Detection],
    ranges: Ranges,
    robot: Robot,
    survivors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    survivors = survivors or []
    causes: List[Dict[str, Any]] = []

    # ---- Fire and smoke, from vision ------------------------------------------
    fire = max([d.conf for d in detections if d.cls == "fire"], default=0.0)
    if fire > 0.35:
        causes.append(_cause(
            "fire", "hazard", "Fire in view", 26, _ramp(fire, 0.35, 0.85),
            "detected %d%%" % round(fire * 100), "any confirmed flame",
        ))
    smoke = max([d.conf for d in detections if d.cls == "smoke"], default=0.0)
    if smoke > 0.35:
        causes.append(_cause(
            "smoke", "hazard", "Smoke obscuring the route", 10, _ramp(smoke, 0.35, 0.9),
            "detected %d%%" % round(smoke * 100), "visibility loss",
        ))

    # ---- Atmosphere ------------------------------------------------------------
    if atmosphere.lel_pct is None:
        causes.append(_cause("lel_unknown", "unknown", "Combustible gas not measured", 12, 1.0,
                             "no reading", "sensor required before entry"))
    elif atmosphere.lel_pct >= 5:
        # 10 % LEL is the standard evacuation trigger; 25 % is an explosive atmosphere.
        causes.append(_cause("lel", "hazard", "Combustible gas", 24,
                             _ramp(atmosphere.lel_pct, 5, 25),
                             "%.0f%%\u00a0LEL" % atmosphere.lel_pct, "evacuate at 10%\u00a0LEL"))

    if atmosphere.co_ppm is None:
        causes.append(_cause("co_unknown", "unknown", "CO not measured", 10, 1.0,
                             "no reading", "sensor required before entry"))
    elif atmosphere.co_ppm >= 35:
        causes.append(_cause("co", "hazard", "Carbon monoxide", 20,
                             _ramp(atmosphere.co_ppm, 35, 400),
                             "%.0f\u00a0ppm" % atmosphere.co_ppm, "35\u00a0ppm exposure limit"))

    if atmosphere.o2_pct is None:
        causes.append(_cause("o2_unknown", "unknown", "Oxygen not measured", 8, 1.0,
                             "no reading", "sensor required before entry"))
    elif atmosphere.o2_pct < 19.5:
        causes.append(_cause("o2", "hazard", "Oxygen deficient", 18,
                             _ramp(19.5 - atmosphere.o2_pct, 0, 3.5),
                             "%.1f%%\u00a0O₂" % atmosphere.o2_pct, "19.5% minimum"))
    elif atmosphere.o2_pct > 23.5:
        causes.append(_cause("o2_rich", "hazard", "Oxygen enriched", 14,
                             _ramp(atmosphere.o2_pct - 23.5, 0, 3.0),
                             "%.1f%%\u00a0O₂" % atmosphere.o2_pct, "23.5% maximum"))

    if atmosphere.temp_c is not None and atmosphere.temp_c >= 38:
        causes.append(_cause("heat", "hazard", "Heat load", 12, _ramp(atmosphere.temp_c, 38, 70),
                             "%.0f\u00a0°C" % atmosphere.temp_c, "38\u00a0°C working limit"))

    if atmosphere.pm25_ugm3 is not None and atmosphere.pm25_ugm3 >= 150:
        causes.append(_cause("particulate", "hazard", "Particulate load", 8,
                             _ramp(atmosphere.pm25_ugm3, 150, 900),
                             "%.0f\u00a0µg/m³" % atmosphere.pm25_ugm3, "150\u00a0µg/m³ limit"))

    # ---- Mobility --------------------------------------------------------------
    clearances = [v for v in (ranges.front_m, ranges.left_m, ranges.right_m) if v is not None]
    if not clearances:
        causes.append(_cause("range_unknown", "unknown", "Obstacle sensing down", 8, 1.0,
                             "no reading", "clearance unknown"))
    else:
        tightest = min(clearances)
        if tightest < 1.2:
            causes.append(_cause("clearance", "hazard", "Restricted passage", 10,
                                 _ramp(1.2 - tightest, 0, 0.9),
                                 "%.1f\u00a0m clearance" % tightest, "1.2\u00a0m to pass a stretcher"))

    if robot.tilt_deg is not None and robot.tilt_deg >= 12:
        causes.append(_cause("tilt", "hazard", "Unstable footing", 10, _ramp(robot.tilt_deg, 12, 30),
                             "%.0f\u00b0 tilt" % robot.tilt_deg, "12\u00b0 limit"))

    # ---- Reason to go in anyway ------------------------------------------------
    for s in survivors:
        conf = float(s.get("confidence", 0.0))
        if conf >= 0.35:
            causes.append(_cause(
                "survivor:%s" % s.get("id", "?"), "urgency",
                "Survivor %s in %s" % (s.get("id", "?"), s.get("zone", "--")),
                22, _ramp(conf, 0.35, 0.9),
                "%d%% confidence" % round(conf * 100), "act above 35%",
            ))

    # ---- Platform condition ----------------------------------------------------
    if robot.battery_pct is not None and robot.battery_pct < 25:
        causes.append(_cause("battery", "platform", "Rover battery low", 10,
                             _ramp(25 - robot.battery_pct, 0, 20),
                             "%.0f%%" % robot.battery_pct, "25% return threshold"))
    if robot.link_quality is not None and robot.link_quality < 0.45:
        causes.append(_cause("link", "platform", "Radio link degrading", 10,
                             _ramp(0.45 - robot.link_quality, 0, 0.4),
                             "%d%% link" % round(robot.link_quality * 100), "45%"))

    causes.sort(key=lambda c: c["points"], reverse=True)
    score = min(100.0, sum(c["points"] for c in causes))
    band = next(name for name, ceiling in BANDS if score < ceiling)

    hazard_pts = sum(c["points"] for c in causes if c["kind"] == "hazard")
    return {
        "score": round(score, 1),
        "band": band,
        "causes": causes,
        "hazard_points": round(hazard_pts, 1),
        "urgency_points": round(sum(c["points"] for c in causes if c["kind"] == "urgency"), 1),
        "unknown_points": round(sum(c["points"] for c in causes if c["kind"] == "unknown"), 1),
        "entry_safe": hazard_pts < 20 and not any(c["kind"] == "unknown" for c in causes),
        "summary": _summary(causes, score, band),
    }


def _summary(causes: List[Dict[str, Any]], score: float, band: str) -> str:
    top = [c["label"] for c in causes[:3]]
    if not top:
        return "Nothing hazardous measured. Sensors all reporting."
    return "%s risk, %d of 100, driven by %s." % (band.capitalize(), round(score), ", ".join(top))
