"""The HTTP surface, exercised over the wire rather than by calling the functions.

A route can be correct and still be unreachable -- wrong path, wrong status, a parameter
FastAPI never binds. These are the checks that a client written against docs/API.md gets
what the document promised.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from server import config, shelters
from server.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------- what already worked
def test_the_endpoints_that_existed_before_the_merge_still_answer(client):
    for path in ("/api/state", "/api/health", "/api/status",
                 "/api/detection", "/api/risk", "/api/full"):
        assert client.get(path).status_code == 200, path


def test_the_grid_block_carries_the_anchor(client):
    grid = client.get("/api/state").json()["grid"]
    assert grid["cols"] and grid["rows"] and grid["cell_m"]      # what was always there
    assert grid["anchor"]["lat"] == config.ORIGIN_LAT            # what the merge added
    assert "sw" in grid and "ne" in grid


# -------------------------------------------------------------------------- shelters
def test_the_city_list_is_served(client):
    body = client.get("/api/shelters/cities").json()
    assert body["count"] == len(shelters.CITIES)
    assert "Cairo" in body["cities"]


def test_shelters_can_be_filtered_by_city_over_http(client):
    body = client.get("/api/shelters", params={"city": "luxor"}).json()
    assert body["count"] > 0
    assert all(s["city"] == "Luxor" for s in body["shelters"])


def test_nearest_shelter_with_no_coordinate_answers_about_this_incident(client):
    body = client.get("/api/nearest_shelter", params={"limit": 3}).json()
    assert body["success"] and body["origin"] == "mission_anchor"
    assert body["latitude"] == config.ORIGIN_LAT
    assert len(body["nearest"]) == 3


def test_nearest_shelter_takes_a_coordinate_when_it_is_given_one(client):
    stadium = shelters.get("CAI-01")
    body = client.get("/api/nearest_shelter",
                      params={"latitude": stadium["lat"], "longitude": stadium["lon"],
                              "limit": 1}).json()
    assert body["origin"] == "given"
    assert body["nearest"][0]["shelter"]["id"] == "CAI-01"


def test_a_coordinate_outside_the_region_is_refused_rather_than_answered(client):
    """Answering Paris with a shelter in Cairo is worse than saying no."""
    r = client.get("/api/nearest_shelter", params={"latitude": 48.8566, "longitude": 2.3522})
    assert r.status_code == 422
    assert r.json()["success"] is False


def test_one_shelter_by_id(client):
    assert client.get("/api/shelter/CAI-01").json()["shelter"]["name"]
    assert client.get("/api/shelter/NOPE-99").status_code == 404


def test_location_validates_a_coordinate(client):
    assert client.get("/api/location", params={"latitude": 30.0, "longitude": 31.0}).json()["valid"]
    assert not client.get("/api/location",
                          params={"latitude": 48.85, "longitude": 2.35}).json()["valid"]


def test_location_with_nothing_given_is_invalid_not_the_origin(client):
    """Rule 1: absent is not zero, and it is not the anchor either."""
    assert client.get("/api/location").json()["valid"] is False


# ---------------------------------------------------------------------------- the record
@pytest.fixture
def field_client():
    """A client on the private network, which is what a rover or a field system is.

    The default TestClient presents the host "testclient", which is not an address at
    all, so config.is_local refuses it -- correctly: a deployment with no token set must
    fail closed rather than trust an unrecognised caller.
    """
    with TestClient(app, client=("127.0.0.1", 51234)) as c:
        yield c


def _settle(client, tries=50):
    """Recording is a queue and a writer task; give it a moment to reach the disk."""
    for _ in range(tries):
        if client.get("/api/events").json()["count"]:
            return
        time.sleep(0.02)


def test_an_outside_system_can_file_a_detection(field_client):
    posted = field_client.post("/api/events", json={
        "type": "fire", "source": "dashboard", "detected": True, "confidence": 0.9,
        "latitude": 30.0477, "longitude": 31.2336, "payload": {"zone": "A1"}})
    assert posted.status_code == 200 and posted.json()["ok"]

    _settle(field_client)
    row = field_client.get("/api/events", params={"type": "fire"}).json()["events"][0]
    assert row["source"] == "dashboard" and row["detected"] is True
    assert row["confidence"] == 0.9
    assert row["payload"]["zone"] == "A1"
    assert row["ts_iso"].endswith("+00:00")


def test_filing_a_detection_is_gated_the_way_pushing_a_frame_is(client):
    """A POST here puts a detection on a live rescue record. An unrecognised caller with
    no token does not get to invent one."""
    assert client.post("/api/events", json={"type": "fire"}).status_code == 401


def test_an_event_with_no_kind_is_refused(field_client):
    assert field_client.post("/api/events", json={"source": "x"}).status_code == 400
    assert field_client.post("/api/events", json=["not", "an", "object"]).status_code == 400


def test_an_absent_verdict_stays_absent(field_client):
    """Rule 1, over HTTP: not saying whether you detected something is not saying no."""
    field_client.post("/api/events", json={"type": "telemetry", "source": "probe"})
    _settle(field_client)
    row = field_client.get("/api/events", params={"type": "telemetry"}).json()["events"][0]
    assert row["detected"] is None
    assert row["confidence"] is None and row["latitude"] is None


def test_a_garbled_reading_becomes_null_rather_than_a_500(field_client):
    posted = field_client.post("/api/events", json={
        "type": "smoke", "confidence": "n/a", "latitude": "", "payload": "not-a-dict"})
    assert posted.status_code == 200
    _settle(field_client)
    row = field_client.get("/api/events", params={"type": "smoke"}).json()["events"][0]
    assert row["confidence"] is None and row["latitude"] is None and row["payload"] is None


def test_events_can_be_filtered_and_counted_over_http(field_client):
    for kind in ("fire", "fire", "smoke"):
        field_client.post("/api/events", json={"type": kind, "source": "probe",
                                               "detected": True})
    _settle(field_client)
    assert field_client.get("/api/events", params={"type": "fire"}).json()["count"] == 2
    assert field_client.get("/api/events", params={"limit": 1}).json()["count"] == 1

    stats = field_client.get("/api/events/stats").json()
    assert stats["by_type"]["fire"] == 2 and stats["recording"] is True
    assert field_client.get("/api/events/export").json()["count"] == 3


def test_latest_carries_the_rows_the_state_and_the_counts(field_client):
    field_client.post("/api/events", json={"type": "fire", "detected": True})
    _settle(field_client)
    body = field_client.get("/api/events/latest").json()
    assert body["events"] and body["stats"]["total"] >= 1
    # The state block is the /api/full projection, so a client cannot see two risk scores.
    assert set(body["state"]) >= {"fire", "smoke", "survivor", "risk", "recommendation"}


def test_the_stream_opens_by_saying_what_it_is(tmp_path, monkeypatch):
    """Pulled straight off the generator rather than through TestClient.

    TestClient drives the app through a portal thread and never returns from an endpoint
    whose body is an endless generator, which is exactly what a live feed is. The thing
    worth asserting is what the feed emits, and that is right here.
    """
    from server import main, recorder as recording

    async def go():
        rec = recording.Recorder(recording.open_ledger(str(tmp_path / "sse")),
                                 throttle_s=0.0)
        await rec.start()
        monkeypatch.setattr(main, "recorder", rec)

        response = await main.api_events_stream()
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"    # nginx must not buffer it

        body = response.body_iterator.__aiter__()
        first = await asyncio.wait_for(body.__anext__(), timeout=5.0)

        rec.record("fire", source="probe", detected=True, confidence=0.9, throttle=False)
        await asyncio.wait_for(rec.queue.join(), timeout=5.0)
        second = await asyncio.wait_for(body.__anext__(), timeout=5.0)

        await body.aclose()
        await rec.stop()
        return first, second

    first, second = asyncio.run(go())

    assert first.startswith("data: ") and first.endswith("\n\n")
    hello = json.loads(first[6:])
    assert hello["kind"] == "hello" and hello["recording"] is True and hello["mission_id"]

    event = json.loads(second[6:])
    assert event["kind"] == "event" and event["event_type"] == "fire"
    assert event["id"] == 1, "a listener gets the stored row, with the id it was given"


def test_a_listener_is_let_go_of_when_the_feed_closes(tmp_path, monkeypatch):
    """A browser that navigates away must not leave a queue behind for the rest of the run."""
    from server import main, recorder as recording

    async def go():
        rec = recording.Recorder(recording.open_ledger(str(tmp_path / "sse")))
        await rec.start()
        monkeypatch.setattr(main, "recorder", rec)

        body = (await main.api_events_stream()).body_iterator.__aiter__()
        await asyncio.wait_for(body.__anext__(), timeout=5.0)
        during = len(rec.subscribers)
        await body.aclose()
        after = len(rec.subscribers)
        await rec.stop()
        return during, after

    during, after = asyncio.run(go())
    assert during == 1 and after == 0


# --------------------------------------------------------------------------- routing
def test_a_route_is_served_and_says_where_it_came_from(client):
    body = client.get("/api/route", params={
        "start_lat": 30.0444, "start_lon": 31.2357,
        "end_lat": 30.069113, "end_lon": 31.312407}).json()
    assert body["success"] and body["distance_km"] > 0
    assert body["source"] in ("osrm", "straight_line_estimate")


def test_a_route_out_of_the_region_is_refused(client):
    r = client.get("/api/route", params={"start_lat": 30.0444, "start_lon": 31.2357,
                                         "end_lat": 48.8566, "end_lon": 2.3522})
    assert r.status_code == 422


def test_a_route_to_a_shelter_needs_only_the_shelter(client):
    body = client.get("/api/route/shelter/CAI-01").json()
    assert body["success"]
    assert body["shelter"]["id"] == "CAI-01"
    assert body["from"]["origin"] == "mission_anchor"
    assert client.get("/api/route/shelter/NOPE-99").status_code == 404
