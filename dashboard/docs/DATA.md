# The mission record

Until the teammates' merge, an incident existed only while the process did. The board
showed it, the process restarted, and it was gone — no debrief, no way to ask how long the
air had been bad before anyone noticed, nothing to hand anyone afterwards.

`server/recorder.py` writes every frame and every detection to two stores at once, both
stdlib, because they answer different questions:

```
$RESQ_RECORD_DIR/africa_resq.db     SQLite, indexed on type, time and source
$RESQ_RECORD_DIR/events.jsonl       append-only, one JSON object per line
```

`RESQ_RECORD_DIR` defaults to `/data` when that directory exists — which it does in the
container — and to `./data` otherwise. Set `RESQ_RECORD=0` to turn recording off; the log
says so at startup, because a mission leaving no trace should never be a silent default.

## A row

```json
{
  "id": 41,
  "event_type": "fire",
  "source": "rover",
  "detected": true,
  "confidence": 0.92,
  "latitude": 30.044413,
  "longitude": 31.235716,
  "payload": {"zone": "D3", "bbox": [0.4, 0.4, 0.1, 0.1], "track_id": null},
  "ts": 1787875498.57,
  "ts_iso": "2026-08-28T00:04:58+00:00"
}
```

`ts_iso` is UTC and offset-aware, the same convention `server/compat.py` answers in. The
upstream store wrote naive local time while the REST layer wrote UTC, which is two clocks
in one system and exactly the thing you do not want to find in the record.

`latitude` and `longitude` come from the rover's survey cell through `server/geo.py`, so
they are only as good as the mission anchor — see [API.md](API.md#where-the-grid-is-on-earth).

### `detected` has three values, and they are all different

| | |
|---|---|
| `true` | something was detected |
| `false` | it was looked for and was not there |
| `null` | this row is not about a detection at all — telemetry |

**Nothing is ever coerced.** A row saying `0` ppm CO and a row saying nobody measured the
CO have to stay different rows forever; the same rule the rest of this codebase is built
on, at the last place it could quietly break. `tests/test_recorder.py` holds it.

`frame_jpeg` is never recorded. A base64 image at 8 Hz is gigabytes an hour and would bury
the readings it was filed beside.

## What gets written

One `telemetry` row per frame — pose, mode, every atmosphere reading as it arrived (`null`
included), the robot's own condition — plus one row per detection in that frame, typed by
its class: `fire`, `smoke`, `person`.

### The throttle

A fire that burns for an hour is one fire, not thirty thousand rows. Identical events —
same type, same source, same verdict — collapse to one per `RESQ_RECORD_THROTTLE_S`
window (default `2.0`; set `0` to record everything, which is what an analysis run wants).

A **change of verdict is never collapsed**: `fire true` and `fire false` are different
keys, so the moment a hazard clears is recorded on the instant. And an event filed through
`POST /api/events` bypasses the throttle entirely — an outside system reports once, and
folding that into a rover's telemetry window would lose the only record of it.

## Reading it back

Over HTTP, without touching the files — see [API.md](API.md#the-mission-record):

```bash
curl 'localhost:8000/api/events?type=fire&start=2026-08-28&limit=100'
curl  localhost:8000/api/events/stats
curl  localhost:8000/api/events/export > mission.json
curl -N localhost:8000/api/events/stream          # live
```

Straight off the disk, for an ETL job that wants the whole thing:

```bash
sqlite3 /data/africa_resq.db \
  'SELECT event_type, COUNT(*), MIN(ts_iso), MAX(ts_iso) FROM events GROUP BY 1'

jq -c 'select(.event_type == "fire" and .confidence > 0.8)' /data/events.jsonl
```

The JSONL is append-only and never rewritten, so it is safe to tail while a mission is
running and safe to copy while the server holds it open.

## Under the hood

Writes never touch the event loop. `record()` stamps a row and puts it on a queue; one
writer task drains it in a worker thread. An `INSERT` and a file append on the loop would
stall the 8 Hz broadcast, and going quiet mid-incident is the one thing the dashboard must
never do.

Every SQLite call takes a lock. `check_same_thread=False` lets the connection cross into a
worker thread but does not make concurrent use safe — on some builds a reader racing the
writer is a segfault rather than an exception, which is how this was found.

Failures are audible, once. A store that has silently stopped recording is worse than no
store, because nobody finds out until they go looking for the record. The first failure
goes to the mission log and the rest are swallowed, so a full disk does not bury the
incident it was meant to be recording.

A store that cannot be opened — a read-only volume, a missing mount — turns recording off
and says so. The board still boots. Losing the record is bad; refusing to show the
incident because the record could not be opened is worse.

## Deployment

The container creates `/data` owned by the app user, and `docker-compose.yml` mounts the
`resq_data` volume there. Without that volume the ledger lives in the container's writable
layer and vanishes with it — which is what happened before this merge, when the Dockerfile
prepared `/data` and nothing ever mounted it.
