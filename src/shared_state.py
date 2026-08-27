import json
import os

# Project root
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

STATE_FILE = os.path.join(
    BASE_DIR,
    "state.json"
)


state = {
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
    "recommendation": None,
    "sensors": None,
    "sensor_history": []
}


def save_state():

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        print("STATE SAVED:", STATE_FILE)
        print("FIRE STATE:", state["fire"])
        print("SMOKE STATE:", state["smoke"])

    except Exception as e:
        print("ERROR SAVING STATE:", e)


def load_state():

    if not os.path.exists(STATE_FILE):
        return state

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        state.update(loaded)

        return state

    except Exception as e:
        print("ERROR LOADING STATE:", e)

        return state