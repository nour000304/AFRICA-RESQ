class HazardEngine:

    def analyze(self, detections, sensors):

        hazards = []

        # Fire
        fire_confidence = max(
            [d["confidence"] for d in detections if d["class"].lower() == "fire"],
            default=0
        )

        if fire_confidence > 0:
            hazards.append({
                "type": "fire",
                "score": round(fire_confidence * 100),
                "level": self.get_level(fire_confidence * 100)
            })

        # Smoke
        smoke_confidence = max(
            [d["confidence"] for d in detections if d["class"].lower() == "smoke"],
            default=0
        )

        if smoke_confidence > 0:
            hazards.append({
                "type": "smoke",
                "score": round(smoke_confidence * 100),
                "level": self.get_level(smoke_confidence * 100)
            })

        # Gas
        gas = sensors.get("gas", 0)

        if gas > 50:
            hazards.append({
                "type": "gas",
                "score": gas,
                "level": self.get_level(gas)
            })

        # Temperature
        temperature = sensors.get("temperature", 0)

        if temperature > 40:
            score = min(100, temperature * 2)

            hazards.append({
                "type": "temperature",
                "score": round(score),
                "level": self.get_level(score)
            })

        return hazards

    def get_level(self, score):

        if score >= 75:
            return "HIGH"

        elif score >= 40:
            return "MEDIUM"

        else:
            return "LOW"