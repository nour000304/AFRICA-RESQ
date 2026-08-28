"""Multi-modal survivor confirmation.

A person-shaped box on a camera is not a survivor. A warm patch is not a survivor. The
job here is to combine independent observations into one confidence the operator can
defend, and to show every term that produced it.

Method: evidence is combined in log-odds. Each modality contributes a log likelihood
ratio, so agreement compounds and disagreement subtracts, and each term stays separately
reportable. A modality that did not report contributes exactly zero -- never a nudge in
either direction -- and is listed as missing evidence instead.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .schemas import Atmosphere, Detection, Thermal, ThermalBlob

PRIOR = 0.20            # the area is being searched because people are believed inside
LOGIT_CAP = 2.2         # no single modality may swing more than this on its own
HUMAN_BAND = (30.0, 40.0)   # plausible surface temperature of a living person, C


def _logit(p: float, cap: float = LOGIT_CAP) -> float:
    p = min(0.995, max(0.005, p))
    return max(-cap, min(cap, math.log(p / (1.0 - p))))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _iou(a: List[float], b: List[float]) -> float:
    ax, ay, aw, ah = a[0], a[1], a[2], a[3]
    bx, by, bw, bh = b[0], b[1], b[2], b[3]
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _thermal_contrast(ambient_c: Optional[float]) -> float:
    """How much a heat signature is worth in this environment.

    In a burning room at 55 C a human body is no longer the hottest thing in frame, so
    thermal evidence must be discounted rather than trusted at face value.
    """
    if ambient_c is None:
        return 0.6                      # unknown ambient: trust it, but not fully
    if ambient_c <= 28.0:
        return 1.0
    if ambient_c >= 45.0:
        return 0.15
    return 1.0 - 0.85 * (ambient_c - 28.0) / 17.0


def fuse_person(
    person: Detection,
    thermal: Thermal,
    atmosphere: Atmosphere,
    inside_search_area: bool = True,
) -> Dict[str, Any]:
    """Combine one person detection with whatever else saw the same place."""
    terms: List[Dict[str, Any]] = []
    missing: List[str] = []
    log_odds = _logit(PRIOR)
    terms.append({
        "source": "prior",
        "label": "Search-area prior",
        "detail": "%d%% base rate before evidence" % round(PRIOR * 100),
        "delta": _logit(PRIOR),
    })

    # --- Visual evidence -------------------------------------------------------
    visual = _logit(person.conf)
    log_odds += visual
    terms.append({
        "source": "rgb",
        "label": "Camera",
        "detail": "person %d%%" % round(person.conf * 100),
        "delta": visual,
    })

    # --- Thermal evidence ------------------------------------------------------
    match: Optional[ThermalBlob] = None
    if thermal.available and thermal.blobs:
        match = max(thermal.blobs, key=lambda b: _iou(person.bbox, b.bbox))
        if _iou(person.bbox, match.bbox) < 0.10:
            match = None
    if not thermal.available:
        missing.append("thermal")
        terms.append({
            "source": "thermal",
            "label": "Thermal",
            "detail": "sensor unavailable",
            "delta": 0.0,
        })
    elif match is None:
        # The array is working and sees no heat where the camera sees a person. That is
        # real evidence against a living survivor -- a mannequin, a poster, a corpse --
        # but the thermal array is narrower than the camera, so it is not proof.
        delta = -0.6
        log_odds += delta
        terms.append({
            "source": "thermal",
            "label": "Thermal",
            "detail": "no heat signature at this position",
            "delta": delta,
        })
    else:
        in_band = HUMAN_BAND[0] <= match.peak_c <= HUMAN_BAND[1]
        contrast = _thermal_contrast(atmosphere.temp_c)
        raw = _logit(match.human_like)
        if not in_band:
            raw = min(raw, 0.0) - 0.4       # hot metal or a fire, not a body
        delta = raw * contrast
        log_odds += delta
        detail = "peak %.1f C, human-like %d%%" % (match.peak_c, round(match.human_like * 100))
        if contrast < 0.7:
            detail += " (discounted, hot scene)"
        terms.append({"source": "thermal", "label": "Thermal", "detail": detail, "delta": delta})

    # --- Environmental plausibility -------------------------------------------
    if atmosphere.temp_c is None:
        missing.append("temperature")
    elif atmosphere.temp_c > 60.0:
        delta = -0.7
        log_odds += delta
        terms.append({
            "source": "environment",
            "label": "Environment",
            "detail": "%.0f C is not survivable at this position" % atmosphere.temp_c,
            "delta": delta,
        })

    # --- Spatial evidence ------------------------------------------------------
    if not inside_search_area:
        delta = -1.2
        log_odds += delta
        terms.append({
            "source": "spatial",
            "label": "Position",
            "detail": "outside the declared search area",
            "delta": delta,
        })

    confidence = _sigmoid(log_odds)
    return {
        "confidence": round(confidence, 4),
        "log_odds": round(log_odds, 4),
        "terms": [dict(t, delta=round(t["delta"], 4)) for t in terms],
        "missing_evidence": missing,
        "thermal_confirmed": match is not None,
        "corroborating_sources": sum(
            1 for t in terms if t["delta"] > 0.3 and t["source"] != "prior"
        ),
    }


def confidence_band(c: float) -> str:
    if c >= 0.85:
        return "confirmed"
    if c >= 0.60:
        return "probable"
    if c >= 0.35:
        return "possible"
    return "weak"
