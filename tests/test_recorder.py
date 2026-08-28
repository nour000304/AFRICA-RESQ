"""The mission record.

The claims: a detection is written to both stores, an unmeasured reading stays null all
the way to disk, the camera frame never lands in the ledger, a fire that burns for an hour
is not thirty thousand rows, and none of it can take the server down.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest

from server import geo
from server.recorder import Ledger, Recorder, Throttle, iso, open_ledger, to_epoch

from conftest import CLEAN_AIR, frame


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def ledger(tmp_path):
    led = Ledger(str(tmp_path / "rec"))
    yield led
    led.close()


def row(**kw):
    base = {"event_type": "fire", "source": "camera", "detected": True,
            "confidence": 0.9, "latitude": 30.0, "longitude": 31.0,
            "payload": {"zone": "D3"}, "ts": 1_700_000_000.0,
            "ts_iso": iso(1_700_000_000.0)}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- the store
def test_a_row_lands_in_both_stores_with_the_same_id(ledger):
    stored = ledger.write(row())
    assert stored["id"] == 1

    lines = ledger.jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == stored["id"]

    assert ledger.query()[0]["id"] == stored["id"]


def test_the_jsonl_is_append_only_and_one_object_a_line(ledger):
    for i in range(3):
        ledger.write(row(confidence=0.1 * i))
    lines = ledger.jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 3
    assert [json.loads(l)["id"] for l in lines] == [1, 2, 3]


def test_an_unmeasured_reading_stays_null_all_the_way_to_disk(ledger):
    """Rule 1 of this codebase, at the last place it could quietly break.

    A row saying 0 ppm CO and a row saying nobody measured the CO have to stay different
    rows forever, or the record is worse than having none.
    """
    ledger.write(row(event_type="telemetry", detected=None, confidence=None,
                     latitude=None, longitude=None))
    stored = ledger.query()[0]
    assert stored["detected"] is None, "not a detection row is not a negative detection"
    assert stored["confidence"] is None
    assert stored["latitude"] is None and stored["longitude"] is None


def test_a_negative_detection_is_false_and_not_null(ledger):
    ledger.write(row(detected=False))
    assert ledger.query()[0]["detected"] is False


def test_zero_confidence_is_a_reading_and_survives(ledger):
    ledger.write(row(confidence=0.0))
    assert ledger.query()[0]["confidence"] == 0.0


def test_timestamps_are_utc_and_offset_aware(ledger):
    stored = ledger.write(row())
    assert stored["ts_iso"].endswith("+00:00")


def test_an_unserialisable_payload_does_not_lose_the_row(ledger):
    """A row that cannot be written is a row nobody knows was missing."""
    ledger.write(row(payload={"model": object()}))
    assert len(ledger.query()) == 1


def test_query_filters_by_type_source_and_window(ledger):
    ledger.write(row(event_type="fire", source="camera", ts=100.0, ts_iso=iso(100.0)))
    ledger.write(row(event_type="smoke", source="camera", ts=200.0, ts_iso=iso(200.0)))
    ledger.write(row(event_type="fire", source="operator", ts=300.0, ts_iso=iso(300.0)))

    assert len(ledger.query(event_type="fire")) == 2
    assert len(ledger.query(source="operator")) == 1
    assert len(ledger.query(start=150.0)) == 2
    assert len(ledger.query(end=150.0)) == 1
    assert len(ledger.query(start=150.0, end=250.0)) == 1


def test_query_is_newest_first_and_honours_limit_and_offset(ledger):
    for t in (100.0, 200.0, 300.0):
        ledger.write(row(ts=t, ts_iso=iso(t)))
    assert [r["ts"] for r in ledger.query()] == [300.0, 200.0, 100.0]
    assert [r["ts"] for r in ledger.query(limit=1)] == [300.0]
    assert [r["ts"] for r in ledger.query(limit=1, offset=1)] == [200.0]


def test_a_window_given_as_a_date_works_like_one_given_as_an_epoch():
    assert to_epoch("1970-01-01T00:00:00+00:00") == 0.0
    assert to_epoch("1970-01-01") == 0.0
    assert to_epoch(1_700_000_000.0) == 1_700_000_000.0
    assert to_epoch("not a date") is None
    assert to_epoch(None) is None


def test_stats_count_what_was_seen_and_what_was_confirmed(ledger):
    ledger.write(row(event_type="fire", detected=True))
    ledger.write(row(event_type="fire", detected=False))
    ledger.write(row(event_type="telemetry", source="rover", detected=None))

    s = ledger.stats()
    assert s["total"] == 3
    assert s["by_type"] == {"fire": 2, "telemetry": 1}
    assert s["by_source"] == {"camera": 2, "rover": 1}
    assert s["detected_by_type"]["fire"] == {"total": 2, "detected": 1}
    assert s["last_event"]["ts_iso"].endswith("+00:00")


def test_stats_on_an_empty_ledger_are_zero_not_an_error(ledger):
    assert ledger.stats()["total"] == 0
    assert ledger.stats()["last_event"] is None


def test_export_is_oldest_first_so_a_pipeline_can_replay_it(ledger):
    for t in (300.0, 100.0, 200.0):
        ledger.write(row(ts=t, ts_iso=iso(t)))
    assert [r["ts"] for r in ledger.export()] == [100.0, 200.0, 300.0]


def test_the_store_is_indexed_on_what_it_is_queried_by(ledger):
    names = {r[0] for r in ledger._db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert {"idx_events_type", "idx_events_ts", "idx_events_src"} <= names


# ------------------------------------------------------------------------- the throttle
def test_identical_events_collapse_inside_the_window():
    t = Throttle(2.0)
    assert t.allows("fire", 100.0) is True
    assert t.allows("fire", 101.0) is False
    assert t.allows("fire", 102.5) is True


def test_a_change_of_verdict_is_never_collapsed():
    """The moment a hazard clears is the moment the record must not be throttling."""
    t = Throttle(60.0)
    assert t.allows(("fire", "camera", True), 100.0) is True
    assert t.allows(("fire", "camera", False), 100.1) is True


def test_a_window_of_zero_records_everything():
    t = Throttle(0.0)
    assert all(t.allows("fire", 100.0) for _ in range(5))


# -------------------------------------------------------------------------- the recorder
def test_a_frame_is_recorded_as_telemetry_plus_one_row_per_detection(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        rec.record_frame(frame(detections=[
            {"cls": "person", "conf": 0.7, "bbox": [0.1, 0.1, 0.2, 0.3]},
            {"cls": "fire", "conf": 0.9, "bbox": [0.4, 0.4, 0.1, 0.1]}]))
        rows = await _settled(rec)
        await rec.stop()
        return rows

    rows = run(go())
    assert {r["event_type"] for r in rows} == {"telemetry", "person", "fire"}
    assert [r["detected"] for r in rows if r["event_type"] == "person"] == [True]


def test_the_camera_frame_never_lands_in_the_ledger(tmp_path):
    """A base64 JPEG at 8 Hz is gigabytes an hour, and it buries the readings beside it."""
    jpeg = "data:image/jpeg;base64," + ("A" * 4096)

    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        f = frame()
        f.frame_jpeg = jpeg
        rec.record_frame(f)
        rows = await _settled(rec)
        await rec.stop()
        return rows

    dumped = json.dumps(run(go()))
    assert "base64" not in dumped
    assert len(dumped) < 4096


def test_an_unread_sensor_is_null_in_the_record_not_zero(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        rec.record_frame(frame(atmosphere={"temp_c": 21.0}))
        rows = await _settled(rec)
        await rec.stop()
        return rows

    atmo = [r for r in run(go()) if r["event_type"] == "telemetry"][0]["payload"]["atmosphere"]
    assert atmo["temp_c"] == 21.0
    for unread in ("co_ppm", "lel_pct", "o2_pct", "pm25_ugm3"):
        assert atmo[unread] is None, "%s was never measured and must not read as 0" % unread


def test_a_recorded_frame_carries_the_cell_as_a_coordinate(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        rec.record_frame(frame(zone="D3"))
        rows = await _settled(rec)
        await rec.stop()
        return rows

    telemetry = [r for r in run(go()) if r["event_type"] == "telemetry"][0]
    expected = geo.latlon_of_zone("D3")
    assert telemetry["latitude"] == pytest.approx(expected[0])
    assert telemetry["payload"]["zone"] == "D3"


def test_a_burning_fire_is_not_thirty_thousand_rows(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=60.0)
        await rec.start()
        for _ in range(50):
            rec.record_frame(frame(detections=[
                {"cls": "fire", "conf": 0.9, "bbox": [0.4, 0.4, 0.1, 0.1]}]))
        rows = await _settled(rec)
        await rec.stop()
        return rows

    rows = run(go())
    assert len([r for r in rows if r["event_type"] == "fire"]) == 1
    assert len([r for r in rows if r["event_type"] == "telemetry"]) == 1


def test_an_explicit_report_is_never_throttled_away(tmp_path):
    """A rover's telemetry repeats. An operator filing a detection by hand does not, and
    dropping one silently would lose the only record of it."""
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=60.0)
        await rec.start()
        for _ in range(3):
            rec.record("fire", source="operator", detected=True, throttle=False)
        rows = await _settled(rec)
        await rec.stop()
        return rows

    assert len(run(go())) == 3


def test_recording_before_start_is_a_no_op_and_not_a_crash(tmp_path):
    rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
    assert rec.record("fire", source="camera") is None
    rec.record_frame(frame())


def test_a_store_that_cannot_be_opened_turns_recording_off_rather_than_the_board(tmp_path):
    """A read-only volume must cost the record, never the incident on screen."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    said = []
    rec = Recorder(open_ledger(str(blocker / "record"), on_error=said.append))
    assert rec.enabled is False
    assert said, "it must say why it is not recording"
    assert rec.record("fire") is None
    rec.record_frame(frame())


def test_a_listener_is_told_about_a_row_once_it_is_written(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        channel = rec.subscribe()
        rec.record("fire", source="camera", detected=True, confidence=0.9)
        await _settled(rec)
        msg = json.loads(channel.get_nowait())
        await rec.stop()
        return msg

    msg = run(go())
    assert msg["kind"] == "event" and msg["event_type"] == "fire"
    assert msg["id"] == 1, "a listener gets the stored row, with its id"


def test_a_listener_that_stopped_reading_never_costs_the_ledger_a_row(tmp_path):
    """A browser that walked away holds an open queue nobody drains. It gets trimmed;
    the record does not."""
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        abandoned = rec.subscribe()                # nothing ever reads this
        for i in range(400):                       # far deeper than a subscriber queue
            rec.record("fire", source="s%d" % i, detected=True, throttle=False)
        rows = await _settled(rec)
        await rec.stop()
        return abandoned.qsize(), rec.written, len(rows)

    queued, written, stored = run(go())
    assert written == 400 and stored == 400, "every row still reached the ledger"
    assert queued <= 256, "the abandoned listener is capped, never grown without bound"


def test_a_listener_that_keeps_up_sees_every_row(tmp_path):
    async def go():
        rec = Recorder(open_ledger(str(tmp_path / "r")), throttle_s=0.0)
        await rec.start()
        channel = rec.subscribe()
        seen = []
        for i in range(20):
            rec.record("fire", source="s%d" % i, detected=True, throttle=False)
            await _settled(rec)
            while not channel.empty():
                seen.append(json.loads(channel.get_nowait()))
        await rec.stop()
        return seen

    seen = run(go())
    assert [m["id"] for m in seen] == list(range(1, 21))


async def _settled(rec, timeout=5.0):
    await asyncio.wait_for(rec.queue.join(), timeout=timeout)
    return await rec.query(limit=500)
