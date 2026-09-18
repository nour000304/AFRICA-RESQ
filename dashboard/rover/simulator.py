"""Scripted rover for demos and for developing the dashboard without hardware.

It speaks the exact wire contract in server/schemas.py, so nothing downstream can tell
it from a real rover except the `sim` flag it sets honestly in every frame.

It is a small sensor model rather than a list of canned readings: the scene has ground
truth -- two people, a fire, a debris pile, all at fixed coordinates -- and each frame is
rendered from the rover's actual pose. A person far away produces a small box and a low
confidence; the same person at three metres produces a large box and a high one; the gas
and heat readings fall off with distance from the fire. That means the command server's
projection, fusion and route planning are being exercised for real, not fed answers.

    python -m rover.simulator                       # against a local server
    python -m rover.simulator --url ws://pi:8000/ws/rover --speed 2

Ten-step demo, on the clock:
    0 s   enters at A1 and sweeps east along row 1
   15 s   turns north at D1 and holds to observe
   17 s   camera picks up something person-shaped, far off
   22 s   thermal array finishes warming and finds a heat signature there
   27 s   fire in D3, directly between the rover and the contact; gas front arrives
   34 s   the direct route is now impassable; the planner offers the long way round
   40 s   rover takes the safe corridor east then north
   62 s   closes on the survivor, confidence rises with the range
   70 s   a second, partly buried contact appears to the west
   75 s   holds overwatch
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import math
import random
import time
from urllib.parse import quote
from typing import Any, Dict, List, Optional, Tuple

import websockets

HZ = 5.0
CELL = 3.0
COLS = "ABCDEFGH"
HFOV, VFOV = 62.0, 48.8

# --- ground truth --------------------------------------------------------------
SURVIVOR_1 = (10.5, 11.4)     # D4, trapped, upright, clear line of sight
SURVIVOR_2 = (5.2, 13.4)      # B5, partly buried: weak signature, unsure camera
FIRE = (9.6, 8.2)             # D3, squarely between the entry point and survivor 1
DEBRIS = (4.5, 7.4)           # B3, off to the west

# --- the drive -----------------------------------------------------------------
SWEEP: List[Tuple[float, float]] = [(1.5, 1.5), (10.5, 1.5)]
DETOUR: List[Tuple[float, float]] = [(10.5, 1.5), (13.5, 1.5), (13.5, 10.5), (13.0, 10.5)]

T_TURN, T_HOLD, T_MOVE, T_END = 15.0, 19.0, 40.0, 72.0


def zone_of(x: float, y: float) -> str:
    return "%s%d" % (COLS[min(7, max(0, int(x // CELL)))], min(5, max(0, int(y // CELL))) + 1)


def walk(path: List[Tuple[float, float]], travelled: float) -> Tuple[float, float, float, bool]:
    remaining = travelled
    for i in range(len(path) - 1):
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if remaining <= seg:
            t = remaining / seg if seg else 0.0
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t,
                    math.degrees(math.atan2(y1 - y0, x1 - x0)), False)
        remaining -= seg
    x, y = path[-1]
    px, py = path[-2] if len(path) > 1 else path[-1]
    return x, y, math.degrees(math.atan2(y - py, x - px)), True


def wrap(deg: float) -> float:
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


class Camera:
    """Turns a world position into the box a detector would draw around it."""

    ASPECT = {"person": 0.42, "fire": 0.85, "smoke": 1.25, "debris": 1.6}

    @staticmethod
    def view(obj: Tuple[float, float], height_m: float, pose: Tuple[float, float, float],
             cls: str) -> Optional[Dict[str, Any]]:
        px, py, ph = pose
        dx, dy = obj[0] - px, obj[1] - py
        rng = math.hypot(dx, dy)
        if rng < 0.4 or rng > 14.0:
            return None
        bearing = wrap(math.degrees(math.atan2(dy, dx)) - ph)
        if abs(bearing) > HFOV * 0.45:
            return None
        h = height_m / (2.0 * rng * math.tan(math.radians(VFOV / 2.0)))
        h = max(0.03, min(0.85, h))
        w = h * Camera.ASPECT.get(cls, 0.5)
        cx = 0.5 - bearing / HFOV
        top = max(0.02, min(0.94 - h, 0.60 - h * 0.55))
        return {"bbox": [round(max(0.0, cx - w / 2), 3), round(top, 3),
                         round(w, 3), round(h, 3)], "range": rng, "bearing": bearing}


class Scenario:
    SPEED = 0.95      # m/s

    def __init__(self) -> None:
        self.t0 = time.time()
        self.seq = 0
        self.travelled = 0.0
        self.phase = 0
        self.estop = False
        self.mode = "assisted"
        self.battery = 94.0

    def command(self, cmd: Dict[str, Any]) -> None:
        if cmd.get("cmd") == "estop":
            self.estop = bool(cmd.get("on", True))
        elif cmd.get("cmd") == "mode":
            self.mode = str(cmd.get("mode", self.mode))

    # -- pose ---------------------------------------------------------------
    def pose(self, el: float, dt: float) -> Tuple[float, float, float, bool]:
        if el < T_TURN:                                   # sweep east
            if not self.estop:
                self.travelled += self.SPEED * dt
            x, y, hd, _ = walk(SWEEP, self.travelled)
            return x, y, hd, not self.estop
        if el < T_HOLD:                                   # turn to face north
            x, y = SWEEP[-1]
            return x, y, 90.0 * (el - T_TURN) / (T_HOLD - T_TURN), False
        if el < T_MOVE:                                   # hold and observe
            x, y = SWEEP[-1]
            return x, y, 90.0, False
        if self.phase == 0:
            self.phase, self.travelled = 1, 0.0
        if not self.estop and el < T_END:
            self.travelled += self.SPEED * dt
        x, y, hd, done = walk(DETOUR, self.travelled)
        if el >= T_END or done:
            hd = math.degrees(math.atan2(SURVIVOR_1[1] - y, SURVIVOR_1[0] - x))
        return x, y, hd, (not self.estop and not done and el < T_END)

    # -- one frame ----------------------------------------------------------
    def frame(self, dt: float) -> Dict[str, Any]:
        el = time.time() - self.t0
        self.seq += 1
        x, y, heading, moving = self.pose(el, dt)
        self.battery = max(6.0, self.battery - dt * 0.055)
        pose = (x, y, heading)

        detections: List[Dict[str, Any]] = []
        thermal_blobs: List[Dict[str, Any]] = []

        # --- fire, and the atmosphere it drives -----------------------------
        fire_on = el > 27.0
        d_fire = math.hypot(FIRE[0] - x, FIRE[1] - y) if fire_on else 99.0
        ramp = min(1.0, (el - 27.0) / 7.0) if fire_on else 0.0
        near = ramp * 1.0 / (1.0 + (d_fire / 3.0) ** 1.8)

        atmosphere = {
            "temp_c": round(28.4 + 46.0 * near + 0.4 * math.sin(el / 7.0), 1),
            "humidity_pct": round(42 + 3 * math.sin(el / 11.0), 1),
            "co_ppm": None,               # no CO sensor fitted
            "lel_pct": round(0.4 + 26.0 * near, 1),
            "o2_pct": None,               # no oxygen sensor fitted
            "pm25_ugm3": round(16 + 780.0 * near + 4 * random.random(), 1),
        }

        if fire_on:
            v = Camera.view(FIRE, 1.2, pose, "fire")
            if v:
                detections.append({"cls": "fire", "conf": round(min(0.92, 0.5 + 0.45 * ramp), 2),
                                   "bbox": v["bbox"]})
                detections.append({"cls": "smoke", "conf": round(min(0.9, 0.45 + 0.5 * ramp), 2),
                                   "bbox": Camera.view(FIRE, 2.6, pose, "smoke")["bbox"]})
                thermal_blobs.append({"peak_c": round(190 + 40 * random.random(), 1),
                                      "bbox": v["bbox"], "human_like": 0.04})

        # --- debris ----------------------------------------------------------
        v = Camera.view(DEBRIS, 0.8, pose, "debris")
        if v and el > 6:
            detections.append({"cls": "debris", "conf": round(0.55 + 0.2 * (1 - v["range"] / 14), 2),
                               "bbox": v["bbox"]})

        # --- people ----------------------------------------------------------
        thermal_up = el > 22.0
        contacts = [("P1", SURVIVOR_1, 17.0, 1.00), ("P2", SURVIVOR_2, 70.0, 0.62)]
        for tid, pos, t_from, quality in contacts:
            if el < t_from:
                continue
            v = Camera.view(pos, 1.70, pose, "person")
            if not v:
                continue
            conf = 0.40 + 0.56 * (1.0 - min(1.0, v["range"] / 13.0))
            conf = max(0.30, min(0.95, conf * quality + 0.02 * (random.random() - 0.5)))
            detections.append({"cls": "person", "conf": round(conf, 2),
                               "bbox": v["bbox"], "track_id": tid})
            if thermal_up:
                warm = 36.2 if quality > 0.9 else 33.4
                # A person the camera is unsure about is usually one the thermal array is
                # unsure about too: partly buried, less skin showing, cooler surface.
                human = min(0.96, (0.62 + 0.34 * (1.0 - min(1.0, v["range"] / 13.0))) * quality + 0.3 * (quality > 0.9))
                thermal_blobs.append({
                    "peak_c": round(warm + 0.3 * math.sin(el / 2.0), 1),
                    "bbox": v["bbox"], "human_like": round(max(0.2, min(0.96, human)), 2),
                    "track_id": tid,
                })

        clearance = max(0.6, min(3.0, (d_fire if fire_on else 3.0) * 0.55))
        status = "stopped" if self.estop else ("searching" if moving else "holding")
        link = max(0.32, 0.97 - 0.035 * math.hypot(x - 1.5, y - 1.5))

        return {
            "mission_id": "RESQ-001",
            "seq": self.seq,
            "t": time.time(),
            "mode": self.mode,
            "sim": True,
            "pose": {"x": round(x, 2), "y": round(y, 2), "heading": round(wrap(heading), 1),
                     "zone": zone_of(x, y)},
            "robot": {
                "battery_pct": round(self.battery, 1),
                "link_quality": round(link, 2),
                "status": status,
                "tilt_deg": round(abs(2.6 * math.sin(el / 3.0)) + (7.0 if 44 < el < 52 else 0.0), 1),
                "speed_mps": round(self.SPEED if moving else 0.0, 2),
            },
            "atmosphere": atmosphere,
            "detections": detections,
            "thermal": ({"available": True,
                         "max_c": max([b["peak_c"] for b in thermal_blobs],
                                      default=round(atmosphere["temp_c"] + 1.5, 1)),
                         "min_c": round(atmosphere["temp_c"] - 4, 1),
                         "blobs": thermal_blobs}
                        if thermal_up else {"available": False, "blobs": []}),
            "ranges": {"front_m": round(clearance, 2), "left_m": round(clearance + 1.2, 2),
                       "right_m": round(clearance + 0.7, 2), "rear_m": 3.0},
            "notes": "simulated rover",
        }


async def run(url: str, speed: float) -> None:
    scenario = Scenario()
    while True:
        try:
            async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
                print("simulator connected to %s" % url)

                async def listen() -> None:
                    async for raw in ws:
                        try:
                            scenario.command(json.loads(raw))
                        except Exception:
                            pass

                task = asyncio.ensure_future(listen())
                last = time.time()
                try:
                    while True:
                        await asyncio.sleep(1.0 / HZ)
                        now = time.time()
                        dt = (now - last) * speed
                        last = now
                        await ws.send(json.dumps(scenario.frame(dt)))
                finally:
                    task.cancel()
        except Exception as exc:
            print("simulator: %s -- retrying in 2 s" % exc)
            await asyncio.sleep(2.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="AFRICA RESQ rover simulator")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/rover")
    ap.add_argument("--token", default=os.getenv("RESQ_ROVER_TOKEN", ""),
                    help="shared secret if the server requires one "
                         "(defaults to $RESQ_ROVER_TOKEN)")
    ap.add_argument("--speed", type=float, default=1.0, help="time multiplier for the script")
    args = ap.parse_args()
    if args.token:
        args.url += ("&" if "?" in args.url else "?") + "token=" + quote(args.token)
    if args.speed != 1.0:
        Scenario.SPEED *= args.speed
    try:
        asyncio.get_event_loop().run_until_complete(run(args.url, args.speed))
    except KeyboardInterrupt:
        print("\nsimulator stopped")


if __name__ == "__main__":
    main()
