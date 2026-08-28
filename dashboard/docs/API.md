# HTTP API

Three ways to read this server, all backed by the same live mission state:

| | |
|---|---|
| `ws://<host>/ws/dashboard` | the full `MissionState`, pushed 8×/s. What the dashboard uses. |
| `GET /api/state` | the same object, once, over HTTP. |
| `GET /api/status` `/api/detection` `/api/risk` `/api/full` | the compatibility shape below. |
| `GET /api/events/stream` | server-sent events: every recorded row, plus the `/api/full` projection once a second. |

There is exactly one engine behind all three. A REST client and a websocket client can
never show two different risk scores for one incident.

## Compatibility endpoints

These four are the shape `morerayad/AFRICA-RESQ` published for the frontend team.
Anything already written against that API keeps working.

What changed is where the answers come from. Upstream, each endpoint read `state.json` —
a file a webcam loop rewrote every frame — and the numbers in it came from a second set
of engines. Here the same four shapes are projected from the one live mission state by
`server/compat.py`, which holds no state, makes no judgements and computes no risk. If a
number is wrong it is wrong in `risk.py` or `state.py`, and it is wrong identically on
every transport.

Fields the upstream shape did not have are **added, never removed or renamed**. Additive
is safe for a polling client; renaming is not. `tests/test_compat.py` pins the keys and
their types.

### `GET /api/status`

```json
{
  "status": "online",
  "timestamp": "2026-08-26T16:17:43+00:00",
  "rover": "connected",
  "mission_id": "RESQ-001",
  "seq": 412,
  "age_s": 0.19
}
```

`status` means "the API answered", as it did upstream. Whether a rover is actually
reporting is a different question and gets its own field: `connected`, `waiting` (none
has ever connected) or `link_lost`.

### `GET /api/detection`

```json
{
  "fire":  { "detected": true, "confidence": 0.87, "zone": "D4",
             "in_view": false, "last_seen_s": null },
  "smoke": { "detected": false, "confidence": 0.0, "zone": null,
             "in_view": false, "last_seen_s": null },
  "survivor": { "detected": true, "confidence": 0.636, "location": "D2",
                "id": "A", "band": "probable" }
}
```

**`detected` is what the server believes, not what the last frame contained.** A fire
stays on the board until something contradicts it, so a rover that has turned away still
reports the fire it drove past — with `in_view` false. Reporting only the current frame
would tell a polling client the fire goes out every time the camera pans, which is what
the upstream 15-frame hold was papering over.

`confidence` is the vision confidence of the last real sighting. `location` is a survey
cell, as it was upstream.

### `GET /api/risk`

```json
{
  "score": 56,
  "level": "HIGH",
  "summary": "High risk, 56 of 100, driven by Combustible gas not measured, ...",
  "entry_safe": false,
  "causes": [
    { "label": "Combustible gas not measured", "kind": "unknown", "points": 12.0,
      "reading": "no reading", "threshold": "sensor required before entry" }
  ]
}
```

`score` is an integer 0–100 and `level` is `LOW` | `MEDIUM` | `HIGH` | `CRITICAL`, as
upstream. `causes` is the addition that matters: every point in the score comes from one
named cause with its reading and the limit it crossed.

A cause of kind `unknown` is a sensor that did not report. **Unknown never lowers the
score, and `entry_safe` is never true while one exists.** A blind rover reads as
dangerous, because it is.

### `GET /api/full`

Everything above plus `priority`, `route`, `recommendation`, and — beyond the upstream
shape — `pose`, `hazards`, `survivors`, `atmosphere`, `connected`.

```json
{
  "recommendation": {
    "action": "APPROACH_SURVIVOR",
    "target": "A",
    "route": ["D1", "D2"],
    "priority": "HIGH",
    "risk": 56,
    "confidence": 0.636,
    "reasons": ["Task the entry team to survivor A in D2."],
    "because": ["92% confidence from 2 agreeing sources."],
    "operator_override_allowed": true
  }
}
```

`action` is one of `APPROACH_SURVIVOR`, `CLOSE_FOR_CONFIRMATION`, `HOLD_AND_REASSESS`,
`RESTORE_LINK`, `CONTINUE_SWEEP`.

`route` is a list of survey cells — `["D1", "D2"]` — not the `(row, col)` index pairs
upstream returned. Cells are what the map shows, what the risk ledger names and what goes
out over the radio, so a route in any other vocabulary has to be translated by whoever
reads it.

## Where the grid is on Earth

The survey grid is metres from its south-west corner, and every layer of this server
speaks in cells — `B3`, not a pair of decimals. The endpoints below need a coordinate, so
one module, `server/geo.py`, anchors the grid to a point on the map and nothing else has
to learn what GPS is.

The anchor is configuration and never a reading: `RESQ_ORIGIN_LAT`, `RESQ_ORIGIN_LON` and
`RESQ_GRID_BEARING` (the true bearing of the grid's north edge, so a grid laid out along a
street resolves as correctly as one along the meridian). It rides along on every snapshot:

```json
"grid": {
  "cols": ["A","B","C","D","E","F","G","H"], "rows": 6, "cell_m": 3.0,
  "width_m": 24.0, "height_m": 18.0,
  "anchor": {"lat": 30.0444, "lon": 31.2357, "bearing_deg": 0.0},
  "sw": {"lat": 30.0444, "lon": 31.2357},
  "ne": {"lat": 30.04456, "lon": 31.23595}
}
```

### `GET /api/location?latitude&longitude`

Is a coordinate inside the region this deployment holds shelter data for. Omitting either
value is invalid — it is not read as the anchor, because "no coordinate" and "this
coordinate" are different statements.

## Shelters

Where survivors go once they are out. Thirty-eight evacuation and gathering points across
thirteen Egyptian cities, from `nour000304/AFRICA-RESQ`. The dataset is a table of
coordinates and the search over it is trigonometry, so **every endpoint here answers with
no network at all** — which matters, because "where do we take them" is the question that
gets asked at the moment the uplink goes.

| | |
|---|---|
| `GET /api/shelters?city=` | every shelter, or one city's. Matching is case-insensitive and partial. |
| `GET /api/shelters/cities` | the cities that hold at least one. |
| `GET /api/nearest_shelter?latitude&longitude&limit&city` | nearest first. |
| `GET /api/shelter/{id}` | one, by id. `404` if there is no such shelter. |

`nearest_shelter` **with no coordinate answers about this incident** — the mission anchor
— because that is what an operator asking the question means. The response says which it
used in `origin`: `"given"` or `"mission_anchor"`. A coordinate outside the region is
`422`, not a shelter on another continent.

```json
{
  "success": true, "latitude": 30.0444, "longitude": 31.2357, "origin": "mission_anchor",
  "nearest": [{
    "shelter": {"id": "CAI-03", "name": "Tahrir Square (Egyptian Museum)", "city": "Cairo",
                "type": "open_square", "lat": 30.045748, "lon": 31.235881,
                "capacity": 50000, "address": "Downtown Cairo", "contact": "+20 2 25796949"},
    "distance_km": 0.15, "bearing_deg": 6.6, "direction": "N",
    "estimated_walk_minutes": 2, "estimated_drive_minutes": 0
  }]
}
```

## Road routes

| | |
|---|---|
| `GET /api/route?start_lat&start_lon&end_lat&end_lon` | between two coordinates. |
| `GET /api/route/shelter/{id}?start_lat&start_lon` | to one shelter; from the anchor if no start is given. |

**This is not the rover's route.** `server/pathing.py` plans the rover across the survey
grid over the hazard field it costs against, and it is the only thing here that knows
whether a cell is safe. These two endpoints plan roads for the vehicle meeting the
survivors, and know nothing about hazards.

Every answer carries `source`:

- `osrm` — a real road route, only when `RESQ_OSRM_URL` is set.
- `straight_line_estimate` — distance as the crow flies at a city driving average, with a
  `note` saying so and why. **This is the default**, because a Pi on a radio link must not
  block on a public routing service. A straight line is a lower bound on a road, so the
  note always says "at least this long" — never "about".

## The mission record

Every frame and every detection is written down. See [DATA.md](DATA.md) for the row
schema, the throttle and how to pull the whole thing out.

| | |
|---|---|
| `GET /api/events?type&source&start&end&limit&offset` | query the history, newest first. |
| `GET /api/events/latest?limit` | recent rows, the current state, the counts. |
| `GET /api/events/stats?since` | totals by type, by source, detected vs seen. |
| `GET /api/events/export` | every stored row, oldest first. |
| `POST /api/events` | ingest a detection from outside this server. |
| `GET /api/events/stream` | the live feed, server-sent. |

`start` and `end` take an epoch or an ISO date. `POST` needs a `type`; everything else is
optional and anything unreadable becomes `null` rather than a `400` — but an **absent
`detected` stays absent**, and never becomes `false`.

### `GET /api/events/stream`

Server-sent events, for clients that are not the dashboard — a chart or a map with no
command to send back. Three kinds of message:

```javascript
const feed = new EventSource('/api/events/stream');
feed.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  // msg.kind === 'hello' — greeting, with the current stats
  // msg.kind === 'event' — a row, exactly as the ledger stored it, with its id
  // msg.kind === 'state' — the /api/full projection, once a second
};
```

`state` messages are the same projection `GET /api/full` returns, so a client streaming
and a client polling can never end up showing two different risk scores. A quiet mission
emits an SSE comment every 15 s so a proxy does not mistake calm for a dead connection.

## Ingest

`POST /api/frame` accepts one `RoverFrame` for rovers without a websocket client. See
[TELEMETRY.md](TELEMETRY.md) for the contract, and `server/schemas.py` for the authority.

## Auth

Reading is not gated — during an incident far more people need to see the board than to
drive it. `POST /api/frame` and `POST /api/events` both require `RESQ_ROVER_TOKEN` (header
`x-resq-token` or `?token=`) when one is configured, because both put a detection on a
live rescue board. Commands require `RESQ_OPERATOR_TOKEN` over the dashboard socket. With
no token configured, writes are accepted from loopback and private networks only and
refused from a public address, so a misconfigured deployment fails closed. See
`server/config.py`.
