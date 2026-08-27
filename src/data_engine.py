"""Data engineering layer for AFRICA RESQ.

Every detection event (from the camera / YOLO pipeline or the fake sensor
simulator) is persisted here so the data can be analysed later.

Storage:
  - SQLite  (data/africa_resq.db)   -> queryable structure, indexes
  - JSONL   (data/events.jsonl)      -> append-only export ready for pipelines

Both use the stdlib only (sqlite3, json) so no extra dependencies are needed.
"""

import json
import os
import sqlite3
import time
from datetime import datetime

# Project root
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DB_PATH = os.environ.get(
    "DATA_DB_PATH",
    os.path.join(DEFAULT_DATA_DIR, "africa_resq.db")
)
DEFAULT_JSONL_PATH = os.environ.get(
    "DATA_JSONL_PATH",
    os.path.join(DEFAULT_DATA_DIR, "events.jsonl")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    source      TEXT,
    detected    INTEGER,             -- 0/1 (NULL for telemetry only)
    confidence  REAL,
    latitude    REAL,
    longitude   REAL,
    payload     TEXT,                -- JSON blob
    ts          REAL    NOT NULL,    -- epoch seconds
    ts_iso      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events (ts);
CREATE INDEX IF NOT EXISTS idx_events_src  ON events (source);
"""


class DataEngine:

    def __init__(
        self,
        db_path=DEFAULT_DB_PATH,
        jsonl_path=DEFAULT_JSONL_PATH,
        throttle_seconds=None,
        on_event=None
    ):
        if throttle_seconds is None:
            throttle_seconds = float(
                os.environ.get("DATA_THROTTLE", "2.0")
            )

        self.db_path = db_path
        self.jsonl_path = jsonl_path
        self.throttle_seconds = throttle_seconds

        # Optional callback fired for every stored event (used to push
        # real-time updates to dashboards through the EventBus).
        self.on_event = on_event

        # last logged time per key (used to avoid spamming identical events)
        self._last_logged = {}

        self._init_dirs()
        self._init_db()

    # ------------------------------------------------------------
    # Init
    # ------------------------------------------------------------

    def _init_dirs(self):
        for path in (self.db_path, self.jsonl_path):
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

        # Ensure the append-only export file exists up-front
        if not os.path.exists(self.jsonl_path):
            with open(self.jsonl_path, "a", encoding="utf-8"):
                pass

    def _init_db(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------

    def log_event(
        self,
        event_type,
        source="unknown",
        detected=None,
        confidence=None,
        latitude=None,
        longitude=None,
        payload=None,
        ts=None
    ):
        if ts is None:
            ts = time.time()

        ts_iso = datetime.fromtimestamp(ts).isoformat()

        key = (event_type, source, bool(detected))

        # Throttle identical events to keep storage sane (default: every 2s)
        now = time.time()
        last = self._last_logged.get(key)
        if last is not None and (now - last) < self.throttle_seconds:
            return None

        self._last_logged[key] = now

        try:
            payload_json = json.dumps(
                payload,
                default=str,
                ensure_ascii=False
            ) if payload is not None else None
        except Exception:
            payload_json = str(payload)

        try:
            cursor = self._conn.execute(
                "INSERT INTO events "
                "(event_type, source, detected, confidence, latitude, "
                " longitude, payload, ts, ts_iso) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(event_type),
                    str(source),
                    (1 if detected else 0) if detected is not None else None,
                    confidence,
                    latitude,
                    longitude,
                    payload_json,
                    ts,
                    ts_iso
                )
            )
            self._conn.commit()

            event_id = cursor.lastrowid

            # Also append to the JSONL file (append-only export)
            line = {
                "id": event_id,
                "event_type": str(event_type),
                "source": str(source),
                "detected": detected,
                "confidence": confidence,
                "latitude": latitude,
                "longitude": longitude,
                "payload": payload,
                "ts": ts,
                "ts_iso": ts_iso
            }

            with open(
                self.jsonl_path,
                "a",
                encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(line, default=str, ensure_ascii=False) + "\n"
                )

            if self.on_event is not None:
                try:
                    self.on_event(line)
                except Exception:
                    pass

            return event_id

        except Exception as e:
            print("DATA ENGINE LOG ERROR:", e)

            return None

    def log_snapshot(self, snapshot):
        """Persist one full simulator / pipeline snapshot.

        Stores a telemetry record plus one record per active detection,
        so that "when the camera/sensor detects something it is saved".
        """
        ts = snapshot.get("timestamp", time.time())

        vehicle = snapshot.get("vehicle", {})
        gps = vehicle.get("gps", {})
        environment = snapshot.get("environment", {})
        detections = snapshot.get("detections", {})

        # 1) telemetry record (always)
        self.log_event(
            "telemetry",
            source=snapshot.get("source", "unknown"),
            detected=None,
            confidence=None,
            latitude=gps.get("lat"),
            longitude=gps.get("lon"),
            payload={
                "environment": environment,
                "vehicle": vehicle,
                "risk": snapshot.get("risk"),
                "recommendation": snapshot.get("recommendation"),
                "tick": snapshot.get("tick")
            },
            ts=ts
        )

        # 2) one record per active detection (fire / smoke / survivor)
        for key in ("fire", "smoke", "survivor"):
            detection = detections.get(key) if detections else None

            if not detection or not detection.get("detected"):
                continue

            self.log_event(
                key,
                source=snapshot.get("source", "unknown"),
                detected=True,
                confidence=detection.get("confidence"),
                latitude=gps.get("lat"),
                longitude=gps.get("lon"),
                payload={
                    "location": detection.get("location"),
                    "risk": snapshot.get("risk"),
                    "vector": detection
                },
                ts=ts
            )

    # ------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------

    def query_events(
        self,
        event_type=None,
        source=None,
        start=None,
        end=None,
        limit=100,
        offset=0
    ):
        clauses = []
        params = []

        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if start is not None:
            clauses.append("ts >= ?")
            params.append(self._to_epoch(start))
        if end is not None:
            clauses.append("ts <= ?")
            params.append(self._to_epoch(end))

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        limit = max(1, min(int(limit), 10000))
        offset = max(0, int(offset))

        sql = (
            f"SELECT * FROM events {where} "
            "ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?"
        )
        params = params + [limit, offset]

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except Exception as e:
            print("DATA QUERY ERROR:", e)

            return []

        return [self._row_to_dict(row) for row in rows]

    def stats(self, since=None):
        base = "WHERE ts >= ?" if since is not None else ""
        params = [self._to_epoch(since)] if since is not None else []

        try:
            total = self._conn.execute(
                "SELECT COUNT(*) AS n FROM events " + base,
                params
            ).fetchone()["n"]

            by_type = {
                row["event_type"]: row["n"]
                for row in self._conn.execute(
                    "SELECT event_type, COUNT(*) AS n FROM events "
                    + base + " GROUP BY event_type",
                    params
                ).fetchall()
            }

            detected_rows = self._conn.execute(
                "SELECT event_type, "
                "COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN detected = 1 THEN 1 ELSE 0 END), 0) "
                "AS detected "
                "FROM events " + base + " GROUP BY event_type",
                params
            ).fetchall()

            source_rows = self._conn.execute(
                "SELECT source, COUNT(*) AS n FROM events "
                + base + " GROUP BY source",
                params
            ).fetchall()

            last = self._conn.execute(
                "SELECT ts_iso, ts FROM events "
                + base + " ORDER BY ts DESC LIMIT 1",
                params
            ).fetchone()

            return {
                "total": total,
                "by_type": by_type,
                "by_source": {r["source"]: r["n"] for r in source_rows},
                "detected_by_type": {
                    r["event_type"]: {
                        "total": r["total"],
                        "detected": r["detected"]
                    }
                    for r in detected_rows
                },
                "last_event": (
                    {"ts": last["ts"], "ts_iso": last["ts_iso"]}
                    if last else None
                )
            }

        except Exception as e:
            print("DATA STATS ERROR:", e)

            return {"total": 0, "by_type": {}, "by_source": {}, "detected_by_type": {}}

    def export(self):
        """Return every stored event as a list of dicts (JSON export)."""
        try:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY ts ASC, id ASC"
            ).fetchall()
        except Exception:
            return []

        return [self._row_to_dict(row) for row in rows]

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    @staticmethod
    def _to_epoch(value):
        if value is None:
            return value

        try:
            return float(value)
        except (TypeError, ValueError):
            pass

        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _row_to_dict(row):
        data = dict(row)

        try:
            data["payload"] = (
                json.loads(data["payload"])
                if data.get("payload")
                else None
            )
        except Exception:
            data["payload"] = None

        data["detected"] = (
            bool(data["detected"])
            if data.get("detected") is not None
            else None
        )

        return data