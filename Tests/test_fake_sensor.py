import time

from fake_sensor import FakeSensorEngine


def _run_ticks(ticks=60, seed=42):
    engine = FakeSensorEngine(seed=seed, incident_lat=30.0977, incident_lon=31.1887)
    states = []
    snapshots = []
    for _ in range(ticks):
        state, snapshot = engine.next()
        states.append(state)
        snapshots.append(snapshot)
    return states, snapshots


def test_snapshot_schema():
    _, snapshots = _run_ticks(2)
    snapshot = snapshots[-1]

    assert snapshot["simulated"] is True
    assert snapshot["tick"] >= 1
    assert "timestamp" in snapshot
    assert "vehicle" in snapshot
    assert "environment" in snapshot
    assert "detections" in snapshot
    assert "thermal" in snapshot
    assert "risk" in snapshot

    # GPS near incident
    assert 30.05 <= snapshot["vehicle"]["gps"]["lat"] <= 30.14

    assert 0 <= snapshot["vehicle"]["battery_pct"] <= 100
    assert 22 <= snapshot["environment"]["temperature_c"] <= 55
    assert 0 <= snapshot["environment"]["gas_ppm"] <= 500
    assert 0 <= snapshot["environment"]["smoke_density_pct"] <= 100


def test_confidences_within_range():
    _, snapshots = _run_ticks(60)
    for snapshot in snapshots:
        assert 0 <= snapshot["detections"]["fire"]["confidence"] <= 1
        assert 0 <= snapshot["detections"]["smoke"]["confidence"] <= 1
        assert 0 <= snapshot["detections"]["survivor"]["confidence"] <= 1


def test_risk_consistent_with_detections():
    states, _ = _run_ticks(200, seed=7)

    for state in states:
        fire = state["fire"]["detected"]
        smoke = state["smoke"]["detected"]
        risk = state["risk"]

        if fire and smoke:
            assert risk["level"] == "HIGH"
            assert risk["score"] >= 80
            assert state["priority"] == "CRITICAL"
        elif fire:
            assert risk["level"] == "HIGH"
            assert risk["score"] >= 80
        elif smoke:
            assert risk["level"] in ("MEDIUM", "HIGH")
        else:
            # no fire/smoke -> LOW or MEDIUM (temp/gas bumps), never HIGH
            assert risk["level"] in ("LOW", "MEDIUM")
            assert state["priority"] is None


def test_simulation_is_lively_over_time():
    _, snapshots = _run_ticks(60)
    temps = [s["environment"]["temperature_c"] for s in snapshots]
    assert max(temps) - min(temps) > 0


def test_eventually_detects_something():
    states, _ = _run_ticks(400, seed=3)
    any_event = any(
        s["fire"]["detected"] or s["smoke"]["detected"] or s["survivor"]["detected"]
        for s in states
    )
    assert any_event


def test_set_incident_recenters():
    engine = FakeSensorEngine(seed=1)
    engine.set_incident(31.2001, 29.9187)  # Alexandria
    _, snapshot = engine.next()
    lat = snapshot["vehicle"]["gps"]["lat"]
    lon = snapshot["vehicle"]["gps"]["lon"]
    assert 31.14 <= lat <= 31.25
    assert 29.86 <= lon <= 29.97


def test_timestamp_is_epoch_seconds():
    _, snapshots = _run_ticks(1)
    ts = snapshots[-1]["timestamp"]
    assert abs(ts - time.time()) < 60