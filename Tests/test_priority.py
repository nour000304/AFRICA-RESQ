from priority_engine import PriorityEngine

engine = PriorityEngine()

survivors = [
    {
        "survivor_id": "S01",
        "confidence": 0.94,
        "risk": 87,
        "distance": 10
    },
    {
        "survivor_id": "S02",
        "confidence": 0.71,
        "risk": 60,
        "distance": 6
    },
    {
        "survivor_id": "S03",
        "confidence": 0.52,
        "risk": 40,
        "distance": 4
    }
]

result = engine.rank(survivors)

for survivor in result:
    print(survivor)