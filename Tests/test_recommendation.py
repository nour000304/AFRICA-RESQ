from recommendation_engine import RecommendationEngine


engine = RecommendationEngine()

survivor = {
    "survivor_id": "S01",
    "confidence": 0.94,
    "priority": 1
}

risk = {
    "risk": 74,
    "level": "HIGH",
    "reasons": [
        "Fire detected",
        "Gas elevated"
    ]
}

route = [
    (0, 0),
    (0, 1),
    (0, 2),
    (0, 3),
    (0, 4)
]

result = engine.generate(
    survivor,
    risk,
    route
)

print(result)