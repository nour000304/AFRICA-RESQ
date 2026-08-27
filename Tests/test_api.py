import asyncio
import json
import time

from fastapi.testclient import TestClient

from src.api import app, events_stream


def _client():
    # Entering the context starts the lifespan -> sensor simulator
    return TestClient(app)


def test_root():
    with _client() as client:
        res = client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert data["system"] == "AFRICA RESQ AI"
        assert data["region"] == "Egypt"
        assert data["simulation"]["enabled"] is True


def test_status():
    with _client() as client:
        res = client.get("/api/status")
        assert res.status_code == 200
        assert res.json()["status"] == "online"


def test_health():
    with _client() as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["simulation_running"] is True


def test_full_state_has_sensor_telemetry():
    with _client() as client:
        time.sleep(0.5)  # let simulator tick a few times
        res = client.get("/api/full")
        assert res.status_code == 200
        data = res.json()
        assert "fire" in data and "smoke" in data and "risk" in data
        assert "sensors" in data
        assert "sensor_history" in data


def test_detection():
    with _client() as client:
        res = client.get("/api/detection")
        assert res.status_code == 200
        data = res.json()
        for key in ("fire", "smoke", "survivor"):
            assert key in data


def test_risk():
    with _client() as client:
        res = client.get("/api/risk")
        assert res.status_code == 200
        data = res.json()
        assert data["level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_priority():
    with _client() as client:
        res = client.get("/api/priority")
        assert res.status_code == 200
        assert "priority" in res.json()


def test_location_valid_cairo():
    with _client() as client:
        res = client.get("/api/location?latitude=30.0444&longitude=31.2357")
        assert res.json()["valid"] is True
        assert res.json()["country"] == "Egypt"


def test_location_invalid_outside_egypt():
    with _client() as client:
        res = client.get("/api/location?latitude=31.63&longitude=-7.99")
        assert res.json()["valid"] is False


def test_shelters_list():
    with _client() as client:
        res = client.get("/api/shelters")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["count"] >= 20


def test_shelters_filter_by_city():
    with _client() as client:
        res = client.get("/api/shelters?city=Alexandria")
        data = res.json()
        assert data["success"] is True
        assert len(data["shelters"]) > 0
        assert all(s["city"] == "Alexandria" for s in data["shelters"])


def test_shelter_cities():
    with _client() as client:
        res = client.get("/api/shelters/cities")
        data = res.json()
        assert data["success"] is True
        assert "Cairo" in data["cities"]


def test_nearest_shelter():
    with _client() as client:
        res = client.get("/api/nearest_shelter?latitude=30.0477&longitude=31.2336&limit=3")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["nearest"]) == 3
        assert "distance_km" in data["nearest"][0]
        assert "shelter" in data["nearest"][0]


def test_nearest_shelter_outside_egypt():
    with _client() as client:
        res = client.get("/api/nearest_shelter?latitude=48.85&longitude=2.35")
        data = res.json()
        assert data["success"] is False


def test_shelter_by_id():
    with _client() as client:
        res = client.get("/api/shelter/ALX-01")
        data = res.json()
        assert data["success"] is True
        assert data["shelter"]["name"] == "Alexandria Stadium"


def test_sensor_endpoint():
    with _client() as client:
        time.sleep(0.5)
        res = client.get("/api/sensor")
        assert res.status_code == 200
        data = res.json()
        assert data.get("simulated") is True
        assert "environment" in data
        assert "detections" in data


def test_sensor_history():
    with _client() as client:
        time.sleep(0.5)
        res = client.get("/api/sensor/history?limit=10")
        data = res.json()
        assert data["success"] is True
        assert len(data["history"]) > 0


def test_simulation_control():
    with _client() as client:
        time.sleep(0.3)

        res = client.get("/api/simulation/status")
        assert res.json()["running"] is True

        res = client.post("/api/simulation/stop")
        assert res.json()["running"] is False

        res = client.get("/api/simulation/status")
        assert res.json()["running"] is False

        res = client.post("/api/simulation/start")
        assert res.json()["running"] is True


def test_incident_endpoint():
    with _client() as client:
        res = client.post("/api/incident?latitude=31.2001&longitude=29.9187")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["latitude"] == 31.2001


def test_incident_outside_egypt_rejected():
    with _client() as client:
        res = client.post("/api/incident?latitude=48.85&longitude=2.35")
        assert res.json()["success"] is False


def test_map_page():
    with _client() as client:
        res = client.get("/map")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]


def test_health_reports_data_store():
    with _client() as client:
        time.sleep(0.5)
        res = client.get("/api/health")
        data = res.json()
        assert data["status"] == "healthy"
        assert "data_store" in data
        assert data["data_store"]["database"].endswith(".db")
        assert data["data_store"]["jsonl"].endswith(".jsonl")
        assert data["data_store"]["total_events"] >= 1


def test_simulator_detections_are_persisted():
    with _client() as client:
        time.sleep(0.8)
        res = client.get("/api/events/stats")
        data = res.json()
        assert data["success"] is True
        assert data["stats"]["total"] >= 1
        assert data["stats"]["by_type"].get("telemetry", 0) >= 1


def test_events_latest():
    with _client() as client:
        time.sleep(0.5)
        res = client.get("/api/events/latest")
        data = res.json()
        assert data["success"] is True
        assert data["total_events"] >= 1
        assert "latest_snapshot" in data
        assert isinstance(data["latest_events"], list)


def test_events_stream_pushes_state_frames():
    # TestClient.stream() deadlocks on an *infinite* streaming response in
    # this starlette version, so we drive the StreamingResponse's
    # body_iterator directly under asyncio — same data flow, no deadlock.
    with _client() as client:
        seen = []

        async def consume():
            response = await events_stream()
            assert response.media_type == "text/event-stream"

            async for chunk in response.body_iterator:
                text = chunk if isinstance(chunk, str) else chunk.decode()
                for line in text.splitlines():
                    if not line.startswith("data: "):
                        continue
                    payload = json.loads(line[6:])
                    seen.append(payload.get("kind"))

                if {"hello", "state", "event"} <= set(seen):
                    return

        asyncio.run(consume())

        # The simulator pushes snapshots (state) and every stored row is an
        # (event), so both must appear after connect without any request.
        assert "state" in seen
        assert "event" in seen
        assert "hello" in seen


def test_ingest_and_query_event():
    with _client() as client:
        res = client.post(
            "/api/events",
            json={
                "type": "fire",
                "source": "test_cam",
                "detected": True,
                "confidence": 0.96,
                "latitude": 30.0477,
                "longitude": 31.2336,
                "payload": {"zone": "A1"}
            }
        )
        data = res.json()
        assert data["success"] is True
        assert data["stored"] is True

        res = client.get("/api/events?type=fire&source=test_cam")
        events = res.json()["events"]
        assert len(events) == 1
        assert events[0]["confidence"] == 0.96
        assert events[0]["latitude"] == 30.0477


def test_events_query_and_export():
    with _client() as client:
        time.sleep(0.5)
        res = client.get("/api/events?limit=100")
        data = res.json()
        assert data["success"] is True
        assert data["count"] >= 1

        res = client.get("/api/events/export")
        export = res.json()
        assert export["success"] is True
        assert export["count"] >= 1


def test_route_fallback():
    with _client() as client:
        res = client.get(
            "/api/route?start_lat=30.0444&start_lon=31.2357"
            "&end_lat=30.0691&end_lon=31.3124"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["distance_km"] > 0