import json
import os
import tempfile
import time

from data_engine import DataEngine


def _engine(tmpdir):
    directory = str(tmpdir)

    return DataEngine(
        db_path=os.path.join(directory, "test.db"),
        jsonl_path=os.path.join(directory, "events.jsonl"),
        throttle_seconds=0
    )


def test_db_and_jsonl_created(tmpdir):
    engine = _engine(tmpdir)
    assert os.path.exists(engine.db_path)
    assert os.path.exists(engine.jsonl_path)


def test_log_event_returns_id_and_persists(tmpdir):
    engine = _engine(tmpdir)

    event_id = engine.log_event(
        "fire",
        source="simulator",
        detected=True,
        confidence=0.92,
        latitude=30.0444,
        longitude=31.2357,
        payload={"zone": "B3"}
    )

    assert event_id is not None

    rows = engine.query_events(event_type="fire")
    assert len(rows) == 1

    row = rows[0]
    assert row["event_type"] == "fire"
    assert row["detected"] is True
    assert row["confidence"] == 0.92
    assert row["latitude"] == 30.0444


def test_jsonl_appended(tmpdir):
    engine = _engine(tmpdir)

    engine.log_event("smoke", detected=True, confidence=0.7)

    with open(engine.jsonl_path, "r", encoding="utf-8") as f:
        line = json.loads(f.readline())

    assert line["event_type"] == "smoke"
    assert line["detected"] is True


def test_query_filters(tmpdir):
    engine = _engine(tmpdir)

    engine.log_event("fire", source="sim", detected=True)
    engine.log_event("smoke", source="sim", detected=True)
    engine.log_event("fire", source="cam", detected=True)

    assert len(engine.query_events()) == 3
    assert len(engine.query_events(event_type="fire")) == 2
    assert len(engine.query_events(source="cam")) == 1
    assert len(engine.query_events(event_type="fire", source="sim")) == 1


def test_query_by_time_window(tmpdir):
    engine = _engine(tmpdir)

    old = time.time() - 3600
    engine.log_event("fire", detected=True, ts=old)
    engine.log_event("fire", detected=True, ts=time.time())

    rows = engine.query_events(start=time.time() - 120)
    assert len(rows) == 1

    rows = engine.query_events(start=old - 10, end=old + 10)
    assert len(rows) == 1


def test_stats(tmpdir):
    engine = _engine(tmpdir)

    engine.log_event("fire", detected=True)
    engine.log_event("fire", detected=True)
    engine.log_event("smoke", detected=False)

    stats = engine.stats()

    assert stats["total"] == 3
    assert stats["by_type"]["fire"] == 2
    assert stats["by_type"]["smoke"] == 1
    assert stats["detected_by_type"]["fire"]["detected"] == 2
    assert stats["last_event"] is not None


def test_log_snapshot_persists_detections(tmpdir):
    engine = _engine(tmpdir)

    snapshot = {
        "timestamp": time.time(),
        "source": "simulator",
        "vehicle": {
            "gps": {"lat": 30.0444, "lon": 31.2357}
        },
        "environment": {
            "temperature_c": 45.0,
            "gas_ppm": 250
        },
        "detections": {
            "fire": {"detected": True, "confidence": 0.88, "location": None},
            "smoke": {"detected": True, "confidence": 0.71, "location": None},
            "survivor": {"detected": False, "confidence": 0.0, "location": None}
        },
        "risk": {"score": 100, "level": "HIGH"}
    }

    engine.log_snapshot(snapshot)

    stats = engine.stats()

    # telemetry + fire + smoke
    assert stats["total"] == 3
    assert stats["by_type"].get("telemetry") == 1
    assert stats["by_type"].get("fire") == 1
    assert stats["by_type"].get("smoke") == 1
    assert "survivor" not in stats["by_type"]


def test_throttle_deduplicates(tmpdir):
    directory = str(tmpdir)
    engine = DataEngine(
        db_path=os.path.join(directory, "t.db"),
        jsonl_path=os.path.join(directory, "t.jsonl"),
        throttle_seconds=5
    )

    engine.log_event("fire", detected=True)
    engine.log_event("fire", detected=True)
    engine.log_event("fire", detected=True)

    assert len(engine.query_events(event_type="fire")) == 1


def test_export(tmpdir):
    engine = _engine(tmpdir)

    engine.log_event("fire", detected=True)
    engine.log_event("smoke", detected=True)

    rows = engine.export()
    assert len(rows) == 2
    assert rows[0]["event_type"] == "fire"
    assert rows[1]["event_type"] == "smoke"


def test_on_event_callback_fires_for_stored_events(tmpdir):
    directory = str(tmpdir)
    published = []

    engine = DataEngine(
        db_path=os.path.join(directory, "cb.db"),
        jsonl_path=os.path.join(directory, "cb.jsonl"),
        throttle_seconds=0,
        on_event=published.append
    )

    engine.log_event("fire", detected=True, confidence=0.9)
    engine.log_event(
        "smoke",
        detected=True,
        source="simulator",
        latitude=30.0444,
        longitude=31.2357
    )

    assert len(published) == 2
    assert published[0]["event_type"] == "fire"
    assert published[0]["detected"] is True
    assert published[1]["latitude"] == 30.0444


def test_on_event_not_fired_for_throttled_duplicate(tmpdir):
    directory = str(tmpdir)
    published = []

    engine = DataEngine(
        db_path=os.path.join(directory, "th.db"),
        jsonl_path=os.path.join(directory, "th.jsonl"),
        throttle_seconds=5,
        on_event=published.append
    )

    engine.log_event("fire", detected=True)
    engine.log_event("fire", detected=True)

    assert len(published) == 1