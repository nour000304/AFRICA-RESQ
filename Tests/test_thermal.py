from thermal import ThermalEngine


thermal = ThermalEngine()

result = thermal.detect_heat(
    location=[318, 242],
    temperature=35.9
)

print(result)