"""Rescue priority.

When more than one survivor is on the board, someone has to be reached first. The
ranking is a weighted sum of four things a commander would weigh out loud, and each
survivor carries the breakdown so the order can be challenged.
"""
from __future__ import annotations

from typing import Any, Dict, List

W_CONFIDENCE = 46      # how sure are we a person is there
W_DANGER = 24          # how fast is their situation getting worse
W_ACCESS = 18          # can we actually get to them
W_FRESHNESS = 12       # how recently did we see them


def score_survivor(s: Dict[str, Any], route: Dict[str, Any], local_risk: float,
                   age_s: float) -> Dict[str, Any]:
    conf = max(0.0, min(1.0, float(s.get("confidence", 0.0))))
    danger = max(0.0, min(1.0, local_risk / 100.0))
    if not route or not route.get("reachable"):
        access = 0.0
        access_note = "no route"
    else:
        rec = route["recommended"]
        access = max(0.0, min(1.0, 1.0 - rec["distance_m"] / 40.0))
        access_note = "%s, %.0f m" % (rec["name"], rec["distance_m"])
    freshness = max(0.0, min(1.0, 1.0 - age_s / 120.0))

    parts = [
        {"label": "Detection confidence", "value": round(conf * W_CONFIDENCE, 1),
         "detail": "%d%%" % round(conf * 100)},
        {"label": "Local danger", "value": round(danger * W_DANGER, 1),
         "detail": "zone risk %.0f" % local_risk},
        {"label": "Reachability", "value": round(access * W_ACCESS, 1), "detail": access_note},
        {"label": "Contact freshness", "value": round(freshness * W_FRESHNESS, 1),
         "detail": "seen %.0f s ago" % age_s},
    ]
    total = round(sum(p["value"] for p in parts), 1)
    tier = "CRITICAL" if total >= 75 else "HIGH" if total >= 55 else "MEDIUM" if total >= 35 else "LOW"
    return {"priority": total, "tier": tier, "priority_parts": parts}


def rank(survivors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(survivors, key=lambda s: s.get("priority", 0.0), reverse=True)
    for i, s in enumerate(ordered):
        s["rank"] = i + 1
    return ordered
