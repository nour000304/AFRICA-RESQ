class RiskEngine:

    def calculate(self, hazards, survivor_confidence=0, battery=100):

        risk = 0
        reasons = []

        # Fire
        fire = self.get_hazard_score(hazards, "fire")

        if fire > 0:
            risk += fire * 0.30
            reasons.append("Fire detected")

        # Gas
        gas = self.get_hazard_score(hazards, "gas")

        if gas > 0:
            risk += gas * 0.25
            reasons.append("Gas elevated")

        # Temperature
        temperature = self.get_hazard_score(hazards, "temperature")

        if temperature > 0:
            risk += temperature * 0.15
            reasons.append("High temperature")

        # Survivor
        if survivor_confidence > 0:
            risk += survivor_confidence * 10
            reasons.append("Survivor detected")

        # Low battery
        if battery < 25:
            risk += 9.5
            reasons.append("Rover battery low")

        # Limit risk to 100
        risk = min(100, round(risk))

        # Risk level
        if risk >= 75:
            level = "CRITICAL"

        elif risk >= 50:
            level = "HIGH"

        elif risk >= 25:
            level = "MEDIUM"

        else:
            level = "LOW"

        return {
            "risk": risk,
            "level": level,
            "reasons": reasons
        }

    def get_hazard_score(self, hazards, hazard_type):

        for hazard in hazards:

            if hazard["type"] == hazard_type:
                return hazard["score"]

        return 0