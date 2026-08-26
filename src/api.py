from fastapi import FastAPI
from datetime import datetime
import json
import os

app = FastAPI(title="AFRICA RESQ AI")

STATE_FILE = "state.json"


def get_state():

    if not os.path.exists(STATE_FILE):
        return {
            "fire": {
                "detected": False,
                "confidence": 0
            },
            "smoke": {
                "detected": False,
                "confidence": 0
            },
            "survivor": {
                "detected": False,
                "confidence": 0,
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

    try:

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:

        return {
            "fire": {
                "detected": False,
                "confidence": 0
            },
            "smoke": {
                "detected": False,
                "confidence": 0
            },
            "survivor": {
                "detected": False,
                "confidence": 0,
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


@app.get("/")
def home():

    return {
        "status": "online",
        "system": "AFRICA RESQ AI"
    }


@app.get("/api/status")
def status():

    return {
        "status": "online",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/full")
def full():

    return get_state()


@app.get("/api/detection")
def detection():

    state = get_state()

    return {
        "fire": state["fire"],
        "smoke": state["smoke"],
        "survivor": state["survivor"]
    }


@app.get("/api/risk")
def risk():

    state = get_state()

    return state["risk"]