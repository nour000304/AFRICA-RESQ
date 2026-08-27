import json
import threading

from src.data_engine import DataEngine
from src.fake_sensor import FakeSensorEngine


class SensorSimulator:
    """Background thread that continuously generates fake sensor telemetry
    and writes it into the shared state file (plus an in-memory history),
    while persisting every detection to the DataEngine."""

    def __init__(
        self,
        state_file,
        interval=2.0,
        max_history=200,
        data_engine=None,
        event_bus=None
    ):
        self.state_file = state_file
        self.interval = interval
        self.max_history = max_history

        self.engine = FakeSensorEngine()
        self.data_engine = data_engine or DataEngine()
        self.event_bus = event_bus

        self._thread = None
        self._stop = threading.Event()

        self.running = False
        self.snapshot = None
        self.history = []

    # ------------------------------------------------------------
    # Control
    # ------------------------------------------------------------

    def start(self):
        if self.running:
            return True

        self._stop.clear()
        self.running = True

        self._thread = threading.Thread(
            target=self._loop,
            daemon=True
        )
        self._thread.start()

        return True

    def stop(self):
        if not self.running:
            return True

        self._stop.set()
        self.running = False

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        return True

    # ------------------------------------------------------------
    # Inner loop
    # ------------------------------------------------------------

    def _loop(self):
        while not self._stop.is_set():
            self.step()
            self._stop.wait(self.interval)

    def step(self):
        state, snapshot = self.engine.next()

        # Persist this snapshot (telemetry + active detections) to the store
        snapshot["source"] = "simulator"
        self.data_engine.log_snapshot(snapshot)

        self.snapshot = snapshot
        self.history.append(snapshot)

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        full = self._load_state()

        # Merge simulated detection/risk state into the live file so
        # the existing dashboard endpoints show moving data
        full.update(state)
        full["sensor_timestamp"] = snapshot["timestamp"]
        full["sensors"] = snapshot
        full["sensor_history"] = self.history[-20:]

        self._write_state(full)

        # Push the live snapshot to dashboards (SSE bus)
        if self.event_bus:
            self.event_bus.publish_state(snapshot)

    # ------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------

    def _load_state(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_state(self, data):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("SIMULATOR WRITE ERROR:", e)