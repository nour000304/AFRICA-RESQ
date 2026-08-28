"""The mission record.

Until now a mission left no trace. The board showed the incident while it was happening
and forgot it the moment the process restarted -- no way to review a call afterwards, no
way to ask how long the air was bad before anyone noticed, nothing for a coroner or a
debrief. This is the layer that fixes that, and it arrived with the merge of the
teammates' repository, where it was src/data_engine.py and src/event_bus.py.

Two stores, both stdlib, because they answer different questions:

    <dir>/africa_resq.db     SQLite, indexed -- for "what happened between 14:02 and 14:09"
    <dir>/events.jsonl       append-only lines -- for anything that wants to stream it out

Four things had to change before it could live in this server.

*Writes leave the event loop.* An INSERT and a file append on the loop would stall the
8 Hz broadcast, and the one thing the dashboard must never do is go quiet during an
incident. Recording is a put on a queue; one writer task drains it. One writer also means
there is no second thread racing the same connection.

*Time is UTC.* The upstream store wrote naive local timestamps while the REST layer wrote
offset-aware UTC, which is two clocks in one system.

*Failures are audible.* A store that has silently stopped recording is worse than no
store, because nobody finds out until they go looking for the record. Errors go to the
mission log.

*The camera frame never lands here.* A base64 JPEG at 8 Hz would be gigabytes an hour and
would bury the readings it was filed next to.

And the rule the rest of this codebase is built on holds here too: a reading that was not
taken is stored as NULL. It is never rounded to zero on the way in, because a row saying
0 ppm CO and a row saying "nobody measured the CO" have to stay different rows forever.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import geo

DB_NAME = "africa_resq.db"
JSONL_NAME = "events.jsonl"

# The row shape the teammates' dashboard contract documents. Additive changes only:
# anything already reading these keys must keep working.
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    source      TEXT,
    detected    INTEGER,             -- 0/1, NULL when the row is not about a detection
    confidence  REAL,
    latitude    REAL,
    longitude   REAL,
    payload     TEXT,                -- JSON
    ts          REAL    NOT NULL,    -- epoch seconds
    ts_iso      TEXT    NOT NULL     -- the same instant, UTC, offset-aware
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events (ts);
CREATE INDEX IF NOT EXISTS idx_events_src  ON events (source);
"""

MAX_LIMIT = 10_000
QUEUE_MAX = 4096          # a backlog this deep means the disk has gone; drop, do not grow


def iso(ts: float) -> str:
    """One instant, UTC, offset-aware -- the same convention compat.py answers in."""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def to_epoch(value: Any) -> Optional[float]:
    """Accept an epoch or an ISO date, because a query string carries either."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


class Throttle:
    """How often the same thing may be written down.

    A fire that burns for an hour is one fire, not twenty-nine thousand rows. Identical
    events -- same type, same source, same verdict -- collapse to one per window. A
    change in verdict is never collapsed: fire true and fire false are different keys, so
    the moment a hazard clears is always recorded on the instant.

    A window of 0 records everything, which is what an analysis run wants.
    """

    def __init__(self, seconds: float = 2.0) -> None:
        self.seconds = max(0.0, float(seconds))
        self._last: Dict[Any, float] = {}

    def allows(self, key: Any, now: Optional[float] = None) -> bool:
        if self.seconds <= 0.0:
            return True
        now = time.time() if now is None else now
        last = self._last.get(key)
        if last is not None and (now - last) < self.seconds:
            return False
        self._last[key] = now
        return True


class Ledger:
    """The store itself. Synchronous, and every call here can block -- callers say when.

    One connection behind one lock. `check_same_thread=False` lets the connection cross
    into a worker thread, but it does not make concurrent use safe: whether two threads
    may touch one connection at once depends on how the sqlite3 this interpreter was
    built against was compiled, and on at least one common build it is a segfault rather
    than an exception. Every entry point here takes the lock, so it cannot be.
    """

    def __init__(self, directory: str) -> None:
        self._lock = threading.RLock()
        self.dir = pathlib.Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / DB_NAME
        self.jsonl_path = self.dir / JSONL_NAME
        self.jsonl_path.touch(exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._db.close()
            except Exception:
                pass

    # ------------------------------------------------------------------------- write
    def write(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Persist one row to both stores and return it with its id.

        Raises. The caller decides whether a failed write is worth telling the operator
        about, because this module is not the one holding the mission log.
        """
        payload = row.get("payload")
        try:
            payload_json = json.dumps(payload, default=str, ensure_ascii=False) \
                if payload is not None else None
        except (TypeError, ValueError):
            payload_json = json.dumps({"unserialisable": str(payload)})

        detected = row.get("detected")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (event_type, source, detected, confidence, latitude, "
                "longitude, payload, ts, ts_iso) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(row["event_type"]), str(row.get("source") or "unknown"),
                 None if detected is None else (1 if detected else 0),
                 row.get("confidence"), row.get("latitude"), row.get("longitude"),
                 payload_json, row["ts"], row["ts_iso"]))
            self._db.commit()

            stored = dict(row)
            stored["id"] = cur.lastrowid
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(stored, default=str, ensure_ascii=False) + "\n")
            return stored

    # ------------------------------------------------------------------------- read
    def query(self, event_type: Optional[str] = None, source: Optional[str] = None,
              start: Any = None, end: Any = None, limit: int = 100,
              offset: int = 0) -> List[Dict[str, Any]]:
        where, params = [], []
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if source:
            where.append("source = ?")
            params.append(source)
        begin, finish = to_epoch(start), to_epoch(end)
        if begin is not None:
            where.append("ts >= ?")
            params.append(begin)
        if finish is not None:
            where.append("ts <= ?")
            params.append(finish)

        clause = ("WHERE " + " AND ".join(where)) if where else ""
        params += [max(1, min(int(limit), MAX_LIMIT)), max(0, int(offset))]
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events %s ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?" % clause,
                params).fetchall()
        return [self._parse(r) for r in rows]

    def stats(self, since: Any = None) -> Dict[str, Any]:
        clause, params = "", []
        begin = to_epoch(since)
        if begin is not None:
            clause, params = "WHERE ts >= ?", [begin]

        with self._lock:
            return self._stats(clause, params)

    def _stats(self, clause: str, params: List[Any]) -> Dict[str, Any]:
        total = self._db.execute(
            "SELECT COUNT(*) AS n FROM events " + clause, params).fetchone()["n"]
        by_type = {r["event_type"]: r["n"] for r in self._db.execute(
            "SELECT event_type, COUNT(*) AS n FROM events " + clause
            + " GROUP BY event_type", params).fetchall()}
        by_source = {r["source"]: r["n"] for r in self._db.execute(
            "SELECT source, COUNT(*) AS n FROM events " + clause
            + " GROUP BY source", params).fetchall()}
        detected = {r["event_type"]: {"total": r["total"], "detected": r["detected"]}
                    for r in self._db.execute(
                        "SELECT event_type, COUNT(*) AS total, "
                        "COALESCE(SUM(CASE WHEN detected = 1 THEN 1 ELSE 0 END), 0) AS detected "
                        "FROM events " + clause + " GROUP BY event_type", params).fetchall()}
        last = self._db.execute(
            "SELECT ts, ts_iso FROM events " + clause
            + " ORDER BY ts DESC LIMIT 1", params).fetchone()
        return {
            "total": total, "by_type": by_type, "by_source": by_source,
            "detected_by_type": detected,
            "last_event": {"ts": last["ts"], "ts_iso": last["ts_iso"]} if last else None,
        }

    def export(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events ORDER BY ts ASC, id ASC").fetchall()
        return [self._parse(r) for r in rows]

    @staticmethod
    def _parse(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        raw = out.get("payload")
        try:
            out["payload"] = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            out["payload"] = None
        # 0 and 1 come back as booleans; NULL stays None. Never coerce None to False --
        # "no detection" and "not a detection row" are different facts.
        out["detected"] = None if out.get("detected") is None else bool(out["detected"])
        return out


class Recorder:
    """The async front of the ledger: a queue, one writer, and a fan-out for listeners.

    `record` never blocks and never raises. It stamps a row, asks the throttle whether it
    is worth writing down, and hands it to the writer task. Everything that touches the
    disk happens in a worker thread, so a slow filesystem costs the broadcast nothing.
    """

    def __init__(self, ledger: Optional[Ledger], throttle_s: float = 2.0,
                 on_error: Optional[Callable[[str], None]] = None) -> None:
        self.ledger = ledger
        self.throttle = Throttle(throttle_s)
        self.on_error = on_error
        # Built in start(), not here. An asyncio.Queue binds itself to a loop the moment
        # it is constructed, and on 3.9 that is whatever loop happens to exist at import
        # time -- not the one the server ends up running on.
        self.queue: Optional["asyncio.Queue[Dict[str, Any]]"] = None
        self.subscribers: List["asyncio.Queue[str]"] = []
        self.latest_event: Optional[Dict[str, Any]] = None
        self.latest_state: Optional[Dict[str, Any]] = None
        self.written = 0
        self.dropped = 0
        self._task: Optional[asyncio.Task] = None
        self._complained = False

    @property
    def enabled(self) -> bool:
        return self.ledger is not None

    # ----------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self.queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._task = asyncio.create_task(self._writer())

    async def stop(self) -> None:
        """Drain what is queued before going away. A record that was taken and then
        thrown out on shutdown is the worst of both designs."""
        if self._task is not None and self.queue is not None:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            self._task.cancel()
            self._task = None
        if self.ledger is not None:
            await asyncio.to_thread(self.ledger.close)

    async def _writer(self) -> None:
        while True:
            row = await self.queue.get()
            try:
                stored = await asyncio.to_thread(self.ledger.write, row)
                self.written += 1
                self.latest_event = stored
                self._fan_out({"kind": "event", **stored})
            except Exception as exc:
                self._complain("Mission record write failed: %s" % exc)
            finally:
                self.queue.task_done()

    def _complain(self, message: str) -> None:
        """Say it once. A disk that has filled will fail on every row, and a log that is
        nothing but that failure hides the incident it was supposed to be recording."""
        if self._complained:
            return
        self._complained = True
        if self.on_error is not None:
            self.on_error(message)

    # -------------------------------------------------------------------- writing
    def record(self, event_type: str, source: str = "unknown",
               detected: Optional[bool] = None, confidence: Optional[float] = None,
               latitude: Optional[float] = None, longitude: Optional[float] = None,
               payload: Optional[Dict[str, Any]] = None, ts: Optional[float] = None,
               throttle: bool = True) -> Optional[Dict[str, Any]]:
        """Queue one row. Returns it as queued (no id yet), or None if it was not kept."""
        if not self.enabled or self.queue is None:
            return None
        ts = time.time() if ts is None else float(ts)
        if throttle and not self.throttle.allows((event_type, source, detected), ts):
            return None

        row = {"event_type": str(event_type), "source": str(source), "detected": detected,
               "confidence": confidence, "latitude": latitude, "longitude": longitude,
               "payload": payload, "ts": ts, "ts_iso": iso(ts)}
        try:
            self.queue.put_nowait(row)
        except asyncio.QueueFull:
            # The disk is not keeping up. Drop the oldest, keep the newest: during an
            # incident the last minute matters more than the first.
            self.dropped += 1
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.queue.put_nowait(row)
            except Exception:
                return None
            self._complain("Mission record is behind; older rows are being dropped.")
        return row

    def record_frame(self, frame: Any, source: str = "rover") -> None:
        """One telemetry row per frame, plus one row per thing the rover can see.

        `frame_jpeg` is deliberately absent: a base64 image at 8 Hz would be gigabytes an
        hour and would bury the readings it was filed beside. Every atmosphere reading is
        copied as it arrived, so a sensor that did not report stays null in the record.
        """
        if not self.enabled or self.queue is None:
            return
        ts = time.time()
        pose = getattr(frame, "pose", None)
        zone = getattr(pose, "zone", None)
        lat, lon = (geo.latlon_of_zone(zone) if zone and zone != "--" else (None, None))
        atmo = getattr(frame, "atmosphere", None)

        self.record("telemetry", source=source, latitude=lat, longitude=lon, ts=ts,
                    payload={
                        "seq": getattr(frame, "seq", None),
                        "mode": getattr(frame, "mode", None),
                        "zone": zone,
                        "pose": {"x": getattr(pose, "x", None), "y": getattr(pose, "y", None),
                                 "heading": getattr(pose, "heading", None)},
                        "atmosphere": {k: getattr(atmo, k, None) for k in
                                       ("temp_c", "humidity_pct", "co_ppm", "lel_pct",
                                        "o2_pct", "pm25_ugm3")},
                        "unavailable": atmo.missing() if atmo is not None else None,
                        "robot": {k: getattr(getattr(frame, "robot", None), k, None)
                                  for k in ("battery_pct", "link_quality", "status",
                                            "tilt_deg", "speed_mps")},
                    })

        for det in getattr(frame, "detections", None) or []:
            self.record(str(getattr(det, "cls", "unknown")), source=source, detected=True,
                        confidence=getattr(det, "conf", None),
                        latitude=lat, longitude=lon, ts=ts,
                        payload={"zone": zone, "bbox": list(getattr(det, "bbox", []) or []),
                                 "track_id": getattr(det, "track_id", None)})

    # ------------------------------------------------------------------- listeners
    def subscribe(self) -> "asyncio.Queue[str]":
        channel: "asyncio.Queue[str]" = asyncio.Queue(maxsize=256)
        self.subscribers.append(channel)
        return channel

    def unsubscribe(self, channel: "asyncio.Queue[str]") -> None:
        try:
            self.subscribers.remove(channel)
        except ValueError:
            pass

    def publish_state(self, snapshot: Dict[str, Any]) -> None:
        self.latest_state = snapshot
        self._fan_out({"kind": "state", **snapshot})

    def _fan_out(self, payload: Dict[str, Any]) -> None:
        if not self.subscribers:
            return
        try:
            message = json.dumps(payload, default=str)
        except (TypeError, ValueError):
            return
        for channel in list(self.subscribers):
            try:
                channel.put_nowait(message)
            except asyncio.QueueFull:
                # A listener that has stopped reading does not get to slow the rest down.
                try:
                    channel.get_nowait()
                    channel.put_nowait(message)
                except Exception:
                    pass

    # ----------------------------------------------------------------- reads, off-loop
    async def query(self, **kw: Any) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        return await asyncio.to_thread(lambda: self.ledger.query(**kw))

    async def stats(self, since: Any = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"total": 0, "by_type": {}, "by_source": {}, "detected_by_type": {},
                    "last_event": None, "recording": False}
        out = await asyncio.to_thread(self.ledger.stats, since)
        out["recording"] = True
        return out

    async def export(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        return await asyncio.to_thread(self.ledger.export)


def open_ledger(directory: str, on_error: Optional[Callable[[str], None]] = None
                ) -> Optional[Ledger]:
    """Open the store, or return None and say why.

    A read-only volume must not stop a rescue board from booting. Losing the record is
    bad; refusing to show the incident because the record could not be opened is worse.
    """
    try:
        return Ledger(directory)
    except Exception as exc:
        if on_error is not None:
            on_error("Mission record is off: cannot open %s (%s)." % (directory, exc))
        return None


def parse_ingest(body: Any) -> Dict[str, Any]:
    """One event as an outside system sends it, in the shape the teammates documented.

    Tolerant in the same way server/schemas.py is: a field that cannot be read becomes
    None rather than taking the request down, because a detection reported badly is still
    worth more than a 500. `type` is the one thing that must be there -- an event with no
    kind cannot be queried for later, so it is not worth writing down.
    """
    if not isinstance(body, dict):
        raise ValueError("An event must be a JSON object.")

    kind = body.get("type") or body.get("event_type")
    if not kind or not str(kind).strip():
        raise ValueError("An event needs a type.")

    def number(key: str) -> Optional[float]:
        v = body.get(key)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    detected = body.get("detected")
    payload = body.get("payload")
    return {
        "event_type": str(kind).strip()[:64],
        "source": str(body.get("source") or "external")[:64],
        # Absent stays absent. Only an explicit value becomes a verdict.
        "detected": None if detected is None else bool(detected),
        "confidence": number("confidence"),
        "latitude": number("latitude"),
        "longitude": number("longitude"),
        "payload": payload if isinstance(payload, (dict, list)) else None,
        "ts": number("ts"),
    }
