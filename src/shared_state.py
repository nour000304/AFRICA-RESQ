import json
import os

STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "state.json"
)


state = {
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


def save_state():

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print("STATE SAVED:", STATE_FILE)
    print("FIRE STATE:", state["fire"])