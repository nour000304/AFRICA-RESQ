# AFRICA RESQ — AI Fire & Smoke Detection System

## Overview

AFRICA RESQ is an AI-powered fire and smoke detection system designed to support emergency response and search-and-rescue operations.

The system combines computer vision, hazard analysis, risk assessment, survivor detection, and decision-support components.

## System Architecture

```text
Camera / Sensors
       ↓
Perception
       ↓
Fusion
       ↓
Hazard & Survivor Analysis
       ↓
Risk / Priority / Safe Path
       ↓
Recommendation
       ↓
FastAPI Backend
       ↓
Frontend Dashboard
```

## Main Components

- `perception.py` — Fire and smoke detection using computer vision
- `webcam.py` — Live camera input
- `fusion.py` — Combines system information
- `hazard_engine.py` — Hazard analysis
- `survivor.py` — Survivor detection
- `thermal.py` — Thermal sensor processing
- `risk_engine.py` — Risk assessment
- `priority_engine.py` — Rescue priority assessment
- `safe_path.py` — Safe route processing
- `zone_mapper.py` — Zone mapping
- `recommendation_engine.py` — Generates recommendations
- `main_pipeline.py` — Main processing pipeline
- `live_pipeline.py` — Live processing pipeline
- `shared_state.py` — Shared system state
- `sensor_data.py` — Sensor data handling
- `api.py` — FastAPI backend

## AI Perception

The perception layer uses a trained YOLO-based computer vision model to detect fire and smoke from camera frames.

For each detection, the system can process information such as:

- Detection class
- Confidence score
- Bounding box
- Object location
- Detection source
- Timestamp

## API Endpoints

The backend is built with FastAPI and provides the following REST API endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /` | Check whether the AFRICA RESQ AI system is online |
| `GET /api/status` | Return backend status and timestamp |
| `GET /api/detection` | Return fire, smoke and survivor detection |
| `GET /api/risk` | Return the current risk assessment |
| `GET /api/full` | Return the complete system state |

## API Examples

### GET `/`

Returns the current system status.

Example response:

```json
{
  "status": "online",
  "system": "AFRICA RESQ AI"
}
```

### GET `/api/status`

Returns the backend status and current timestamp.

Example response:

```json
{
  "status": "online",
  "timestamp": "2026-08-25T13:30:00"
}
```

### GET `/api/detection`

Returns current fire, smoke and survivor detection information.

Example response:

```json
{
  "fire": {
    "detected": true,
    "confidence": 0.85
  },
  "smoke": {
    "detected": false,
    "confidence": 0
  },
  "survivor": {
    "detected": false,
    "confidence": 0,
    "location": null
  }
}
```

### GET `/api/risk`

Returns the current risk assessment.

Example response:

```json
{
  "score": 75,
  "level": "HIGH"
}
```

### GET `/api/full`

Returns the complete current system state, including:

- Fire detection
- Smoke detection
- Survivor detection
- Risk information
- Priority
- Route
- Recommendation

## State Management

The current system state is stored in:

```text
state.json
```

The FastAPI backend reads this state and provides the relevant information to the frontend.

## Running the Backend

First activate the Python virtual environment.

From the project directory:

```powershell
.venv\Scripts\Activate.ps1
```

Then move to the `src` directory:

```powershell
cd src
```

Start the FastAPI backend:

```powershell
python -m uvicorn api:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

## Interactive API Documentation

FastAPI automatically provides interactive API documentation.

Open:

```text
http://127.0.0.1:8000/docs
```

The documentation allows the frontend team to test the available API endpoints.

## Project Structure

```text
fire-smoke-detection/
│
├── model/
│   └── best.pt
│
├── src/
│   ├── api.py
│   ├── perception.py
│   ├── webcam.py
│   ├── fusion.py
│   ├── hazard_engine.py
│   ├── survivor.py
│   ├── thermal.py
│   ├── risk_engine.py
│   ├── priority_engine.py
│   ├── safe_path.py
│   ├── zone_mapper.py
│   ├── recommendation_engine.py
│   ├── main_pipeline.py
│   ├── live_pipeline.py
│   ├── shared_state.py
│   └── sensor_data.py
│
├── Tests/
├── alert.mp3
├── requirements.txt
├── state.json
├── .gitignore
└── README.md
```

## Frontend Integration

The frontend dashboard can periodically request the API endpoints to retrieve the current AI system state.

Main integration endpoints:

```text
/api/status
/api/detection
/api/risk
/api/full
```

This allows the frontend to display:

- Fire alerts
- Smoke alerts
- Survivor information
- Risk level
- Rescue priority
- Recommended actions
- Safe route information

## Technologies

- Python
- FastAPI
- YOLO / Ultralytics
- OpenCV
- PyTorch
- NumPy

## Project Status

The AFRICA RESQ backend provides the API integration layer between the AI processing pipeline and the frontend dashboard.

The current system exposes real-time system status, fire and smoke detection, survivor information, and risk assessment through REST API endpoints.

## Team Project

AFRICA RESQ is developed as an AI-powered decision-support system for emergency response and search-and-rescue operations.