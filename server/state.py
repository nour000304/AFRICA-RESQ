"""Mission memory.

A rover frame is a snapshot; a rescue is a story. This module keeps what the operator
needs to remember between frames -- survivor tracks, where hazards were last seen, which
cells have been swept -- and turns each incoming frame into the single MissionState
object the dashboard renders.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import geo, geometry, grid, priority, pathing
from .fusion import confidence_band, fuse_person
from .risk import assess
from .schemas import RoverFrame

SURVIVOR_TTL_S = 90.0        # a track with no new evidence for this long goes stale
PROMOTE_AT = 0.30            # below this a contact is logged, not carried as a survivor
REACQUIRE_M = 5.0            # a fix this far from the old one is a new sighting, not drift
HAZARD_TTL_S = 120.0
# A gas reading is a point sample taken as the rover drove past. It ages out quickly,
# because "there was 300 ppm here a minute ago" is not the same claim as "there is a
# fire here". A fire stays on the board until something contradicts it.
HAZARD_TTL_BY_KIND = {"gas": 45.0, "co": 45.0, "heat": 60.0}
HAZARD_LOG_EVERY_S = 30.0
STALE_LINK_S = 4.0           # no frame for this long and the link is presumed lost


def _grid_block() -> Dict[str, Any]:
    """The survey grid, plus where it was surveyed.

    The dashboard draws cells and the radio calls cells; neither needs a coordinate. The
    anchor rides along so a client that has to leave the grid -- routing an ambulance,
    naming a shelter -- can, without every other layer learning about GPS. It is
    configuration, so it is here whether or not a rover is reporting.
    """
    corner = geo.latlon_of(0.0, 0.0)
    far = geo.latlon_of(grid.WIDTH_M, grid.HEIGHT_M)
    return {
        "cols": list(grid.COLS), "rows": grid.ROWS, "cell_m": grid.CELL_M,
        "width_m": grid.WIDTH_M, "height_m": grid.HEIGHT_M,
        "anchor": geo.anchor(),
        "sw": {"lat": corner[0], "lon": corner[1]},
        "ne": {"lat": far[0], "lon": far[1]},
    }


class Mission:
    def __init__(self, mission_id: str = "RESQ-001") -> None:
        self.mission_id = mission_id
        self.started_at = time.time()
        self.frame: Optional[RoverFrame] = None
        self.last_frame_at: float = 0.0
        self.seq = 0
        self.survivors: Dict[str, Dict[str, Any]] = {}
        self.hazards: Dict[str, Dict[str, Any]] = {}
        self.swept: Dict[str, float] = {}
        self.track: List[Dict[str, float]] = []
        self.events: List[Dict[str, Any]] = []
        self.estop = False
        self.operator_mode: Optional[str] = None
        self.noted_contacts: set = set()
        self.noted_hazards: Dict[str, float] = {}

        # Optional. Anything with a record_frame(frame) method -- server/recorder.py has
        # the one this server uses. Left as None the mission behaves exactly as it did
        # before there was a ledger, which is what every test that does not care about
        # recording gets.
        self.recorder: Optional[Any] = None

    # -- event log -----------------------------------------------------------
    def log(self, level: str, text: str) -> None:
        if self.events and self.events[-1]["text"] == text:
            return
        self.events.append({
            "t": time.time(), "mission_t": time.time() - self.started_at,
            "level": level, "text": text,
        })
        del self.events[:-60]

    # -- ingest --------------------------------------------------------------
    def ingest(self, frame: RoverFrame) -> None:
        now = time.time()
        self.frame = frame
        self.last_frame_at = now
        self.seq = frame.seq
        if frame.mission_id:
            self.mission_id = frame.mission_id

        zone = frame.pose.zone if frame.pose.zone != "--" else grid.zone_of(frame.pose.x, frame.pose.y)
        frame.pose.zone = zone
        self.swept[zone] = now
        self.track.append({"x": frame.pose.x, "y": frame.pose.y})
        del self.track[:-400]

        self._update_survivors(frame, zone, now)
        self._update_hazards(frame, zone, now)

        # Every route a frame can take into this server passes through here, so this is
        # the one place recording has to be wired for the record to be complete.
        if self.recorder is not None:
            self.recorder.record_frame(frame)

    def _update_survivors(self, frame: RoverFrame, zone: str, now: float) -> None:
        people = [d for d in frame.detections if d.cls == "person"]
        for det in people:
            fused = fuse_person(det, frame.thermal, frame.atmosphere, inside_search_area=True)
            key = det.track_id or zone
            prev = self.survivors.get(key)

            if prev is None and fused["confidence"] < PROMOTE_AT:
                if key not in self.noted_contacts:
                    self.noted_contacts.add(key)
                    self.log("info", "Unconfirmed contact ahead of %s at %d%%. Watching."
                             % (zone, round(fused["confidence"] * 100)))
                continue

            # Where the person is, not where the rover is.
            fix = geometry.project(frame.pose.x, frame.pose.y, frame.pose.heading, det.bbox)
            fix["x"] = min(grid.WIDTH_M - 0.1, max(0.1, fix["x"]))
            fix["y"] = min(grid.HEIGHT_M - 0.1, max(0.1, fix["y"]))
            if prev is not None:
                drift = ((fix["x"] - prev["x"]) ** 2 + (fix["y"] - prev["y"]) ** 2) ** 0.5
                if drift < REACQUIRE_M:
                    # A trapped person does not move. Hold the first fix and let repeat
                    # sightings pull it in slowly rather than chase every frame.
                    fix["x"] = prev["x"] * 0.85 + fix["x"] * 0.15
                    fix["y"] = prev["y"] * 0.85 + fix["y"] * 0.15
            at_zone = grid.zone_of(fix["x"], fix["y"])

            record = {
                "id": prev["id"] if prev else chr(65 + len(self.survivors)),
                "key": key,
                "zone": at_zone,
                "x": round(fix["x"], 2), "y": round(fix["y"], 2),
                "range_m": fix["range_m"], "bearing_deg": fix["bearing_deg"],
                "seen_from": zone,
                "confidence": fused["confidence"],
                "band": confidence_band(fused["confidence"]),
                "terms": fused["terms"],
                "missing_evidence": fused["missing_evidence"],
                "thermal_confirmed": fused["thermal_confirmed"],
                "corroborating_sources": fused["corroborating_sources"],
                "bbox": det.bbox,
                "last_seen": now,
                "first_seen": prev["first_seen"] if prev else now,
            }
            if prev is None:
                self.log("alert", "Possible survivor in %s, %d%% confidence, %.1f m ahead of %s."
                         % (at_zone, round(fused["confidence"] * 100), fix["range_m"], zone))
            elif fused["confidence"] >= 0.85 > prev["confidence"]:
                self.log("critical", "Survivor %s confirmed in %s at %d%%."
                         % (record["id"], at_zone, round(fused["confidence"] * 100)))
            self.survivors[key] = record

        for key, s in list(self.survivors.items()):
            s["stale"] = (now - s["last_seen"]) > SURVIVOR_TTL_S

    def _update_hazards(self, frame: RoverFrame, zone: str, now: float) -> None:
        # A hazard the camera saw belongs where it is, not where the rover is standing.
        # A hazard the gas sensor measured belongs at the rover, because that is the only
        # place it was actually sampled.
        found: List[tuple] = []
        for d in frame.detections:
            spec = None
            if d.cls == "fire" and d.conf > 0.4:
                spec = ("fire", "Fire", 40 + 60 * d.conf, 7.0, d.conf)
            elif d.cls == "smoke" and d.conf > 0.5:
                spec = ("smoke", "Smoke", 20 + 30 * d.conf, 6.0, d.conf)
            elif d.cls in ("debris", "obstacle") and d.conf > 0.5:
                spec = ("debris", "Debris", 25 + 25 * d.conf, 3.0, d.conf)
            if spec is None:
                continue
            fix = geometry.project(frame.pose.x, frame.pose.y, frame.pose.heading, d.bbox, d.cls)
            at = grid.zone_of(min(grid.WIDTH_M - 0.1, max(0.1, fix["x"])),
                              min(grid.HEIGHT_M - 0.1, max(0.1, fix["y"])))
            found.append(spec + (at,))
        a = frame.atmosphere
        if a.lel_pct is not None and a.lel_pct >= 10:
            found.append(("gas", "Combustible gas", 30 + 2.6 * min(25.0, a.lel_pct), 4.0, None, zone))
        if a.co_ppm is not None and a.co_ppm >= 200:
            found.append(("co", "Carbon monoxide", 25 + 0.09 * min(800.0, a.co_ppm), 4.0, None, zone))
        if a.temp_c is not None and a.temp_c >= 55:
            found.append(("heat", "Extreme heat", 30 + 1.2 * min(60.0, a.temp_c - 55), 5.0, None, zone))

        for kind, label, severity, reach, conf, at_zone in found:
            zone = at_zone
            key = "%s@%s" % (kind, zone)
            prev = self.hazards.get(key)
            # Log the hazard, not every cell it was measured in: driving through a gas
            # cloud must not push the survivor callout off the top of the log.
            if now - self.noted_hazards.get(kind, 0.0) > HAZARD_LOG_EVERY_S:
                self.noted_hazards[kind] = now
                self.log("warning", "%s detected in %s." % (label, zone))
            self.hazards[key] = {
                "key": key, "kind": kind, "label": label, "zone": zone,
                "severity": round(min(100.0, max(severity, prev["severity"] * 0.9 if prev else 0)), 1),
                "reach_m": reach, "last_seen": now,
                # The vision confidence behind the last sighting. None for a hazard the
                # camera never saw -- a gas reading is measured, not recognised.
                "conf": conf,
            }

        for key, h in list(self.hazards.items()):
            if now - h["last_seen"] > HAZARD_TTL_BY_KIND.get(h["kind"], HAZARD_TTL_S):
                del self.hazards[key]

    # -- projection ----------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        connected = self.frame is not None and (now - self.last_frame_at) < STALE_LINK_S
        if self.frame is None:
            return {
                "connected": False, "mission_id": self.mission_id,
                "mission_t": now - self.started_at, "events": self.events,
                "grid": _grid_block(),
            }

        f = self.frame
        hazards = [dict(h) for h in self.hazards.values()]
        field = pathing.hazard_field(hazards)

        survivors: List[Dict[str, Any]] = []
        for s in self.survivors.values():
            rec = dict(s)
            route = pathing.plan(f.pose.zone, s["zone"], hazards)
            rec["route"] = route
            rec.update(priority.score_survivor(
                s, route, field.get(s["zone"], 0.0), now - s["last_seen"]))
            survivors.append(rec)
        survivors = priority.rank(survivors)

        risk = assess(f.atmosphere, f.detections, f.ranges, f.robot,
                      [{"id": s["id"], "zone": s["zone"], "confidence": s["confidence"]}
                       for s in survivors if not s.get("stale")])

        target = survivors[0] if survivors else None
        route = target["route"] if target else None

        return {
            "connected": connected,
            "estop": self.estop,
            "mission_id": self.mission_id,
            "mission_t": now - self.started_at,
            "seq": self.seq,
            "age_s": round(now - self.last_frame_at, 2),
            "mode": self.operator_mode or f.mode,
            "pose": {"x": f.pose.x, "y": f.pose.y, "heading": f.pose.heading, "zone": f.pose.zone},
            "robot": {
                "battery_pct": f.robot.battery_pct, "link_quality": f.robot.link_quality,
                "status": "stopped" if self.estop else f.robot.status,
                "tilt_deg": f.robot.tilt_deg, "speed_mps": f.robot.speed_mps,
            },
            "atmosphere": {
                "temp_c": f.atmosphere.temp_c, "humidity_pct": f.atmosphere.humidity_pct,
                "co_ppm": f.atmosphere.co_ppm, "lel_pct": f.atmosphere.lel_pct,
                "o2_pct": f.atmosphere.o2_pct, "pm25_ugm3": f.atmosphere.pm25_ugm3,
                "unavailable": f.atmosphere.missing(),
            },
            "detections": [
                {"cls": d.cls, "conf": d.conf, "bbox": d.bbox, "track_id": d.track_id}
                for d in f.detections
            ],
            "thermal": {
                "available": f.thermal.available, "max_c": f.thermal.max_c,
                "blobs": [{"peak_c": b.peak_c, "bbox": b.bbox, "human_like": b.human_like}
                          for b in f.thermal.blobs],
            },
            "ranges": {"front_m": f.ranges.front_m, "left_m": f.ranges.left_m,
                       "right_m": f.ranges.right_m, "rear_m": f.ranges.rear_m},
            "frame_jpeg": f.frame_jpeg,
            "survivors": survivors,
            "hazards": hazards,
            "hazard_field": field,
            "swept": sorted(self.swept.keys()),
            "track": self.track[-200:],
            "risk": risk,
            "route": route,
            "actions": recommend(risk, survivors, route, f, connected, self.estop),
            "events": self.events[-24:],
            "grid": _grid_block(),
        }


def recommend(risk, survivors, route, frame: RoverFrame, connected: bool,
              estop: bool) -> List[Dict[str, Any]]:
    """What the operator should do next, in the order they should do it."""
    out: List[Dict[str, Any]] = []

    def add(urgency: str, text: str, because: str) -> None:
        out.append({"urgency": urgency, "text": text, "because": because})

    if estop:
        add("hold", "Clear the emergency stop to resume the sweep.",
            "The rover is held by operator command.")
        return out
    if not connected:
        add("critical", "Restore the radio link before sending anyone in.",
            "The rover stopped reporting; the picture on screen is not current.")
        return out

    live = [s for s in survivors if not s.get("stale")]
    if live:
        top = live[0]
        if top["confidence"] >= 0.85:
            add("critical", "Task the entry team to survivor %s in %s."
                % (top["id"], top["zone"]),
                "%d%% confidence from %d agreeing sources."
                % (round(top["confidence"] * 100), top["corroborating_sources"]))
        elif top["confidence"] >= 0.5:
            add("warning", "Hold the team and close on %s for a second look." % top["zone"],
                "%d%% confidence is not enough to commit a team."
                % round(top["confidence"] * 100))
        if top.get("missing_evidence"):
            add("warning", "Confirm %s by hand." % top["zone"],
                "No %s reading, so the fusion score rests on the camera alone."
                % ", ".join(top["missing_evidence"]))

    if route and route.get("reachable") and route.get("recommended"):
        rec = route["recommended"]
        if route.get("identical"):
            add("info", "Send them in on %s." % " - ".join(rec["path"]), route["reason"])
        else:
            add("info", "Send them in on %s (%s)." % (rec["name"], " - ".join(rec["path"])),
                route["reason"])
    elif route and not route.get("reachable"):
        add("critical", "No route to the survivor. Breach or wait for the way to clear.",
            route.get("reason", ""))

    for c in risk["causes"]:
        if c["kind"] == "hazard" and c["severity"] > 0.55:
            add("warning", _mitigation(c["key"]), "%s: %s (limit %s)."
                % (c["label"], c["reading"], c["threshold"]))
    if risk["unknown_points"] > 0:
        blind = [c["label"] for c in risk["causes"] if c["kind"] == "unknown"]
        add("warning", "Treat the atmosphere as unknown, not clear.",
            "%s. A sensor that is not reading is not a safe reading." % "; ".join(blind))

    if frame.robot.battery_pct is not None and frame.robot.battery_pct < 25:
        add("warning", "Plan the rover's return now.",
            "%.0f%% battery against a %.0f m trip back."
            % (frame.robot.battery_pct, (route or {}).get("recommended", {}).get("distance_m", 0)))

    if not out:
        add("info", "Continue the sweep.", "Nothing on the board needs a decision yet.")
    return out[:5]


def _mitigation(key: str) -> str:
    return {
        "fire": "Charge a line before the team enters.",
        "smoke": "Move on thermal, not sight.",
        "lel": "Stop hot work and ventilate before entry.",
        "co": "SCBA on. Do not enter on filters.",
        "o2": "SCBA on. The air will not support work.",
        "o2_rich": "No sparks, no tools. The air is oxygen enriched.",
        "heat": "Cut the entry team's work cycle short.",
        "clearance": "Take the small-frame kit; a stretcher will not pass.",
        "tilt": "Shore the floor before anyone stands on it.",
        "particulate": "Respiratory protection on.",
    }.get(key, "Reduce exposure in this zone.")
