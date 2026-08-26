import cv2
import pygame

from perception import PerceptionEngine


# ==========================================
# Initialize Perception Engine
# ==========================================

perception = PerceptionEngine("model/best.pt")


# ==========================================
# Initialize Alert Sound
# ==========================================

pygame.mixer.init()
pygame.mixer.music.load("alert.mp3")


# ==========================================
# Open Webcam
# ==========================================

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not cap.isOpened():
    print("❌ Camera not found")
    exit()

print("====================================")
print("✅ AFRICA RESQ Perception started")
print("🔥 Fire / Smoke Detection Active")
print("Press Q to quit")
print("====================================")


# ==========================================
# Main Loop
# ==========================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("❌ Failed to read camera")
        break


    # ======================================
    # YOLO Detection
    # ======================================

    detections, annotated_frame = perception.detect(frame)


    # ======================================
    # Display Detection Information
    # ======================================

    for detection in detections:

        class_name = detection["class"]
        confidence = detection["confidence"]

        print(
            f"DETECTION: {class_name} "
            f"{confidence:.3f}"
        )


    # ======================================
    # Fire / Smoke Alert
    # ======================================

    dangerous_detection = any(
        detection["class"].lower() in ["fire", "smoke"]
        for detection in detections
    )


    if dangerous_detection:

        cv2.putText(
            annotated_frame,
            "!!! FIRE / SMOKE DETECTED !!!",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3
        )

        # Play alert
        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.play()


    # ======================================
    # Show Camera
    # ======================================

    cv2.imshow(
        "AFRICA RESQ - Perception",
        annotated_frame
    )


    # ======================================
    # Keyboard
    # ======================================

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q") or key == ord("Q") or key == 27:
        break


# ==========================================
# Cleanup
# ==========================================

cap.release()

cv2.destroyAllWindows()

pygame.mixer.quit()

print("✅ Perception stopped")