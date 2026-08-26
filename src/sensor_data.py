import time


class SensorData:

    def read(self):

        return {
            "gas": 62,
            "temperature": 38,
            "obstacle_distance": 45,
            "tilt": 3,
            "battery": 78,
            "status": "ok",
            "timestamp": time.time()
        }