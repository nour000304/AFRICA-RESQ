from risk_engine import RiskEngine

engine = RiskEngine()

hazards = [
    {
        "type": "fire",
        "score": 88,
        "level": "HIGH"
    },
    {
        "type": "gas",
        "score": 62,
        "level": "MEDIUM"
    },
    {
        "type": "temperature",
        "score": 90,
        "level": "HIGH"
    }
]

result = engine.calculate(
    hazards=hazards,
    survivor_confidence=0.94,
    battery=20
)

print(result)