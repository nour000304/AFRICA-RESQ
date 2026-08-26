from perception import PerceptionEngine
from thermal import ThermalEngine
from sensor_data import SensorData
from fusion import FusionEngine
from survivor import SurvivorEngine
from hazard_engine import HazardEngine
from risk_engine import RiskEngine
from priority_engine import PriorityEngine
from safe_path import SafePathPlanner
from recommendation_engine import RecommendationEngine


# -----------------------------------
# Initialize engines
# -----------------------------------

perception = PerceptionEngine()
thermal = ThermalEngine()
sensors = SensorData()
fusion = FusionEngine()
survivor_engine = SurvivorEngine()
hazard = HazardEngine()
risk_engine = RiskEngine()
priority_engine = PriorityEngine()
recommendation = RecommendationEngine()


# -----------------------------------
# 1. Fake camera detection
# -----------------------------------

visual_detection = {
    "class": "person",
    "confidence": 0.91,
    "location": [320, 240],
    "source": "rgb"
}

detections = [
    visual_detection,
    {
        "class": "fire",
        "confidence": 0.88,
        "location": [400, 250],
        "source": "rgb"
    }
]


# -----------------------------------
# 2. Thermal
# -----------------------------------

thermal_result = thermal.detect_heat(
    location=[318, 242],
    temperature=35.9
)


# -----------------------------------
# 3. Sensors
# -----------------------------------

sensor_result = sensors.read()


# -----------------------------------
# 4. Fusion
# -----------------------------------

fusion_result = fusion.combine(
    visual_confidence=visual_detection["confidence"],
    thermal_confidence=thermal_result["heat_confidence"]
)


# -----------------------------------
# 5. Survivor
# -----------------------------------

survivor = survivor_engine.create_candidate(
    confidence=fusion_result["survivor_confidence"],
    location="B3",
    evidence=fusion_result["evidence"]
)


# -----------------------------------
# 6. Hazard
# -----------------------------------

hazards = hazard.analyze(
    detections=detections,
    sensors=sensor_result
)


# -----------------------------------
# 7. Risk
# -----------------------------------

risk_result = risk_engine.calculate(
    hazards=hazards,
    survivor_confidence=survivor["confidence"],
    battery=sensor_result["battery"]
)


# -----------------------------------
# 8. Priority
# -----------------------------------

survivors = priority_engine.rank([
    {
        "survivor_id": survivor["survivor_id"],
        "confidence": survivor["confidence"],
        "risk": risk_result["risk"],
        "distance": 10
    }
])


# -----------------------------------
# 9. Safe Path
# -----------------------------------

grid = [
    [0, 0, 0, 0, 0],
    [0, 100, 100, 100, 0],
    [0, 5, 5, 5, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0]
]

planner = SafePathPlanner(grid)

path = planner.find_path(
    start=(0, 0),
    goal=(0, 4)
)


# -----------------------------------
# 10. Recommendation
# -----------------------------------

final_result = recommendation.generate(
    survivor=survivors[0],
    risk_result=risk_result,
    route=path
)


# -----------------------------------
# FINAL OUTPUT
# -----------------------------------

print("\n==============================")
print("     AFRICA RESQ AI RESULT")
print("==============================")

print("\nSURVIVOR:")
print(survivor)

print("\nHAZARDS:")
print(hazards)

print("\nRISK:")
print(risk_result)

print("\nPRIORITY:")
print(survivors[0])

print("\nSAFE PATH:")
print(path)

print("\nRECOMMENDATION:")
print(final_result)

print("\n==============================")