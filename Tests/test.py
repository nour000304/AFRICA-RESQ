from ultralytics import YOLO

# Load trained model
model = YOLO("model/best.pt")

# Run detection
results = model.predict(
    source="smoke.jpg",
    conf=0.25,
    save=True
)

print("✅ Detection finished!")