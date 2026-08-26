class RecommendationEngine:

    def generate(
        self,
        survivor,
        risk_result,
        route
    ):

        risk = risk_result["risk"]
        priority = survivor["priority"]
        confidence = survivor["confidence"]

        reasons = []

        if confidence >= 0.8:
            reasons.append("High survivor confidence")

        if risk >= 75:
            reasons.append("Critical environmental risk")

        elif risk >= 50:
            reasons.append("Elevated environmental risk")

        else:
            reasons.append("Low environmental risk")

        if route:
            reasons.append("Safest feasible route identified")

        action = "APPROACH_SURVIVOR"

        if risk >= 90:
            action = "HOLD_AND_REASSESS"

        return {
            "action": action,
            "target": survivor["survivor_id"],
            "route": route,
            "priority": priority,
            "risk": risk,
            "confidence": confidence,
            "reasons": reasons,
            "operator_override_allowed": True
        }