"""Streams a real camera into the command server as a rover.

    python -m rover.camera_client --url ws://127.0.0.1:8000/ws/rover --at D3 --heading 90

This is `hardware_client.py` with the one sensor we actually have filled in. It opens a
source, runs `rover/perception.py` over every frame, and pushes a valid RoverFrame. The
server cannot tell it from the simulator, which is the point of the contract.

`--source` is a camera index by default, and accepts a video file or a still image so
the perception chain can be driven with no hardware -- on a machine with no camera
permission, or in a demo that has to show the same fire twice. A recorded source is
never presented as a live one: it says so in the frame's notes, where the operator
reads it.

Everything this rover cannot measure is sent as null, every frame, on purpose:

    atmosphere   no gas, CO, O2 or particulate sensor is fitted
    ranges       no ultrasonic or ToF ring is fitted
    thermal      available: false -- there is no thermal array
    battery      not instrumented on a mains or USB-powered camera

The risk engine turns each of those into an `unknown` cause that raises the score and
tells the operator the air was never measured. That is the correct reading of a
camera-only rover, and it is the reason no plausible-looking default appears anywhere
below. A hardcoded 20.9 % oxygen would score as clean air on a live rescue board.

`--at` is a surveyed constant, not a sensor: it is where the camera was physically
installed and pointed. A rover that can drive should read odometry into `pose` instead.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import websockets

from server import grid
from .perception import Detector

MISSION_ID = os.getenv("RESQ_MISSION_ID", "RESQ-001")
REOPEN_AFTER = 10        # consecutive failed reads before the device is reacquired

_estop = False
_mode = "assisted"


def on_command(cmd: Dict[str, Any]) -> None:
    """A fixed camera has no motors, but the operator's stop must still be visible.

    Reporting `stopped` back is what closes the loop on the dashboard: pressing stop and
    seeing nothing change is indistinguishable from pressing stop on a rover that has
    stopped listening.
    """
    global _estop, _mode
    kind = cmd.get("cmd")
    if kind == "estop":
        _estop = bool(cmd.get("on", True))
        print("e-stop %s" % ("engaged" if _estop else "released"))
    elif kind == "mode":
        _mode = str(cmd.get("mode", "assisted"))
        print("mode -> %s" % _mode)


def encode_jpeg(frame: Any, width: int, quality: int) -> Optional[str]:
    """Base64 data URI of the annotated frame, small enough for a field radio."""
    import cv2

    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)))
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def build_frame(seq: int, pose: Dict[str, Any], detections: list,
                jpeg: Optional[str], live: bool = True) -> Dict[str, Any]:
    return {
        "mission_id": MISSION_ID,
        "seq": seq,
        "t": time.time(),
        "mode": _mode,
        "pose": pose,
        "robot": {
            "battery_pct": None,
            "link_quality": None,
            "status": "stopped" if _estop else "searching",
            "tilt_deg": None,
            "speed_mps": None,
        },
        # Not measured. Not "fine". See the module docstring.
        "atmosphere": {"temp_c": None, "humidity_pct": None, "co_ppm": None,
                       "lel_pct": None, "o2_pct": None, "pm25_ugm3": None},
        "detections": detections,
        "thermal": {"available": False, "blobs": []},
        "ranges": {"front_m": None, "left_m": None, "right_m": None, "rear_m": None},
        "frame_jpeg": jpeg,
        # A recording must never be presented as a live sensor. The operator reads this.
        "notes": ("camera-only rover: vision, no environmental sensors" if live
                  else "RECORDED SOURCE - not a live camera. Vision only."),
    }


class Source:
    """Where frames come from: a camera, a video file, or one still image.

    A file source exists so the perception chain can be exercised without hardware --
    on a laptop with no camera permission, in CI, or in a demo that has to show the same
    fire twice. A video loops; a still image repeats. Neither is pretending to be a live
    camera: the frames are real frames and the detector is the real detector, but nothing
    downstream should be told a recording is a live sensor, which is why `live` is
    reported and the client puts it in the frame's notes.
    """

    def __init__(self, spec: str) -> None:
        import cv2

        self.spec = spec
        self.live = spec.isdigit()
        self.still = None
        self._cap = None

        if self.live:
            self._cap = cv2.VideoCapture(int(spec))
            if not self._cap.isOpened():
                raise SystemExit(
                    "cannot open camera %s.\n"
                    "On macOS the terminal application needs camera access:\n"
                    "  System Settings > Privacy & Security > Camera\n"
                    "Or point --source at a video file or an image instead." % spec)
            return

        if not os.path.exists(spec):
            raise SystemExit("no such file: %s" % spec)

        still = cv2.imread(spec)
        if still is not None:
            self.still = still
            return

        self._cap = cv2.VideoCapture(spec)
        if not self._cap.isOpened():
            raise SystemExit("cannot read %s as a video or an image" % spec)

    def read(self):
        """(ok, frame). A file that ends rewinds; only a live camera can go dead."""
        if self.still is not None:
            return True, self.still
        ok, frame = self._cap.read()
        if not ok and not self.live:
            self._cap.set(0, 0)               # cv2.CAP_PROP_POS_FRAMES
            ok, frame = self._cap.read()
        return ok, frame

    def reopen(self) -> bool:
        """Try to reacquire the device after it stopped delivering frames.

        A laptop suspending, a lid closing, another application taking the camera: the
        device goes away and every read fails from then on, for ever. Without this the
        rover keeps its socket open while sending nothing, which the server reads as a
        lost link -- correct, but it never comes back on its own. A camera that browns
        out and returns should be picked up again, not require a restart in the field.
        """
        import cv2

        if self.still is not None:
            return True
        try:
            self._cap.release()
        except Exception:
            pass
        self._cap = cv2.VideoCapture(int(self.spec) if self.live else self.spec)
        return bool(self._cap.isOpened())

    def describe(self) -> str:
        if self.live:
            return "camera %s" % self.spec
        return "%s %s (looping)" % ("image" if self.still is not None else "video", self.spec)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()


async def run(url: str, args: argparse.Namespace) -> None:
    source = Source(str(args.source))
    print("source: %s" % source.describe())

    detector = Detector(imgsz=args.imgsz, device=args.device)

    cx, cy = grid.center_of(args.at)
    pose = {"x": round(cx, 2), "y": round(cy, 2),
            "heading": float(args.heading), "zone": args.at.upper()}
    print("streaming from %s (%.1f, %.1f) heading %.0f deg"
          % (pose["zone"], pose["x"], pose["y"], pose["heading"]))

    seq = 0
    try:
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

                    def capture():
                        """Read, detect and encode. Runs in a worker thread -- see below."""
                        ok, frame = source.read()
                        if not ok:
                            return None, None
                        dets = detector.detect(frame)
                        # The raw frame, not an annotated one. The dashboard draws the
                        # boxes from the detections the server holds, so the feed and the
                        # detection list cannot show different things.
                        return dets, (encode_jpeg(frame, args.jpeg_width, args.jpeg_quality)
                                      if not args.no_jpeg else None)

                    loop = asyncio.get_event_loop()
                    period = 1.0 / args.hz
                    next_at = loop.time()
                    misses = 0
                    try:
                        while True:
                            # Pace on a fixed schedule rather than sleeping a whole period
                            # between frames: reading a camera and running two models costs
                            # real time, and sleeping the full period on top of it means the
                            # rover always runs slower than the rate it was asked for.
                            next_at += period
                            delay = next_at - loop.time()
                            if delay > 0:
                                await asyncio.sleep(delay)
                            else:
                                # Behind schedule. Carry on from now rather than firing a
                                # burst of catch-up frames nobody asked for.
                                next_at = loop.time()

                            # In a worker thread, because both calls block for tens of
                            # milliseconds. On the event loop they would stall the command
                            # listener -- and the one command that must never wait behind an
                            # inference pass is the operator's emergency stop.
                            detections, jpeg = await loop.run_in_executor(None, capture)
                            if detections is None:
                                # A camera that stops reading is a dead sensor, not an
                                # empty scene. Say nothing rather than report no fire --
                                # but try to get the sensor back, with a widening gap so
                                # a device that is gone for good is not hammered.
                                misses += 1
                                if misses % REOPEN_AFTER == 0:
                                    back = await loop.run_in_executor(None, source.reopen)
                                    print("camera lost (%d frames). reopen: %s"
                                          % (misses, "ok" if back else "failed"))
                                    if not back:
                                        await asyncio.sleep(min(10.0, misses * period))
                                continue
                            misses = 0

                            seq += 1
                            await ws.send(json.dumps(
                                build_frame(seq, pose, detections, jpeg, source.live)))

                            if detections and args.verbose:
                                print(" ".join("%s %.2f" % (d["cls"], d["conf"])
                                               for d in detections))
                    finally:
                        task.cancel()
            except Exception as exc:
                # The link dropping is normal in a disaster. Keep trying.
                print("link down (%s). retrying in 2 s" % exc)
                await asyncio.sleep(2.0)
    finally:
        source.release()


def main() -> None:
    ap = argparse.ArgumentParser(description="AFRICA RESQ camera rover")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/rover")
    ap.add_argument("--token", default=os.getenv("RESQ_ROVER_TOKEN", ""),
                    help="shared secret if the server requires one")
    ap.add_argument("--source", default="0",
                    help="camera index (0, 1, ...), or a path to a video or an image")
    ap.add_argument("--at", default="A1", help="survey cell the camera is installed in")
    ap.add_argument("--heading", type=float, default=0.0,
                    help="degrees the camera faces, 0 = east")
    ap.add_argument("--hz", type=float, default=5.0,
                    help="frames per second. 5 suits a field radio link, which is what "
                         "the contract is built for; on a local network the ceiling is "
                         "the camera and the models, around 18 with both loaded. Note "
                         "the dashboard cannot show more than RESQ_BROADCAST_HZ (8).")
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--device", default="cpu", help="cpu, or 0 for a CUDA device")
    ap.add_argument("--jpeg-width", type=int, default=320)
    ap.add_argument("--jpeg-quality", type=int, default=60)
    ap.add_argument("--no-jpeg", action="store_true",
                    help="omit the feed and let the dashboard draw a sim view")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    url = args.url
    if args.token:
        url += ("&" if "?" in url else "?") + "token=" + quote(args.token)

    try:
        asyncio.run(run(url, args))
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
