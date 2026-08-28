# AFRICA RESQ — Low-Cost Research Rover (ROS2-Ready) — Design Brief

Companion file: `design/rover_sketch.svg`

## 1. Why a rover

The AFRICA RESQ system currently turns cameras/radios/sensors into a live survival map. A small, cheap rover extends coverage into the danger zone where people cannot safely walk:

- Reconnaissance before/while rescue teams advance **reduces rescuer risk**.
- Carries the same sensor stack the fixed nodes carry, so it **feeds the existing live event API** unchanged (POST `/api/events` → DataEngine → SSE to the dashboard).

## 2. Main features (what the sketch shows)

| # | Component | Role | ROS2 topic / note |
|---|-----------|------|-------------------|
| 1 | YDLIDAR X2L LiDAR (360°, 8 m) — the cheap 360° ROS2 lidar | SLAM + obstacle avoidance + localisation | `/scan` via `ydlidar_ros2` |
| 2 | RPi Camera V2.1 (used/refurb) | YOLO fire / smoke / survivor detection (edge) | `/image_raw` → `/detections` |
| 3 | GPS NEO-6M | outdoor position for the map | `/fix` |
| 4 | DHT22 + MQ-2 + MQ-7 | temp, humidity, gas, CO/smoke → risk score | `/env_telemetry` |
| 5 | Raspberry Pi 4B 2 GB | runs ROS2 Humble + YOLO + AFRICA RESQ API | main compute |
| 6 | 4× 12 V gearmotors + L298N ×2 | differential drive, climbing torque | `/cmd_vel`, `/odom` |
| 7 | MPU-6050 (6-axis IMU) | roll / pitch / heading — climbing stability | `/imu` |
| 8 | 11.1 V LiPo 2200 mAh + buck/BEC | power, mounted LOW for a low centre of gravity | — |
| 9 | Gearmotors (same as #6) | hub/encoder option for wheel odometry | part of #6 |
| 10 | Rubber tracks + drive sprockets | climb rubble, kerbs, steps | — |
| 11 | Aluminium chassis + 3D-printed mounts | tub design, low COG, front flipper for obstacle climb | — |
| 12 | Wiring / connectors / fasteners | misc. hardware | — |

**Target bill of materials ≈ $220 USD** (see legend on the sketch; even cheaper ~$200 by using a YDLIDAR X2 at ~$50 and a 4WD starter-kit chassis). Cheaper double-beam lidars (e.g. LD06) cost more, so the X2L at ~$60 is the sweet spot for 360° ROS2.

## 3. Why this design climbs & survives dangerous terrain

- **Tracks not wheels** — rubber tracks spread weight, grip rubble, and step over kerbs; the front **flipper** lifts the nose onto obstacles.
- **Low centre of gravity** — battery and drive layers sit at the bottom of the tub; nothing heavy topside but the LiDAR mast.
- **High-torque 12 V gearmotors** — moderate speed (~0.6 m/s) for rescuer-following pace but strong crawl ratio for slopes/steps up to ~10 cm.
- **First responder sized** ≈ L50 × W34 × H30 cm — fits gaps, over thresholds, into semi-collapsed rooms.
- Optional tracks-off 4WD config: lighter, cheaper, still works on hard terrain.

## 4. ROS2 software design (2 lightweight packages)

```
rover_perception
  lidar_node   (ydlidar_ros2 -> /scan)          [SLAM: slam_toolbox or rtabmap]
  camera_node  (/image_raw) + yolo_node -> /detections   (fire, smoke, person)
  imu_node   -> /imu       gps_node -> /fix       env_node -> /env_telemetry

rover_control
  motor_node: subscribes /cmd_vel (diff drive) -> PWM via L298N on RPi GPIO
              publishes /odom from wheel encoders
```

- **Teleop:** gamepad / WebRTC low-latency video over the existing 4G-cellular gateway; `teleop_twist_keyboard` for tests.
- **Semi-autonomy:** Nav2 waypoints from GPS + local SLAM map; manual override always trumps autonomy.
- **Safety behaviours** (on-chip, low-level on the motor node): stop if `/scan` too close; stop if IMU pitch > ~60° (tip-over risk); gas/CO threshold -> back off.

## 5. Bridging to the AFRICA RESQ stack

The rover is a **mobile sensor node**, so it reuses everything built already:
**rover_perception / rover_control → `rosbridge` → AFRICA RESQ API → `api.py` (POST /api/events) → DataEngine → SSE → dashboard.**

No new backend work required — detection and environment events from the rover appear on the live map exactly like the simulator/static-node events already do.

## 6. Next steps (if we keep going)

1. Mechanical: pick concrete kit (e.g. proven plastic track-drive platform ~$40) + 3D-printed LiDAR mast & flipper.
2. Electrical: single L298N dual H-bridge prototype, then second for 4WD.
3. ROS2 bring-up: flash Pi OS + ROS2 Humble, run `ydlidar_ros2`, record a test bag in a corridor.
4. Edge YOLO: export a small fire/smoke model (or use the same detector backend as the fixed nodes).
5. Field test: obstacle course incl. kerb climb + tip-over IMU test; log everything via `/rosout` and the AFRICA RESQ API.