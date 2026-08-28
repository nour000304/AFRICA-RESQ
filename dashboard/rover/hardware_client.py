"""Skeleton rover client for real hardware.

Fill in the four read_* functions with your sensor code and this streams a valid frame to
the command server. Nothing else in the system needs to change: the dashboard, fusion,
risk engine and route planner cannot tell this apart from the simulator.

    python -m rover.hardware_client --url ws://command-laptop:8000/ws/rover

The one rule that is not negotiable: a sensor you could not read returns None. Never a
zero, never a last-known value, never a plausible default. The risk engine treats a
missing reading as a reason to raise the score and tell the operator the air is unknown;
a fabricated safe value would quietly tell them the opposite.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from urllib.parse import quote
from typing import Any, Dict, List, Optional

import websockets

HZ = 5.0
MISSION_ID = "RESQ-001"


# --------------------------------------------------------------------------- sensors

def read_pose() -> Dict[str, Any]:
    """Odometry, IMU heading, GPS if outdoors. Metres from the SW corner of the area."""
    return {"x": 0.0, "y": 0.0, "heading": 0.0}


def read_robot() -> Dict[str, Any]:
    """Battery, radio quality, drive state, tilt from the IMU."""
    return {"battery_pct": None, "link_quality": None, "status": "searching",
            "tilt_deg": None, "speed_mps": None}


def read_atmosphere() -> Dict[str, Optional[float]]:
    """Return None per field for any sensor that did not answer this cycle."""
    return {"temp_c": None, "humidity_pct": None, "co_ppm": None,
            "lel_pct": None, "o2_pct": None, "pm25_ugm3": None}


def read_ranges() -> Dict[str, Optional[float]]:
    """Ultrasonic / ToF clearances in metres. None for a sensor that timed out."""
    return {"front_m": None, "left_m": None, "right_m": None, "rear_m": None}


def read_detections() -> List[Dict[str, Any]]:
    """Your detector's output, boxes normalised 0..1 as [x, y, w, h].

    Keep track_id stable for the same object across frames -- without it the server
    cannot tell two people in one cell apart.
    """
    return []


def read_thermal() -> Optional[Dict[str, Any]]:
    """Thermal array. Return None if the board has no thermal sensor at all.

    `human_like` is your own classifier's score for the blob. Do not pre-filter by
    temperature; the server applies the human band and the hot-scene discount itself.
    """
    return {"available": False, "blobs": []}


def read_camera_jpeg() -> Optional[str]:
    """Optional base64 data URI. Return None to let the dashboard draw a sim view.

    Keep it small -- 320x240 at quality 60 is plenty at 5 Hz over a field radio.
    """
    return None


# ---------------------------------------------------------------------------- control

def on_command(cmd: Dict[str, Any]) -> None:
    """Act on the operator. estop is handled before anything else, always."""
    kind = cmd.get("cmd")
    if kind == "estop":
        stop_motors() if cmd.get("on", True) else release_motors()
    elif kind == "mode":
        set_mode(str(cmd.get("mode", "assisted")))
    elif kind == "drive":
        drive(float(cmd.get("throttle", 0.0)), float(cmd.get("steer", 0.0)))


def stop_motors() -> None: ...
def release_motors() -> None: ...
def set_mode(mode: str) -> None: ...
def drive(throttle: float, steer: float) -> None: ...


# ------------------------------------------------------------------------------- loop

def build_frame(seq: int) -> Dict[str, Any]:
    return {
        "mission_id": MISSION_ID,
        "seq": seq,
        "t": time.time(),
        "mode": "assisted",
        "pose": read_pose(),
        "robot": read_robot(),
        "atmosphere": read_atmosphere(),
        "detections": read_detections(),
        "thermal": read_thermal(),
        "ranges": read_ranges(),
        "frame_jpeg": read_camera_jpeg(),
    }


async def run(url: str) -> None:
    seq = 0
    while True:
        try:
            async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
                print("connected to %s" % url)

                async def listen() -> None:
                    async for raw in ws:
                        try:
                            on_command(json.loads(raw))
                        except Exception as exc:
                            print("bad command: %s" % exc)

                task = asyncio.ensure_future(listen())
                try:
                    while True:
                        await asyncio.sleep(1.0 / HZ)
                        seq += 1
                        await ws.send(json.dumps(build_frame(seq)))
                finally:
                    task.cancel()
        except Exception as exc:
            # The link dropping is normal in a disaster. Stop moving, then keep trying.
            stop_motors()
            print("link down (%s). retrying in 2 s" % exc)
            await asyncio.sleep(2.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="AFRICA RESQ rover client")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/rover")
    ap.add_argument("--token", default=os.getenv("RESQ_ROVER_TOKEN", ""),
                    help="shared secret if the server requires one "
                         "(defaults to $RESQ_ROVER_TOKEN)")
    args = ap.parse_args()
    if args.token:
        args.url += ("&" if "?" in args.url else "?") + "token=" + quote(args.token)
    try:
        asyncio.get_event_loop().run_until_complete(run(args.url))
    except KeyboardInterrupt:
        stop_motors()
        print("\nstopped")


if __name__ == "__main__":
    main()
