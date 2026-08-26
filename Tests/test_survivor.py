from survivor import SurvivorEngine


engine = SurvivorEngine()

fusion_result = {
    "survivor_confidence": 0.93,
    "evidence": {
        "visual": 0.91,
        "thermal": 0.95
    }
}

survivor = engine.create_candidate(
    confidence=fusion_result["survivor_confidence"],
    location="B3",
    evidence=fusion_result["evidence"]
)

print(survivor)