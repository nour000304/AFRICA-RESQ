import time
from ultralytics import YOLO


class PerceptionEngine:

    def __init__(self, model_path="model/best.pt"):
        print("Loading YOLO model...")
        self.model = YOLO(model_path)
        print("YOLO model loaded successfully.")

    def detect(self, frame):
        try:
            results = self.model(
                frame,
                conf=0.50,
                imgsz=416,
                verbose=False,
                device="cpu"
            )

            detections = []

            # YOLO annotated frame
            annotated_frame = results[0].plot()

            for box in results[0].boxes:

                class_id = int(box.cls[0])
                class_name = self.model.names[class_id]
                confidence = float(box.conf[0])

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)

                detection = {
                    "class": class_name,
                    "confidence": round(confidence, 3),
                    "location": [center_x, center_y],
                    "bbox": [x1, y1, x2, y2],
                    "source": "rgb",
                    "timestamp": time.time()
                }

                detections.append(detection)

            return detections, annotated_frame

        except Exception as e:

            print("YOLO ERROR:", e)

            return [], frame