import cv2
import time
import pygame

from perception import PerceptionEngine
from shared_state import state, save_state


# ==========================================
# CONFIG
# ==========================================

CAMERA_INDEX = 0
MODEL_PATH = "model/best.pt"

# YOLO confidence
CONFIDENCE_THRESHOLD = 0.45

# How long detection stays active after YOLO
# temporarily loses the object
FIRE_HOLD_FRAMES = 15
SMOKE_HOLD_FRAMES = 15


# ==========================================
# INIT
# ==========================================

print("Loading YOLO model...")

perception = PerceptionEngine(MODEL_PATH)

print("YOLO model loaded successfully.")

print("================================")
print("      AFRICA RESQ LIVE AI")
print("================================")


# ==========================================
# CAMERA
# ==========================================

cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print("ERROR: Cannot open camera")
    exit()

print("Camera started")
print("Fire alert system: ON")
print("API state sharing: ON")
print("Press Q to quit")


# ==========================================
# SOUND
# ==========================================

pygame.init()

alert_sound = None

try:
    alert_sound = pygame.mixer.Sound("alert.mp3")
except Exception:
    print("WARNING: alert.mp3 not found")


alert_playing = False


# ==========================================
# DETECTION MEMORY
# ==========================================

fire_hold = 0
smoke_hold = 0

last_fire_confidence = 0.0
last_smoke_confidence = 0.0


# ==========================================
# MAIN LOOP
# ==========================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("ERROR: Cannot read frame")
        break


    # ======================================
    # YOLO
    # ======================================

    try:

        result = perception.detect(frame)

        if isinstance(result, tuple):

            detections = result[0]

            if len(result) > 1:
                annotated_frame = result[1]
            else:
                annotated_frame = frame.copy()

        else:

            detections = result
            annotated_frame = frame.copy()


    except Exception as e:

        print("DETECTION ERROR:", e)

        detections = []
        annotated_frame = frame.copy()


    # ======================================
    # CURRENT FRAME DETECTIONS
    # ======================================

    current_fire = False
    current_smoke = False

    current_fire_confidence = 0.0
    current_smoke_confidence = 0.0


    # ======================================
    # PROCESS YOLO DETECTIONS
    # ======================================

    for detection in detections:

        try:

            class_name = str(
                detection.get("class", "")
            ).lower().strip()

            confidence = float(
                detection.get("confidence", 0)
            )


            print(
                f"DETECTION: {class_name} {confidence}"
            )


            # ------------------------------
            # FIRE
            # ------------------------------

            if class_name == "fire":

                if confidence >= CONFIDENCE_THRESHOLD:

                    current_fire = True

                    if confidence > current_fire_confidence:
                        current_fire_confidence = confidence


            # ------------------------------
            # SMOKE
            # ------------------------------

            elif class_name == "smoke":

                if confidence >= CONFIDENCE_THRESHOLD:

                    current_smoke = True

                    if confidence > current_smoke_confidence:
                        current_smoke_confidence = confidence


        except Exception as e:

            print("Detection parsing error:", e)


    # ======================================
    # FIRE MEMORY / SMOOTHING
    # ======================================

    if current_fire:

        fire_hold = FIRE_HOLD_FRAMES

        last_fire_confidence = current_fire_confidence

    else:

        if fire_hold > 0:

            fire_hold -= 1


    fire_detected = fire_hold > 0


    # ======================================
    # SMOKE MEMORY / SMOOTHING
    # ======================================

    if current_smoke:

        smoke_hold = SMOKE_HOLD_FRAMES

        last_smoke_confidence = current_smoke_confidence

    else:

        if smoke_hold > 0:

            smoke_hold -= 1


    smoke_detected = smoke_hold > 0


    # ======================================
    # CONFIDENCE
    # ======================================

    if fire_detected:

        fire_confidence = last_fire_confidence

    else:

        fire_confidence = 0.0


    if smoke_detected:

        smoke_confidence = last_smoke_confidence

    else:

        smoke_confidence = 0.0


    # ======================================
    # UPDATE SHARED STATE
    # ======================================

    state["fire"]["detected"] = bool(fire_detected)

    state["fire"]["confidence"] = round(
        float(fire_confidence),
        3
    )


    state["smoke"]["detected"] = bool(smoke_detected)

    state["smoke"]["confidence"] = round(
        float(smoke_confidence),
        3
    )


    # ======================================
    # RISK
    # ======================================

    if fire_detected and smoke_detected:

        state["risk"]["score"] = 100
        state["risk"]["level"] = "HIGH"

    elif fire_detected:

        state["risk"]["score"] = 80
        state["risk"]["level"] = "HIGH"

    elif smoke_detected:

        state["risk"]["score"] = 50
        state["risk"]["level"] = "MEDIUM"

    else:

        state["risk"]["score"] = 0
        state["risk"]["level"] = "LOW"


    # ======================================
    # PRIORITY
    # ======================================

    if fire_detected and smoke_detected:

        state["priority"] = "CRITICAL"

    elif fire_detected:

        state["priority"] = "HIGH"

    elif smoke_detected:

        state["priority"] = "MEDIUM"

    else:

        state["priority"] = None


    # ======================================
    # SAVE STATE
    # ======================================

    print(
        "LIVE STATE:",
        state["fire"],
        state["smoke"]
    )

    save_state()


    # ======================================
    # DISPLAY FIRE
    # ======================================

    if fire_detected:

        cv2.putText(
            annotated_frame,
            f"FIRE DETECTED {fire_confidence:.2f}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3
        )


        if alert_sound and not alert_playing:

            try:

                alert_sound.play(-1)
                alert_playing = True

            except Exception:
                pass


    else:

        cv2.putText(
            annotated_frame,
            "NO FIRE",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            3
        )


        if alert_sound and alert_playing:

            try:
                alert_sound.stop()
            except Exception:
                pass

            alert_playing = False


    # ======================================
    # DISPLAY SMOKE
    # ======================================

    if smoke_detected:

        cv2.putText(
            annotated_frame,
            f"SMOKE DETECTED {smoke_confidence:.2f}",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2
        )


    # ======================================
    # DISPLAY RISK
    # ======================================

    cv2.putText(
        annotated_frame,
        f"RISK: {state['risk']['level']}",
        (20, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255) if state["risk"]["level"] == "HIGH"
        else (0, 255, 0),
        2
    )


    # ======================================
    # SHOW CAMERA
    # ======================================

    cv2.imshow(
        "AFRICA RESQ - LIVE AI",
        annotated_frame
    )


    # ======================================
    # QUIT
    # ======================================

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):

        break


# ==========================================
# CLEANUP
# ==========================================

if alert_sound:

    try:
        alert_sound.stop()
    except Exception:
        pass


cap.release()

cv2.destroyAllWindows()

pygame.quit()

print("Camera stopped.")
print("AFRICA RESQ LIVE AI stopped.")