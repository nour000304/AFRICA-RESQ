import asyncio
import json
import os
import queue
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.location_engine import LocationEngine
from src.route_engine import RouteEngine
from src.shelter_engine import ShelterEngine
from src.simulator import SensorSimulator
from src.data_engine import DataEngine
from src.event_bus import EventBus


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
    "state.json"
)

MAP_FILE = os.path.join(
    BASE_DIR,
    "static",
    "map.html"
)

STATIC_DIR = os.path.join(
    BASE_DIR,
    "static"
)


# ==========================================
# ENGINES
# ==========================================

location_engine = LocationEngine()
route_engine = RouteEngine()
shelter_engine = ShelterEngine()

# Persistent event store (all detections are saved here)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Real-time pub/sub so dashboards receive live detections without polling
event_bus = EventBus()

data_engine = DataEngine()
data_engine.on_event = event_bus.publish_event

SIM_INTERVAL = float(os.environ.get("SIM_INTERVAL", "2.0"))
ALT_LAT = float(os.environ.get("ALT_LAT", "30.0444"))
ALT_LON = float(os.environ.get("ALT_LON", "31.2357"))

simulator = SensorSimulator(
    state_file=STATE_FILE,
    interval=SIM_INTERVAL,
    data_engine=data_engine,
    event_bus=event_bus
)
if ALT_LAT and ALT_LON:
    simulator.engine.set_incident(ALT_LAT, ALT_LON)


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

        "recommendation": None,

        "sensors": None,

        "sensor_history": []
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
# LIFESPAN - start prototype sensor simulator
# ==========================================

@asynccontextmanager
async def lifespan(app):
    simulator.start()
    yield
    simulator.stop()


# ==========================================
# APP
# ==========================================

app = FastAPI(
    title="AFRICA RESQ AI",
    description="AI-powered Fire, Smoke, Risk, Safe Route and Shelter System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Serve static assets (dashboard, etc.)
app.mount(
    "/static",
    StaticFiles(
        directory=STATIC_DIR
    ),
    name="static"
)


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return {
        "status": "online",
        "system": "AFRICA RESQ AI",
        "version": "1.0.0",
        "region": "Egypt",
        "simulation": {
            "enabled": simulator.running,
            "interval_seconds": SIM_INTERVAL
        },
        "endpoints": [
            "/api/status",
            "/api/full",
            "/api/detection",
            "/api/risk",
            "/api/priority",
            "/api/location",
            "/api/route",
            "/api/shelters",
            "/api/shelters/cities",
            "/api/nearest_shelter",
            "/api/shelter/{shelter_id}",
            "/api/sensor",
            "/api/sensor/history",
            "/api/events",
            "/api/events/latest",
            "/api/events/stats",
            "/api/events/export",
            "/api/events/stream",
            "/api/simulation/start",
            "/api/simulation/stop",
            "/api/simulation/status",
            "/map"
        ]
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
# SHELTERS - list (all or by city)
# ==========================================

@app.get("/api/shelters")
def shelters(city: str = None):

    return {
        "success": True,
        "count": len(shelter_engine.list_shelters(city)),
        "shelters": shelter_engine.list_shelters(city)
    }


# ==========================================
# SHELTERS - available cities
# ==========================================

@app.get("/api/shelters/cities")
def shelter_cities():

    return {
        "success": True,
        "cities": shelter_engine.list_cities()
    }


# ==========================================
# NEAREST SHELTER SEARCH
# ==========================================

@app.get("/api/nearest_shelter")
def nearest_shelter(
    latitude: float,
    longitude: float,
    limit: int = 3
):

    if limit < 1:
        limit = 1
    if limit > 10:
        limit = 10

    check = location_engine.validate_location(
        latitude,
        longitude
    )

    if not check:
        return {
            "success": False,
            "message": "Location is outside the supported region (Egypt)"
        }

    results = shelter_engine.find_nearest(
        latitude,
        longitude,
        limit=limit
    )

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "count": len(results),
        "nearest": results
    }


# ==========================================
# SHELTER - by id
# ==========================================

@app.get("/api/shelter/{shelter_id}")
def shelter(shelter_id: str):

    result = shelter_engine.get(shelter_id)

    if not result:
        return {
            "success": False,
            "message": "Shelter not found"
        }

    return {
        "success": True,
        "shelter": result
    }


# ==========================================
# SENSOR - current fake reading
# ==========================================

@app.get("/api/sensor")
def sensor():

    if simulator.snapshot:
        return simulator.snapshot

    # Fall back to what was last written to disk
    state = get_state()
    saved = state.get("sensors")
    if saved:
        return saved

    return {
        "simulated": True,
        "timestamp": time.time(),
        "message": "Simulator not started yet"
    }


# ==========================================
# SENSOR - history
# ==========================================

@app.get("/api/sensor/history")
def sensor_history(limit: int = 50):

    history = simulator.history

    if limit <= 0:
        limit = 50

    return {
        "success": True,
        "count": len(history[-limit:]),
        "history": history[-limit:]
    }


# ==========================================
# SIMULATION - control
# ==========================================

class EventIn(BaseModel):
    """Incoming detection event from the dashboard / camera pipeline."""
    type: str
    source: str = "external"
    detected: bool = True
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payload: Optional[dict] = None


@app.post("/api/events")
def create_event(event: EventIn):

    event_id = data_engine.log_event(
        event.type,
        source=event.source,
        detected=event.detected,
        confidence=event.confidence,
        latitude=event.latitude,
        longitude=event.longitude,
        payload=event.payload
    )

    if event_id is None:
        return {
            "success": False,
            "message": "Event not stored (duplicate within throttle window)"
        }

    return {
        "success": True,
        "id": event_id,
        "stored": True
    }


@app.get("/api/events")
def list_events(
    type: Optional[str] = None,
    source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):

    rows = data_engine.query_events(
        event_type=type,
        source=source,
        start=start,
        end=end,
        limit=limit,
        offset=offset
    )

    return {
        "success": True,
        "count": len(rows),
        "events": rows
    }


@app.get("/api/events/stats")
def events_stats(since: Optional[str] = None):

    return {
        "success": True,
        "stats": data_engine.stats(since=since)
    }


@app.get("/api/events/export")
def events_export():

    events = data_engine.export()

    return {
        "success": True,
        "count": len(events),
        "events": events
    }


@app.get("/api/events/latest")
def events_latest():

    stats = data_engine.stats()

    return {
        "success": True,
        "latest_events": data_engine.query_events(limit=5),
        "latest_snapshot": (
            event_bus.latest_state() or simulator.snapshot
        ),
        "total_events": stats["total"],
        "by_type": stats["by_type"],
        "last_event": stats["last_event"]
    }


@app.get("/api/events/stream")
async def events_stream():
    """Server-Sent Events feed for the dashboard.

    Each message is `data: {json}`. Messages are tagged with a `kind`:
      - hello  -> sent once on connect (version + stats)
      - event  -> a freshly stored detection/telemetry row
      - state  -> the latest full sensor snapshot

    The frontend connects once and receives live updates with no polling:
        const stream = new EventSource('/api/events/stream');
        stream.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            // msg.kind === 'event' | 'state' | 'hello'
        };
    """

    async def generate():
        channel = event_bus.subscribe()

        try:
            hello = {
                "kind": "hello",
                "version": "1.0.0",
                "server_time": datetime.now().isoformat(),
                "stats": data_engine.stats()
            }
            yield f"data: {json.dumps(hello, default=str)}\n\n"

            last_sent = time.time()

            while True:
                sent_anything = False

                while not channel.empty():
                    try:
                        message = channel.get_nowait()
                    except queue.Empty:
                        break

                    yield f"data: {message}\n\n"
                    last_sent = time.time()
                    sent_anything = True

                # Keep-alive comment so proxies / clients don't time out
                if not sent_anything and (time.time() - last_sent) > 10:
                    yield ": keep-alive\n\n"
                    last_sent = time.time()

                await asyncio.sleep(0.2)

        finally:
            # Clean up when the dashboard disconnects
            event_bus.unsubscribe(channel)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/simulation/start")
def simulation_start():

    simulator.start()

    return {
        "success": True,
        "running": simulator.running
    }


@app.post("/api/simulation/stop")
def simulation_stop():

    simulator.stop()

    return {
        "success": True,
        "running": simulator.running
    }


@app.get("/api/simulation/status")
def simulation_status():

    return {
        "success": True,
        "running": simulator.running,
        "interval_seconds": SIM_INTERVAL,
        "history_size": len(simulator.history)
    }


# ==========================================
# INCIDENT - set incident location
# ==========================================

@app.post("/api/incident")
def set_incident(
    latitude: float,
    longitude: float
):

    check = location_engine.validate_location(
        latitude,
        longitude
    )

    if not check:
        return {
            "success": False,
            "message": "Location is outside the supported region (Egypt)"
        }

    simulator.engine.set_incident(
        latitude,
        longitude
    )

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "message": "Incident location updated - sensor simulation now centers here"
    }


# ==========================================
# MAP / DASHBOARD
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

    events_stats = data_engine.stats()

    return {
        "status": "healthy",
        "api": "online",
        "region": "Egypt",
        "simulation_running": simulator.running,
        "simulation_history": len(simulator.history),
        "state_file": os.path.exists(STATE_FILE),
        "map_file": os.path.exists(MAP_FILE),
        "data_store": {
            "database": data_engine.db_path,
            "jsonl": data_engine.jsonl_path,
            "total_events": events_stats["total"],
            "events_by_type": events_stats["by_type"],
            "last_event": events_stats["last_event"]
        },
        "timestamp": datetime.now().isoformat()
    }