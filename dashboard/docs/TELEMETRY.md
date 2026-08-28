# Rover → command wire contract

Push this object to `ws://<host>:8000/ws/rover` at 2–10 Hz, or POST it to `/api/frame`.
Field-by-field definitions live in `server/schemas.py`; that file is the authority.

```jsonc
{
  "mission_id": "RESQ-001",
  "seq": 412,
  "t": 1755800000.4,               // rover clock, unix seconds
  "mode": "assisted",              // manual | assisted | autonomous

  "pose":  { "x": 10.5, "y": 1.5, "heading": 90.0, "zone": "D1" },
  //         metres from the SW corner; heading degrees, 0 = east. zone is optional,
  //         the server derives it if absent.

  "robot": { "battery_pct": 92.0, "link_quality": 0.86, "status": "searching",
             "tilt_deg": 3.1, "speed_mps": 0.9 },

  "atmosphere": {                  // any field may be null — null means NOT MEASURED
    "temp_c": 28.4, "humidity_pct": 42.0, "co_ppm": 6.0,
    "lel_pct": 0.4, "o2_pct": 20.9, "pm25_ugm3": 16.0
  },

  "detections": [                  // bbox is [x, y, w, h] normalised 0..1 on the frame
    { "cls": "person", "conf": 0.93, "bbox": [0.44, 0.38, 0.17, 0.42], "track_id": "P1" },
    { "cls": "fire",   "conf": 0.92, "bbox": [0.66, 0.30, 0.26, 0.46] }
  ],
  // recognised classes: person, fire, smoke, debris, obstacle

  "thermal": {                     // omit the block entirely if there is no thermal array
    "available": true, "max_c": 36.4, "min_c": 24.1,
    "blobs": [ { "peak_c": 36.4, "bbox": [0.45,0.37,0.16,0.43],
                 "human_like": 0.96, "track_id": "P1" } ]
  },

  "ranges": { "front_m": 1.6, "left_m": 2.8, "right_m": 2.3, "rear_m": 3.0 },

  "frame_jpeg": null,              // "data:image/jpeg;base64,..." to show the real camera
  "notes": null
}
```

## Rules that matter

1. **A sensor you cannot read is `null`.** Never send a default, a last-known value or a
   zero. The risk engine turns a missing reading into an `unknown` cause that raises the
   score; a fabricated safe value would lower it.
2. **`human_like` is your thermal classifier's own score**, not a temperature test. The
   server applies the temperature band and the hot-scene discount itself.
3. **Keep `track_id` stable** across frames for the same object. Without it the server
   keys survivors by cell, and two people in one cell become one.
4. **Bounding boxes carry the range estimate.** A sloppy box height moves the survivor on
   the map, because distance is solved from apparent height.

## Commands the server sends back

```jsonc
{ "cmd": "estop", "on": true }
{ "cmd": "mode",  "mode": "assisted" }
{ "cmd": "drive", "throttle": 0.4, "steer": -0.2 }
```

The rover must act on `estop` before anything else, and must stop on its own if frames
stop being acknowledged.
