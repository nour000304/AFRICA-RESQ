class FusionEngine:

    def combine(self, visual_confidence, thermal_confidence):

        # Weighted fusion
        survivor_confidence = (
            visual_confidence * 0.5
            + thermal_confidence * 0.5
        )

        return {
            "survivor_confidence": round(
                survivor_confidence,
                3
            ),
            "evidence": {
                "visual": visual_confidence,
                "thermal": thermal_confidence
            }
        }