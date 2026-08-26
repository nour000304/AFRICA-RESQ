from hazard_engine import HazardEngine

engine = HazardEngine()

detections = [
    {
        "class": "fire",
        "confidence": 0.88,
        "location": [320, 240],
        "source": "rgb"
    }
]

sensors = {
    "gas": 62,
    "temperature": 45
}

hazards = engine.analyze(detections, sensors)

print(hazards)