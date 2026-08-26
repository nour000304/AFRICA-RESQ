from fusion import FusionEngine


fusion = FusionEngine()

result = fusion.combine(
    visual_confidence=0.91,
    thermal_confidence=0.95
)

print(result)