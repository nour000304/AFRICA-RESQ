import time


class ThermalEngine:

    def detect_heat(self, location, temperature=35.9):

        # Simple MVP thermal simulation
        if 30 <= temperature <= 42:

            heat_confidence = 0.95

        else:

            heat_confidence = 0.30

        return {
            "heat_confidence": heat_confidence,
            "temperature": temperature,
            "location": location,
            "source": "thermal",
            "timestamp": time.time()
        }