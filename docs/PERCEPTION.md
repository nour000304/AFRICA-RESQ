# Camera perception

The rover's eyes. Two YOLO models wrapped so their output arrives at the command server
as an ordinary `RoverFrame` — the same contract the simulator speaks, so nothing
downstream knows or cares which one is connected.

```
camera ─▶ rover/perception.py ─▶ RoverFrame ─ws─▶ /ws/rover ─▶ fusion · risk · pathing
          fire_smoke.pt + yolov8n.pt
```

## The models

| file | source | classes forwarded |
|---|---|---|
| `models/fire_smoke.pt` | YOLOv8n fine-tuned by Mohamed Rayad for the AFRICA RESQ team ([morerayad/AFRICA-RESQ](https://github.com/morerayad/AFRICA-RESQ)) | `fire`, `smoke` |
| `models/yolov8n.pt` | stock COCO YOLOv8n | `person` (1 of its 80) |

Both run over every frame and their detections merge into one list. COCO's other 79
classes are dropped by the mapping — a chair in frame is not something `server/risk.py`
can score, and an unscoreable class on a field radio link is noise.

Both are committed rather than fetched. A detector that phones home on first start would
undo the reason the fonts are vendored and there is no build step: a clone has to run on
a Pi in the field with the radio link as its only network. 13 MB total.

**On the person model.** COCO is trained on ordinary photographs, not on partially buried
casualties in smoke, so its person score is the weakest evidence on the board.
`server/fusion.py` is built for exactly that — a camera-only contact is not promoted to a
survivor, and a working thermal array seeing nothing where the camera sees a person
counts as evidence *against*. Adding thermal hardware will do more for survivor
confidence than a better person model would.

## Running it

```bash
pip install -r requirements.txt -r requirements-perception.txt

python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
python -m rover.camera_client --at D3 --heading 90 --verbose
```

`--at` and `--heading` are where the camera was physically installed and which way it
points. They are surveyed constants, not readings: a rover that can drive should read
odometry into `pose` instead. Everything else defaults sensibly — camera 0, 5 Hz, 416 px
inference, CPU, and a 320 px JPEG feed so the dashboard shows the real camera instead of
the drawn scene.

| flag | default | |
|---|---|---|
| `--url` | `ws://127.0.0.1:8000/ws/rover` | command server |
| `--token` | `$RESQ_ROVER_TOKEN` | required if the server sets one |
| `--source` | `0` | camera index, or a path to a video or an image |
| `--hz` | `5` | frames per second. Suits a field radio link; on a local network the ceiling is the camera and the models, around 18 with both loaded. The dashboard cannot show more than `RESQ_BROADCAST_HZ`. |
| `--device` | `cpu` | `0` for a CUDA device |
| `--no-jpeg` | off | drop the feed on a thin radio link |

A file source exists so the perception chain can be driven with no hardware — on a
machine with no camera permission, or in a demo that has to show the same fire twice. A
video loops and a still image repeats, and neither is presented as a live sensor: the
frame's `notes` say so, where the operator reads them.

If the device goes away mid-run — a laptop suspending, a lid closing, another
application taking the camera — ten consecutive failed reads trigger a reopen, with a
widening gap so a device that is gone for good is not hammered. Until it comes back the
server reports the link as lost, which is the honest reading: the rover is connected and
telling you nothing.

## What this rover does not measure

Every field below is sent as `null` on every frame, and that is the design:

```jsonc
"atmosphere": { "temp_c": null, "co_ppm": null, "lel_pct": null, "o2_pct": null, ... },
"ranges":     { "front_m": null, "left_m": null, "right_m": null, "rear_m": null },
"thermal":    { "available": false, "blobs": [] },
"robot":      { "battery_pct": null, "link_quality": null, ... }
```

`server/risk.py` turns each into an `unknown` cause that raises the score and prints
"not measured" on the ledger. A camera-only rover *should* read as a partial picture.
The failure mode worth naming is the other one: a hardcoded `"o2_pct": 20.9` would score
as clean air and tell an operator it is safe to send people into a room nobody sampled.

`docs/TELEMETRY.md` rule 1 is the rule this file exists to obey.

## The two conversions

Both are in `rover/perception.py`, and both fail quietly rather than loudly. Both are
pinned by tests in `tests/test_perception.py`:

**Boxes.** YOLO returns pixel corners `[x1, y1, x2, y2]`. The contract wants
`[left, top, width, height]` normalised 0..1. `server/geometry.py` solves range from the
box *height* against a known vertical field of view, so a box left in pixels does not
just look wrong on the feed — it puts the survivor tens of metres off on the map.

**Keys.** The contract's confidence field is `conf`. A detection dict carrying
`confidence` parses to `conf=0.0` and is dropped downstream without an error.

## Tracking

`_Tracker` gives each object a `track_id` that survives across frames, matched on box
overlap alone. Contract rule 3 asks for this because the server otherwise keys survivors
by cell — and two people standing together, which is the normal case in a rescue, become
one survivor.

It never emits a box that was not detected in the current frame. Keeping an *identity*
alive through a brief occlusion is memory; keeping a *box* alive is invention. The
upstream project smooths detections with a 15-frame hold — that is deliberately not
carried over, because `server/state.py` already keeps a fire on the board until
something contradicts it, and a second layer of hold would only delay the contradiction
and leave the operator looking at a flame that has gone out.

## Swapping or adding a model

`MODELS` is the whole configuration:

```python
MODELS = [
    ("models/fire_smoke.pt", 0.30, {"fire": "fire", "smoke": "smoke"}),
    ("models/yolov8n.pt",    0.35, {"person": "person"}),
]
```

Each entry is `(weights, confidence floor, {model class name: contract class})`. The
floors sit just under the server's own thresholds — fire is acted on at 0.40 in
`state.py` and 0.35 in `risk.py` — so the server does the judging, not the rover.

`CONTRACT_CLASSES` is validated before any weights are read, so a typo in a mapping
fails on startup with a clear message rather than silently emitting detections the risk
engine will ignore. The classes the server can score are `person`, `fire`, `smoke`,
`debris`, `obstacle`.

## The browser bench

Anyone who opens the board can press **Test detector** and run the same two models on
their own camera. It answers the one question a live board cannot: is the detection real,
or is this a mock-up?

It is deliberately not a rover, and `dashboard/js/bench.js` says why at length. The short
version: the server holds one mission, so if every visitor pushed frames to `/ws/rover`
two visitors would be two cameras overwriting each other on one shared board — and the
rover token would have to ship in a public file, where anyone could read it and invent
survivors on a live rescue board.

So nothing leaves the machine. The camera is read locally, inference runs locally in
WebAssembly, boxes are drawn locally, and the mission behind the panel is untouched. The
server pays nothing, which matters on one shared vCPU.

```
dashboard/models/*.onnx        the same weights, exported at imgsz=416   (25 MB)
dashboard/vendor/ort/          onnxruntime-web, wasm backend             (11 MB)
```

None of it is fetched until the panel is opened, so a viewer who only wants to watch the
board pays nothing either. Measured in Chromium: **~155 ms per frame, 6.5 fps** with both
models, single-threaded — threads would need cross-origin isolation headers this host
does not send.

The decode is the same arithmetic as the Python side and was checked against it: on the
same frame, ONNX in the browser returns `fire 0.335, bbox [0.369, 0.019, 0.254, 0.739]`
against PyTorch's `0.323, [0.378, 0.007, 0.249, 0.751]` — within a percent on every
coordinate, the difference being letterbox padding.

## What was not taken from the upstream project

`morerayad/AFRICA-RESQ` is a complete parallel system: its own fusion, hazard, risk,
priority, safe-path and recommendation engines behind a REST API reading a `state.json`
that a webcam loop rewrote each frame. The detector crossed over, and the REST shape
crossed over as a projection of this server's state — see [API.md](API.md). The engines
did not.

They were left because this repository already has them and they disagree. Two risk
engines scoring one incident differently on one board is worse than either alone.
`server/risk.py` scores from named causes against published limits (10 % LEL evacuation,
35 ppm CO exposure, 19.5 % oxygen minimum) and carries the arithmetic to the screen so an
operator can argue with it; the upstream engine sums weighted percentages of detection
confidence into a number with no units behind it.

Two upstream files would have been actively unsafe to import. `thermal.py` returns a heat
reading with `temperature=35.9` as a default argument, and `sensor_data.py` returns
`{"gas": 62, "temperature": 38, ...}` hardcoded on every call. Under this contract those
are not placeholders — they are measurements the board would present as real.
