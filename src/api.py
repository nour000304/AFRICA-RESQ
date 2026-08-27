from fastapi import FastAPI
from fastapi.responses import FileResponse
from datetime import datetime
import json
import os

from src.location_engine import LocationEngine
from src.route_engine import RouteEngine


# ==========================================
# APP
# ==========================================

app = FastAPI(
    title="AFRICA RESQ AI",
    description="AI-powered Fire, Smoke, Risk and Safe Route System",
    version="1.0.0"
)


# ==========================================
# PATHS
# ==========================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

STATE_FILE = os.path.join(
    BASE_DIR,
    "src",
    "state.json"
)

MAP_FILE = os.path.join(
    BASE_DIR,
    "static",
    "map.html"
)


# ==========================================
# ENGINES
# ==========================================

location_engine = LocationEngine()
route_engine = RouteEngine()


# ==========================================
# DEFAULT STATE
# ==========================================

def default_state():

    return {
        "fire": {
            "detected": False,
            "confidence": 0.0
        },

        "smoke": {
            "detected": False,
            "confidence": 0.0
        },

        "survivor": {
            "detected": False,
            "confidence": 0.0,
            "location": None
        },

        "risk": {
            "score": 0,
            "level": "LOW"
        },

        "priority": None,

        "route": [],

        "recommendation": None
    }


# ==========================================
# READ STATE
# ==========================================

def get_state():

    if not os.path.exists(STATE_FILE):

        return default_state()

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print("STATE ERROR:", e)

        return default_state()


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return {
        "status": "online",
        "system": "AFRICA RESQ AI",
        "version": "1.0.0"
    }


# ==========================================
# API STATUS
# ==========================================

@app.get("/api/status")
def status():

    return {
        "status": "online",
        "system": "AFRICA RESQ AI",
        "timestamp": datetime.now().isoformat()
    }


# ==========================================
# FULL SYSTEM STATE
# ==========================================

@app.get("/api/full")
def full():

    return get_state()


# ==========================================
# FIRE / SMOKE / SURVIVOR DETECTION
# ==========================================

@app.get("/api/detection")
def detection():

    state = get_state()

    return {
        "fire": state.get(
            "fire",
            {
                "detected": False,
                "confidence": 0
            }
        ),

        "smoke": state.get(
            "smoke",
            {
                "detected": False,
                "confidence": 0
            }
        ),

        "survivor": state.get(
            "survivor",
            {
                "detected": False,
                "confidence": 0,
                "location": None
            }
        )
    }


# ==========================================
# RISK
# ==========================================

@app.get("/api/risk")
def risk():

    state = get_state()

    return state.get(
        "risk",
        {
            "score": 0,
            "level": "LOW"
        }
    )


# ==========================================
# PRIORITY
# ==========================================

@app.get("/api/priority")
def priority():

    state = get_state()

    return {
        "priority": state.get(
            "priority",
            None
        )
    }


# ==========================================
# LOCATION
# ==========================================

@app.get("/api/location")
def location(
    latitude: float,
    longitude: float
):

    return location_engine.get_location(
        latitude,
        longitude
    )


# ==========================================
# ROUTE
# ==========================================

@app.get("/api/route")
def route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float
):

    try:

        return route_engine.get_route(
            start_lat,
            start_lon,
            end_lat,
            end_lon
        )

    except Exception as e:

        return {
            "success": False,
            "message": "Route calculation failed",
            "error": str(e)
        }


# ==========================================
# MAP
# ==========================================

@app.get("/map")
def map_page():

    if not os.path.exists(MAP_FILE):

        return {
            "error": "map.html not found",
            "path": MAP_FILE
        }

    return FileResponse(
        MAP_FILE,
        media_type="text/html"
    )


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/api/health")
def health():

    return {
        "status": "healthy",
        "api": "online",
        "state_file": os.path.exists(STATE_FILE),
        "map_file": os.path.exists(MAP_FILE),
        "timestamp": datetime.now().isoformat()
    }