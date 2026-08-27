import time

from ultralytics import YOLO

try:
    from data_engine import DataEngine
except ImportError:
    from src.data_engine import DataEngine


LOG_CLASSES = ("fire", "smoke", "survivor", "person")


class PerceptionEngine:

    def __init__(self, model_path="model/best.pt", persist=True):
        print("Loading YOLO model...")
        self.model = YOLO(model_path)
        self.persist = persist

        # Event store: every camera detection is saved for later analysis
        self.data_engine = DataEngine()

        # Throttle per class so a constantly-detected fire does not
        # flood the database with duplicate rows every frame
        self._last_log = {}

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

                # Persist the detection event (throttled per class)
                if self.persist and class_name in LOG_CLASSES:
                    self._log_detection(class_name, confidence, detection)

            return detections, annotated_frame

        except Exception as e:

            print("YOLO ERROR:", e)

            return [], frame

    def _log_detection(self, class_name, confidence, detection):
        now = time.time()

        last = self._last_log.get(class_name)
        if last and (now - last) < 2.0:
            return

        self._last_log[class_name] = now

        try:
            self.data_engine.log_event(
                class_name,
                source="camera_yolo",
                detected=True,
                confidence=confidence,
                payload={
                    "location": detection["location"],
                    "bbox": detection["bbox"],
                    "source": detection["source"]
                },
                ts=detection["timestamp"]
            )
        except Exception as persist_error:
            print("PERSIST ERROR:", persist_error)