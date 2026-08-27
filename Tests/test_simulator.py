import json
import os
import tempfile

from simulator import SensorSimulator


def _make_simulator(tmpdir, interval=0.0):
    state_file = os.path.join(tmpdir, "state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({}, f)
    return SensorSimulator(
        state_file=state_file,
        interval=interval,
        max_history=5
    ), state_file


def test_step_writes_state_file(tmpdir):
    sim, state_file = _make_simulator(str(tmpdir))
    sim.step()

    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "fire" in data
    assert "smoke" in data
    assert "sensor_timestamp" in data
    assert "sensors" in data
    assert "sensor_history" in data


def test_history_is_bounded(tmpdir):
    sim, _ = _make_simulator(str(tmpdir))
    for _ in range(20):
        sim.step()
    assert len(sim.history) <= 5


def test_start_and_stop(tmpdir):
    sim, _ = _make_simulator(str(tmpdir), interval=0.01)

    sim.start()
    assert sim.running is True
    assert sim._thread is not None

    sim.stop()
    assert sim.running is False

    sim.start()
    sim.stop()