import math
import random
import time


def _clamp(value, low, high):
    return max(low, min(high, value))


def _risk_for(fire_detected, smoke_detected, temp, gas, smoke):
    """Mirror the risk logic used by the live pipeline."""
    if fire_detected and smoke_detected:
        score = 100
        level = "HIGH"
    elif fire_detected:
        score = 80
        level = "HIGH"
    elif smoke_detected:
        score = 50
        level = "MEDIUM"
    else:
        score = 0
        level = "LOW"

    # Rising ambient temperature/gas/smoke always lifts risk,
    # but without an actual fire it should stay at MEDIUM.
    if level == "LOW":
        if temp >= 42:
            score = 50
            level = "MEDIUM"
        elif gas >= 300 or smoke >= 65:
            score = 50
            level = "MEDIUM"

    return {"score": score, "level": level}


class FakeSensorEngine:
    """Generates realistic simulated sensor readings for prototyping.

    The values evolve over time with a random walk so the dashboard
    shows live-changing telemetry without needing real hardware.
    """

    def __init__(self, seed=None, incident_lat=30.0444, incident_lon=31.2357):
        self.rng = random.Random(seed) if seed is not None else random

        self.incident_lat = incident_lat
        self.incident_lon = incident_lon

        # Rover state (random walk state)
        self.tick = 0
        self.lat = incident_lat
        self.lon = incident_lon
        self.battery = 82.0
        self.temp = 32.0
        self.gas = 25.0
        self.smoke = 5.0
        self.humidity = 45.0
        self.wind = 8.0
        self.wind_dir = 45.0
        self.tilt = 2.0

        # Event levels 0..1
        self.fire_level = 0.0
        self.smoke_level = 0.0
        self.survivor_level = 0.0

        # Event timers in ticks
        self.fire_remaining = 0
        self.smoke_remaining = 0
        self.survivor_remaining = 0

    def set_incident(self, lat, lon):
        self.incident_lat = lat
        self.incident_lon = lon
        self.lat = lat
        self.lon = lon

    def _maybe_start_events(self):
        # Occasionally start a fire/smoke "incident" so the demo is lively
        if self.fire_remaining <= 0 and self.rng.random() < 0.05:
            self.fire_remaining = self.rng.randint(6, 15)

        if self.smoke_remaining <= 0 and self.rng.random() < 0.10:
            self.smoke_remaining = self.rng.randint(8, 20)

        if self.survivor_remaining <= 0 and self.rng.random() < 0.07:
            self.survivor_remaining = self.rng.randint(4, 10)

    def next(self):
        """Advance the simulation one tick and return (state, snapshot)."""
        self.tick += 1
        self._maybe_start_events()

        # ----------------------------- rover -----------------------------
        self.battery = _clamp(
            self.battery - self.rng.uniform(0.01, 0.12),
            5,
            100
        )

        # Slow wander around the incident point
        self.lat = _clamp(
            self.lat + self.rng.uniform(-0.004, 0.004),
            self.incident_lat - 0.05,
            self.incident_lat + 0.05
        )
        self.lon = _clamp(
            self.lon + self.rng.uniform(-0.004, 0.004),
            self.incident_lon - 0.05,
            self.incident_lon + 0.05
        )

        self.tilt = _clamp(
            self.tilt + self.rng.uniform(-0.5, 0.5),
            0,
            10
        )

        # ------------------------- environment ---------------------------
        fire_active = self.fire_remaining > 0
        smoke_active = self.smoke_remaining > 0

        self.temp = _clamp(
            self.temp
            + self.rng.uniform(-0.4, 0.5)
            + (2.0 if fire_active else 0)
            - (0.2 if self.temp > 46 else 0),
            22,
            55
        )

        self.gas = _clamp(
            self.gas
            + self.rng.uniform(-8, 12)
            + (60.0 if fire_active else 0),
            0,
            500
        )

        self.smoke = _clamp(
            self.smoke
            + self.rng.uniform(-6, 7)
            + (30.0 if smoke_active or fire_active else 0),
            0,
            100
        )

        self.humidity = _clamp(
            self.humidity + self.rng.uniform(-1.5, 1.5),
            15,
            90
        )

        self.wind = _clamp(
            self.wind + self.rng.uniform(-1, 1),
            0,
            35
        )

        self.wind_dir = (self.wind_dir + self.rng.uniform(-15, 15)) % 360

        # ------------------------- event levels --------------------------
        target_fire = 1.0 if fire_active else 0.0
        target_smoke = 1.0 if (smoke_active or fire_active) else 0.0
        target_survivor = 1.0 if self.survivor_remaining > 0 else 0.0

        self.fire_level = _clamp(
            self.fire_level + (target_fire - self.fire_level) * 0.35,
            0,
            1
        )
        self.smoke_level = _clamp(
            self.smoke_level + (target_smoke - self.smoke_level) * 0.35,
            0,
            1
        )
        self.survivor_level = _clamp(
            self.survivor_level + (target_survivor - self.survivor_level) * 0.3,
            0,
            1
        )

        if self.fire_remaining > 0:
            self.fire_remaining -= 1
        if self.smoke_remaining > 0:
            self.smoke_remaining -= 1
        if self.survivor_remaining > 0:
            self.survivor_remaining -= 1

        # -------------------------- detections ---------------------------
        fire_conf = round(
            _clamp(self.fire_level, 0, 1) * (0.45 + 0.55 * self.rng.random()),
            3
        )
        smoke_conf = round(
            _clamp(self.smoke_level, 0, 1) * (0.45 + 0.55 * self.rng.random()),
            3
        )
        survivor_conf = round(
            max(self.survivor_level, self.fire_level * 0.1),
            3
        )

        fire_detected = fire_conf >= 0.45
        smoke_detected = smoke_conf >= 0.45
        survivor_detected = survivor_conf >= 0.55

        survivor_location = None
        if survivor_detected:
            col = self.rng.randint(0, 5)
            row = self.rng.randint(0, 5)
            survivor_location = f"{chr(ord('A') + col)}{row + 1}"

        # ----------------------------- risk ------------------------------
        risk = _risk_for(
            fire_detected,
            smoke_detected,
            self.temp,
            self.gas,
            self.smoke
        )

        if fire_detected and smoke_detected:
            priority = "CRITICAL"
        elif fire_detected:
            priority = "HIGH"
        elif smoke_detected:
            priority = "MEDIUM"
        else:
            priority = None

        recommendation = self._recommendation(
            risk["level"],
            priority,
            survivor_detected
        )

        # --------------------------- snapshot ----------------------------
        snapshot = {
            "timestamp": time.time(),
            "tick": self.tick,
            "simulated": True,
            "vehicle": {
                "id": "ROV-EG-01",
                "gps": {
                    "lat": round(self.lat, 6),
                    "lon": round(self.lon, 6)
                },
                "battery_pct": round(self.battery, 1),
                "tilt_deg": round(self.tilt, 1),
                "obstacle_distance_cm": self.rng.randint(20, 200),
                "status": "on_site"
            },
            "environment": {
                "temperature_c": round(self.temp, 1),
                "humidity_pct": round(self.humidity, 1),
                "gas_ppm": round(self.gas, 1),
                "smoke_density_pct": round(self.smoke, 1),
                "wind_speed_kmh": round(self.wind, 1),
                "wind_direction_deg": round(self.wind_dir, 1)
            },
            "detections": {
                "fire": {
                    "detected": fire_detected,
                    "confidence": fire_conf
                },
                "smoke": {
                    "detected": smoke_detected,
                    "confidence": smoke_conf
                },
                "survivor": {
                    "detected": survivor_detected,
                    "confidence": survivor_conf,
                    "location": survivor_location
                }
            },
            "thermal": {
                "heat_sources": (
                    self.rng.randint(1, 4)
                    if fire_detected
                    else self.rng.randint(0, 1)
                ),
                "max_temperature_c": round(
                    self.temp if not fire_detected else min(65, self.temp + 12),
                    1
                )
            },
            "risk": risk,
            "priority": priority,
            "recommendation": recommendation
        }

        state = {
            "fire": {
                "detected": fire_detected,
                "confidence": fire_conf
            },
            "smoke": {
                "detected": smoke_detected,
                "confidence": smoke_conf
            },
            "survivor": {
                "detected": survivor_detected,
                "confidence": survivor_conf,
                "location": survivor_location
            },
            "risk": risk,
            "priority": priority,
            "recommendation": recommendation
        }

        return state, snapshot

    def _recommendation(self, risk_level, priority, survivor_detected):
        if survivor_detected:
            return "Deploy rescue team to survivor zone immediately"

        if risk_level == "HIGH":
            return "Evacuate area and evacuate personnel to nearest shelter"

        if risk_level == "MEDIUM":
            return "Monitor conditions and prepare evacuation teams"

        return "Area appears safe - continue routine monitoring"