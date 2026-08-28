"""Real detections from a camera, in the units the wire contract expects.

Two models run over every frame and their detections merge into one list:

  `models/fire_smoke.pt`  a YOLOv8n fine-tuned on fire and smoke, trained by Mohamed
                          Rayad for the AFRICA RESQ team
                          (github.com/morerayad/AFRICA-RESQ). Two classes: fire, smoke.
  `models/yolov8n.pt`     stock COCO YOLOv8n, of whose 80 classes exactly one is
                          forwarded: person. It is what feeds the survivor half of the
                          board -- `server/state.py` builds survivors from `person`
                          detections, and without this model that whole chain sits idle.

Both are committed rather than fetched. A detector that phones home on first start would
undo the reason the fonts are vendored and there is no build step: a clone has to run on
a Pi in the field with the radio link as its only network.

A word on the person model, because the ranking of these two is not obvious. COCO is
trained on ordinary photographs, not on partially buried casualties in smoke, so its
person score is the weakest evidence on the board. `server/fusion.py` is built for
exactly that: a camera-only contact is not promoted to a survivor, and a working thermal
array seeing nothing where the camera sees a person counts as evidence *against*. Adding
thermal hardware will do more for survivor confidence than a better person model would.

Two conversions matter, and both fail quietly when wrong:

  * YOLO returns pixel corners `[x1, y1, x2, y2]`. The contract wants
    `[left, top, width, height]` normalised 0..1 against the frame. `server/geometry.py`
    solves range from the box *height*, so a box in the wrong units does not merely look
    odd on the feed -- it places the hazard at the wrong distance on the map.
  * The contract's confidence key is `conf`. A dict carrying `confidence` parses to
    `conf=0.0` and the detection is silently discarded downstream.

What this deliberately does not do is hold a detection alive after the camera stops
seeing it. `server/state.py` already keeps a fire on the board until something
contradicts it; a second layer of smoothing here would delay that contradiction and
leave the operator looking at a flame that has gone out.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# Only classes the server understands are forwarded. A model that emits anything else
# has its extra classes dropped here rather than sent on to be ignored downstream --
# a class the risk engine cannot score is not evidence, it is noise on the wire.
CONTRACT_CLASSES = {"person", "fire", "smoke", "debris", "obstacle"}

# Each entry is (weights path, confidence floor, {model class name: contract class}).
# The floors sit just under the server's own thresholds -- fire is acted on at 0.40 in
# state.py and 0.35 in risk.py -- so the server does the judging, not the rover.
MODELS: List[Tuple[str, float, Dict[str, str]]] = [
    ("models/fire_smoke.pt", 0.30, {"fire": "fire", "smoke": "smoke"}),
    # COCO's other 79 classes are dropped by the mapping. A chair in the frame is not
    # something the risk engine can score, and an unscoreable class on the wire is noise.
    ("models/yolov8n.pt", 0.35, {"person": "person"}),
]

IOU_MATCH = 0.30      # overlap needed to call two boxes the same object
TRACK_TTL_S = 2.0     # how long an unseen track keeps its identity before it is retired


def _iou(a: List[float], b: List[float]) -> float:
    """Overlap of two [left, top, w, h] boxes."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 1e-9 else 0.0


class _Tracker:
    """Stable `track_id`s across frames, by greedy overlap.

    The contract asks for an id that stays with the same object because without one the
    server keys survivors by cell and two people standing together become one. This is a
    deliberately plain tracker: it matches on overlap alone and gives up after
    TRACK_TTL_S. It never emits a track that was not detected in the current frame -- an
    identity surviving a brief occlusion is memory, but a *box* surviving one would be
    an invention.
    """

    def __init__(self) -> None:
        self._tracks: Dict[str, Dict[str, Any]] = {}
        self._counts: Dict[str, int] = {}

    def assign(self, cls: str, bbox: List[float], now: float) -> str:
        best_id, best_iou = None, IOU_MATCH
        for tid, tr in self._tracks.items():
            if tr["cls"] != cls or now - tr["seen"] > TRACK_TTL_S:
                continue
            overlap = _iou(bbox, tr["bbox"])
            if overlap >= best_iou:
                best_id, best_iou = tid, overlap

        if best_id is None:
            self._counts[cls] = self._counts.get(cls, 0) + 1
            best_id = "%s-%d" % (cls, self._counts[cls])

        self._tracks[best_id] = {"cls": cls, "bbox": bbox, "seen": now}
        return best_id

    def sweep(self, now: float) -> None:
        for tid in [t for t, tr in self._tracks.items() if now - tr["seen"] > TRACK_TTL_S]:
            del self._tracks[tid]


class Detector:
    """Runs every configured model over one frame and returns contract detections."""

    def __init__(self, models: Optional[List] = None, imgsz: int = 416,
                 device: str = "cpu") -> None:
        spec = list(models or MODELS)

        # Check every mapping before anything is loaded. Weights take seconds to read on
        # a Pi, and a typo in the second model's mapping should not cost the time it
        # takes to load the first -- nor should catching it require the ML stack to be
        # installed at all.
        for path, _floor, mapping in spec:
            unknown = set(mapping.values()) - CONTRACT_CLASSES
            if unknown:
                raise ValueError("%s maps to classes the server cannot score: %s"
                                 % (path, ", ".join(sorted(unknown))))

        try:
            from ultralytics import YOLO
        except ImportError as exc:                                   # pragma: no cover
            raise SystemExit(
                "ultralytics is not installed. This is the rover-side dependency set:\n"
                "    pip install -r requirements-perception.txt"
            ) from exc

        self.imgsz = imgsz
        self.device = device
        self._tracker = _Tracker()
        self._loaded: List[Tuple[Any, float, Dict[str, str]]] = []

        for path, floor, mapping in spec:
            print("loading %s" % path)
            self._loaded.append((YOLO(path), floor, mapping))
        print("perception ready: %d model(s)" % len(self._loaded))

    def detect(self, frame: Any) -> List[Dict[str, Any]]:
        """One BGR frame in, contract detections out. The frame is never drawn on.

        YOLO's own `plot()` is deliberately not used. It would bake boxes into the JPEG
        the operator sees, and those boxes are not the ones the server received: it draws
        every class the model emits, including the 79 COCO classes this rover drops, so a
        chair or a vase in the flames would appear on the feed and nowhere else. With two
        models it is worse -- each call replaces the previous model's annotation, so the
        fire box vanishes behind the person model's.

        The dashboard draws the boxes itself, from the detections the server actually
        holds. That way the feed and the detection list cannot disagree, and the frame on
        the wire stays a photograph rather than a claim.

        A model that throws is reported and skipped. It must not take the telemetry
        stream down with it -- a rover that stops sending frames is read as a lost link,
        and a lost link is a far worse thing to report than one blind sensor.
        """
        now = time.time()
        height, width = frame.shape[:2]
        detections: List[Dict[str, Any]] = []

        for model, floor, mapping in self._loaded:
            try:
                results = model(frame, conf=floor, imgsz=self.imgsz,
                                verbose=False, device=self.device)
            except Exception as exc:
                print("detector error (%s): %s" % (getattr(model, "model_name", "?"), exc))
                continue

            for box in results[0].boxes:
                name = model.names[int(box.cls[0])]
                cls = mapping.get(name)
                if cls is None:
                    continue

                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                # Pixels to fractions of the frame, clamped: a box running off the edge
                # is real, but a negative width would invert the range solution.
                left = max(0.0, min(1.0, x1 / width))
                top = max(0.0, min(1.0, y1 / height))
                w = max(0.0, min(1.0 - left, (x2 - x1) / width))
                h = max(0.0, min(1.0 - top, (y2 - y1) / height))
                if w <= 0.0 or h <= 0.0:
                    continue

                bbox = [round(v, 4) for v in (left, top, w, h)]
                detections.append({
                    "cls": cls,
                    "conf": round(float(box.conf[0]), 3),
                    "bbox": bbox,
                    "track_id": self._tracker.assign(cls, bbox, now),
                })

        self._tracker.sweep(now)
        return detections
