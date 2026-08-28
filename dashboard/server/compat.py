"""The REST shape Didi's backend published, served from this server's state.

`morerayad/AFRICA-RESQ` documented four endpoints for the frontend team to poll:

    GET /api/status      is the system up
    GET /api/detection   fire, smoke, survivor
    GET /api/risk        score and level
    GET /api/full        everything at once

Anything already written against those keeps working. What changed is where the answers
come from. In the upstream project each endpoint read `state.json`, a file a webcam loop
rewrote every frame, and the numbers in it came from a second set of engines. Here the
same four shapes are projected from the one live MissionState -- the same object the
websocket dashboard renders -- so a REST client and a websocket client can never show
two different risk scores for one incident.

This module is a projection and nothing else. It holds no state, makes no judgements and
computes no risk. If a number is wrong, it is wrong in `risk.py` or `state.py`, and it is
wrong identically on both transports.

Fields the upstream shape did not have are added, never removed or renamed: `zone`,
`in_view` and `last_seen_s` on a detection, `causes` on the risk block. Additive is safe
for a polling client; renaming is not.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# What the upstream `action` vocabulary becomes. The left column is this server's own
# recommendation urgency plus the situation; the right is the string an existing client
# is already switching on.
ACTION_HOLD = "HOLD_AND_REASSESS"
ACTION_APPROACH = "APPROACH_SURVIVOR"
ACTION_CONFIRM = "CLOSE_FOR_CONFIRMATION"
ACTION_LINK = "RESTORE_LINK"
ACTION_SWEEP = "CONTINUE_SWEEP"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hazard(snap: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    """The worst active hazard of one kind, or None if the board holds none."""
    live = [h for h in snap.get("hazards") or [] if h.get("kind") == kind]
    return max(live, key=lambda h: h.get("severity", 0.0)) if live else None


def _in_view(snap: Dict[str, Any], cls: str) -> float:
    """Best confidence for a class in the frame on screen right now. 0.0 if absent."""
    return max([d.get("conf", 0.0) for d in snap.get("detections") or []
                if d.get("cls") == cls], default=0.0)


def _vision(snap: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """One fire/smoke block.

    `detected` is what the server believes, not what the last frame happened to contain.
    A fire stays on the board until something contradicts it, so a rover that has turned
    away still reports the fire it drove past -- with `in_view` false and `last_seen_s`
    saying how stale the sighting is. Reporting only the current frame would tell a
    polling client the fire went out every time the camera looked elsewhere.
    """
    haz = _hazard(snap, kind)
    live = _in_view(snap, kind)
    if haz is None:
        return {"detected": False, "confidence": round(live, 3), "zone": None,
                "in_view": live > 0.0, "last_seen_s": None}
    age = snap.get("age_s") or 0.0
    return {
        "detected": True,
        # The confidence of the sighting that put it there, not a decayed guess.
        "confidence": round(live if live > 0.0 else (haz.get("conf") or 0.0), 3),
        "zone": haz.get("zone"),
        "in_view": live > 0.0,
        "last_seen_s": round(age, 1) if live > 0.0 else None,
    }


def _top_survivor(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    live = [s for s in snap.get("survivors") or [] if not s.get("stale")]
    return live[0] if live else None


def detection(snap: Dict[str, Any]) -> Dict[str, Any]:
    top = _top_survivor(snap)
    return {
        "fire": _vision(snap, "fire"),
        "smoke": _vision(snap, "smoke"),
        "survivor": {
            "detected": top is not None,
            "confidence": round(float(top["confidence"]), 3) if top else 0,
            # Upstream `location` was a survey cell string. It still is.
            "location": top["zone"] if top else None,
            "id": top["id"] if top else None,
            "band": top.get("band") if top else None,
        },
    }


def risk(snap: Dict[str, Any]) -> Dict[str, Any]:
    r = snap.get("risk") or {}
    if not r:
        return {"score": 0, "level": "LOW", "summary": "No rover reporting.",
                "entry_safe": False, "causes": []}
    return {
        "score": int(round(r.get("score", 0.0))),
        "level": r.get("band", "LOW"),
        "summary": r.get("summary"),
        "entry_safe": r.get("entry_safe", False),
        # The whole point of this server's risk engine: the score carries its reasons.
        "causes": [{"label": c["label"], "kind": c["kind"], "points": c["points"],
                    "reading": c["reading"], "threshold": c["threshold"]}
                   for c in r.get("causes") or []],
    }


def _action(snap: Dict[str, Any], top: Optional[Dict[str, Any]]) -> str:
    if snap.get("estop"):
        return ACTION_HOLD
    if not snap.get("connected"):
        return ACTION_LINK
    score = (snap.get("risk") or {}).get("score", 0.0)
    route = snap.get("route") or {}
    if score >= 90:
        return ACTION_HOLD
    if top is None:
        return ACTION_SWEEP
    if top.get("confidence", 0.0) >= 0.85 and route.get("reachable"):
        return ACTION_APPROACH
    return ACTION_CONFIRM


def recommendation(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    actions = snap.get("actions") or []
    if not actions:
        return None
    top = _top_survivor(snap)
    route = snap.get("route") or {}
    rec = route.get("recommended") or {}
    return {
        "action": _action(snap, top),
        "target": top["id"] if top else None,
        # Upstream sent (row, col) index pairs. This server speaks survey cells, the
        # same names the radio callouts and the map use, so the route is ["D1","D2",...].
        "route": rec.get("path") or [],
        "priority": top.get("tier") if top else None,
        "risk": int(round((snap.get("risk") or {}).get("score", 0.0))),
        "confidence": round(float(top["confidence"]), 3) if top else 0,
        "reasons": [a["text"] for a in actions],
        "because": [a["because"] for a in actions],
        "operator_override_allowed": True,
    }


def status(snap: Dict[str, Any]) -> Dict[str, Any]:
    """`status` stays "online" whenever the API answers, as it did upstream.

    Whether a rover is actually reporting is a different question, and it gets its own
    field rather than being folded into the one an existing client is already reading.
    """
    if not snap.get("connected"):
        rover = "link_lost" if snap.get("seq") else "waiting"
    else:
        rover = "connected"
    return {
        "status": "online",
        "timestamp": _now_iso(),
        "rover": rover,
        "mission_id": snap.get("mission_id"),
        "seq": snap.get("seq", 0),
        "age_s": snap.get("age_s"),
    }


def full(snap: Dict[str, Any]) -> Dict[str, Any]:
    det = detection(snap)
    top = _top_survivor(snap)
    route = (snap.get("route") or {}).get("recommended") or {}
    return {
        "fire": det["fire"],
        "smoke": det["smoke"],
        "survivor": det["survivor"],
        "risk": risk(snap),
        "priority": top.get("tier") if top else None,
        "route": route.get("path") or [],
        "recommendation": recommendation(snap),
        # Everything above is the upstream shape. Below is what this server knows and
        # the upstream one did not, for a client that wants it.
        "pose": snap.get("pose"),
        "hazards": [{"kind": h["kind"], "label": h["label"], "zone": h["zone"],
                     "severity": h["severity"]} for h in snap.get("hazards") or []],
        "survivors": [{"id": s["id"], "zone": s["zone"], "confidence": s["confidence"],
                       "tier": s.get("tier"), "rank": s.get("rank"), "stale": s.get("stale", False)}
                      for s in snap.get("survivors") or []],
        "atmosphere": snap.get("atmosphere"),
        "connected": snap.get("connected", False),
    }
