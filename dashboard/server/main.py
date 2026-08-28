"""AFRICA RESQ command server.

  rover  --ws--> /ws/rover  -->  Mission  -->  /ws/dashboard  --ws--> operator
                     ^                                  |
                     +--------- commands ---------------+

The server owns nothing the rover owns. It fuses, scores, plans and remembers, then
broadcasts one MissionState at a fixed rate so every open dashboard shows the same
picture. Operator commands travel the other way down the same sockets.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import pathlib
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import compat, config, geo, recorder as recording, route, shelters
from .schemas import RoverFrame
from .state import Mission

BROADCAST_HZ = config.BROADCAST_HZ
DASHBOARD_DIR = pathlib.Path(__file__).resolve().parent.parent / "dashboard"

# Not every base image registers these, and a font served as application/octet-stream
# is skipped by some proxies' compression and cache rules.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")

# The event stream is for REST clients; the dashboard has the websocket. One state
# message a second is plenty for a chart or a map marker, and eight would spend the link
# on frames nobody redraws.
STATE_STREAM_PERIOD_S = 1.0


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """One run of the server: open the record, start broadcasting, and close both.

    The recorder is built here rather than at import because its queues belong to the
    loop that is about to run, and because a second run of this app in one process --
    which is what a test suite is -- must start with an empty ledger and an empty
    throttle rather than inheriting the last one's.
    """
    global recorder
    mission.log("info", "Command server up. Waiting for a rover.")
    for w in config.warnings():
        print("WARNING: %s" % w)
        mission.log("warning", w)

    recorder = recording.Recorder(
        recording.open_ledger(config.RECORD_DIR,
                              on_error=lambda m: mission.log("warning", m))
        if config.RECORD else None,
        throttle_s=config.RECORD_THROTTLE_S,
        on_error=lambda m: mission.log("warning", m))
    await recorder.start()

    if recorder.enabled:
        mission.log("info", "Recording this mission to %s." % config.RECORD_DIR)
        mission.recorder = recorder
    elif not config.RECORD:
        mission.log("warning", "Mission recording is off. This incident leaves no record.")

    task = asyncio.create_task(_broadcast_loop())
    try:
        yield
    finally:
        task.cancel()
        mission.recorder = None
        await recorder.stop()


app = FastAPI(title="AFRICA RESQ", version="1.0", lifespan=lifespan)
mission = Mission(config.MISSION_ID)
# Replaced by the lifespan with one bound to the running loop. Until then it is a
# recorder with no store, which accepts every call and keeps nothing -- so importing this
# module without running it (a doc build, a route dump) costs no file handles.
recorder = recording.Recorder(None)
dashboards: Set[WebSocket] = set()
rovers: Set[WebSocket] = set()

# Sockets allowed to send commands. Membership is granted at connect time or later, by
# the client presenting the operator token; it is never inferred from anything else.
commanders: Set[WebSocket] = set()


def _presented(ws: WebSocket) -> str:
    """A token may arrive as ?token= or as the x-resq-token header."""
    return (ws.query_params.get("token")
            or ws.headers.get("x-resq-token")
            or "")


def _client(ws: WebSocket) -> str:
    return ws.client.host if ws.client else ""


async def _send_command(cmd: Dict[str, Any]) -> None:
    """Push an operator command to every connected rover."""
    dead = []
    for ws in rovers:
        try:
            await ws.send_text(json.dumps(cmd))
        except Exception:
            dead.append(ws)
    for ws in dead:
        rovers.discard(ws)


async def _broadcast_loop() -> None:
    period = 1.0 / BROADCAST_HZ
    was_connected = False
    published_at = 0.0
    while True:
        await asyncio.sleep(period)
        listeners = bool(recorder.subscribers)
        if not dashboards and not listeners:
            continue
        snap = mission.snapshot()
        if was_connected and not snap.get("connected"):
            mission.log("critical", "Radio link lost. Rover held at last commanded state.")
        was_connected = bool(snap.get("connected"))

        # What the stream sends is what /api/full answers with -- the same projection of
        # the same live state -- so a client polling and a client streaming can never
        # disagree about a score.
        now = time.time()
        if listeners and now - published_at >= STATE_STREAM_PERIOD_S:
            published_at = now
            recorder.publish_state(compat.full(snap))

        if not dashboards:
            continue
        payload = json.dumps({"type": "state", "state": snap})
        dead = []
        for ws in dashboards:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            dashboards.discard(ws)


# --------------------------------------------------------------------------- rover
@app.websocket("/ws/rover")
async def ws_rover(ws: WebSocket) -> None:
    await ws.accept()
    if not config.may_ingest(_presented(ws), _client(ws)):
        mission.log("warning", "Rejected a rover connection from %s." % (_client(ws) or "?"))
        await ws.close(code=1008)
        return
    rovers.add(ws)
    mission.log("info", "Rover online.")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                mission.ingest(RoverFrame.parse(json.loads(raw)))
            except Exception as exc:                      # a malformed frame is not fatal
                mission.log("warning", "Dropped a malformed frame: %s" % exc)
    except WebSocketDisconnect:
        pass
    finally:
        rovers.discard(ws)
        mission.log("warning", "Rover disconnected.")


@app.post("/api/frame")
async def post_frame(request: Request) -> JSONResponse:
    """HTTP ingest for rovers without a websocket client."""
    token = request.headers.get("x-resq-token") or request.query_params.get("token") or ""
    host = request.client.host if request.client else ""
    if not config.may_ingest(token, host):
        return JSONResponse({"ok": False, "error": "unauthorised"}, status_code=401)
    try:
        mission.ingest(RoverFrame.parse(await request.json()))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True, "seq": mission.seq})


# ----------------------------------------------------------------------- dashboard
@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket) -> None:
    """Anyone may watch. Only a client holding the operator token may command."""
    await ws.accept()
    dashboards.add(ws)
    if config.may_command(_presented(ws), _client(ws)):
        commanders.add(ws)
    await _send_hello(ws)
    await ws.send_text(json.dumps({"type": "state", "state": mission.snapshot()}))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("cmd") == "auth":
                if config.may_command(str(msg.get("token", "")), _client(ws)):
                    commanders.add(ws)
                    mission.log("info", "Operator unlocked the controls.")
                else:
                    commanders.discard(ws)
                await _send_hello(ws)
                continue
            if ws not in commanders:
                await ws.send_text(json.dumps({
                    "type": "denied",
                    "reason": "This dashboard is watching only. Unlock the controls to command the rover.",
                }))
                continue
            await _handle_command(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        dashboards.discard(ws)
        commanders.discard(ws)


async def _send_hello(ws: WebSocket) -> None:
    await ws.send_text(json.dumps({
        "type": "hello",
        "can_command": ws in commanders,
        "auth_required": config.OPERATOR_AUTH_REQUIRED or not config.is_local(_client(ws)),
        "rover_auth_required": config.ROVER_AUTH_REQUIRED,
    }))


async def _handle_command(cmd: Dict[str, Any]) -> None:
    kind = cmd.get("cmd")
    if kind == "estop":
        mission.estop = bool(cmd.get("on", True))
        mission.log("critical" if mission.estop else "info",
                    "Emergency stop engaged by operator." if mission.estop
                    else "Emergency stop cleared. Rover may move.")
        await _send_command({"cmd": "estop", "on": mission.estop})
    elif kind == "mode":
        mode = str(cmd.get("mode", "assisted"))
        mission.operator_mode = mode
        mission.log("info", "Mode set to %s by operator." % mode)
        await _send_command({"cmd": "mode", "mode": mode})
    elif kind == "drive":
        await _send_command(cmd)
    elif kind == "mark":
        mission.log("info", str(cmd.get("text", "Operator mark."))[:160])


@app.get("/api/state")
async def get_state() -> JSONResponse:
    return JSONResponse(mission.snapshot())


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "ok": True, "rovers": len(rovers), "dashboards": len(dashboards),
        "auth": {"rover": config.ROVER_AUTH_REQUIRED, "operator": config.OPERATOR_AUTH_REQUIRED},
        "last_frame_age_s": round(time.time() - mission.last_frame_at, 2)
        if mission.last_frame_at else None,
    })


# ------------------------------------------------------- REST compatibility layer
# The shape morerayad/AFRICA-RESQ published for the frontend team, projected from this
# server's live state instead of from a state.json file. See server/compat.py.

@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse(compat.status(mission.snapshot()))


@app.get("/api/detection")
async def api_detection() -> JSONResponse:
    return JSONResponse(compat.detection(mission.snapshot()))


@app.get("/api/risk")
async def api_risk() -> JSONResponse:
    return JSONResponse(compat.risk(mission.snapshot()))


@app.get("/api/full")
async def api_full() -> JSONResponse:
    return JSONResponse(compat.full(mission.snapshot()))


# ------------------------------------------------------------------------ the record
# The query surface over server/recorder.py, in the shape the teammates published for the
# frontend team. Reading is open, like the dashboard socket -- during an incident more
# people need to see the board than to touch it. Writing is not: a POST here puts a
# detection on a live rescue record, so it goes behind the same gate as /api/frame.

SSE_KEEPALIVE_S = 15.0


@app.get("/api/events")
async def api_events(type: Optional[str] = None, source: Optional[str] = None,
                     start: Optional[str] = None, end: Optional[str] = None,
                     limit: int = 100, offset: int = 0) -> JSONResponse:
    rows = await recorder.query(event_type=type, source=source, start=start, end=end,
                                limit=limit, offset=offset)
    return JSONResponse({"count": len(rows), "recording": recorder.enabled, "events": rows})


@app.get("/api/events/latest")
async def api_events_latest(limit: int = 20) -> JSONResponse:
    return JSONResponse({
        "recording": recorder.enabled,
        "events": await recorder.query(limit=limit),
        "state": recorder.latest_state or compat.full(mission.snapshot()),
        "stats": await recorder.stats(),
    })


@app.get("/api/events/stats")
async def api_events_stats(since: Optional[str] = None) -> JSONResponse:
    return JSONResponse(await recorder.stats(since))


@app.get("/api/events/export")
async def api_events_export() -> JSONResponse:
    rows = await recorder.export()
    return JSONResponse({"count": len(rows), "events": rows})


@app.post("/api/events")
async def api_events_ingest(request: Request) -> JSONResponse:
    token = request.headers.get("x-resq-token") or request.query_params.get("token") or ""
    host = request.client.host if request.client else ""
    if not config.may_ingest(token, host):
        return JSONResponse({"ok": False, "error": "unauthorised"}, status_code=401)
    if not recorder.enabled:
        return JSONResponse({"ok": False, "error": "This server is not recording."},
                            status_code=503)
    try:
        fields = recording.parse_ingest(await request.json())
    except (ValueError, json.JSONDecodeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    # Never throttled: an outside system reporting a detection does it once, and
    # collapsing it into a rover's telemetry window would lose the only record of it.
    row = recorder.record(throttle=False, **fields)
    return JSONResponse({"ok": row is not None, "event": row})


@app.get("/api/events/stream")
async def api_events_stream() -> StreamingResponse:
    """The live feed, for clients that are not the dashboard.

    Server-sent events rather than a websocket, because the thing on the other end is
    usually a chart or a map with no command to send back. The `state` messages are
    exactly what /api/full answers with, so a client streaming and a client polling can
    never disagree about a score.
    """
    async def feed():
        channel = recorder.subscribe()
        try:
            yield "data: %s\n\n" % json.dumps({
                "kind": "hello",
                "mission_id": mission.mission_id,
                "recording": recorder.enabled,
                "stats": await recorder.stats(),
            }, default=str)
            while True:
                try:
                    message = await asyncio.wait_for(channel.get(), timeout=SSE_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    # A comment frame. A quiet mission must not look like a dropped
                    # connection to whatever proxy sits in front of this.
                    yield ": still here\n\n"
                    continue
                yield "data: %s\n\n" % message
        finally:
            recorder.unsubscribe(channel)

    return StreamingResponse(feed(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",       # nginx would otherwise hold the stream in a buffer
    })


# ------------------------------------------------------------------ where to send them
# The shelter dataset and the search over it arrived with the merge of the teammates'
# repository. Both are stdlib arithmetic over a table of coordinates, so every answer
# below is available with the uplink down -- which is when the question gets asked.

@app.get("/api/shelters")
async def api_shelters(city: Optional[str] = None) -> JSONResponse:
    found = shelters.by_city(city)
    return JSONResponse({"count": len(found), "city": city, "shelters": found})


@app.get("/api/shelters/cities")
async def api_shelter_cities() -> JSONResponse:
    return JSONResponse({"count": len(shelters.CITIES), "cities": shelters.cities()})


@app.get("/api/nearest_shelter")
async def api_nearest_shelter(latitude: Optional[float] = None,
                              longitude: Optional[float] = None,
                              limit: int = 3,
                              city: Optional[str] = None) -> JSONResponse:
    """Omit the coordinate and the mission anchor is used, because the operator asking
    where to take people means from this incident, and the server already knows where
    this incident is."""
    origin_given = latitude is not None and longitude is not None
    if origin_given and not geo.in_region(latitude, longitude):
        return JSONResponse({"success": False, "error": geo.describe(latitude, longitude)},
                            status_code=422)
    a = geo.anchor()
    lat = latitude if origin_given else a["lat"]
    lon = longitude if origin_given else a["lon"]
    return JSONResponse({
        "success": True,
        "latitude": lat, "longitude": lon,
        "origin": "given" if origin_given else "mission_anchor",
        "nearest": shelters.nearest(lat, lon, limit=limit, city=city),
    })


@app.get("/api/shelter/{shelter_id}")
async def api_shelter(shelter_id: str) -> JSONResponse:
    found = shelters.get(shelter_id)
    if found is None:
        return JSONResponse({"success": False, "error": "No shelter with id %s." % shelter_id},
                            status_code=404)
    return JSONResponse({"success": True, "shelter": found})


@app.get("/api/route")
async def api_route(start_lat: float, start_lon: float,
                    end_lat: float, end_lon: float) -> JSONResponse:
    """Roads, for the vehicle meeting the survivors -- not the rover's route through the
    grid, which is server/pathing.py and is the only one that knows about hazards."""
    for lat, lon in ((start_lat, start_lon), (end_lat, end_lon)):
        if not geo.in_region(lat, lon):
            return JSONResponse({"success": False, "error": geo.describe(lat, lon)},
                                status_code=422)
    return JSONResponse(await route.plan(start_lat, start_lon, end_lat, end_lon))


@app.get("/api/route/shelter/{shelter_id}")
async def api_route_to_shelter(shelter_id: str, start_lat: Optional[float] = None,
                               start_lon: Optional[float] = None) -> JSONResponse:
    """From the incident to one shelter. With no start given, from the mission anchor."""
    target = shelters.get(shelter_id)
    if target is None:
        return JSONResponse({"success": False, "error": "No shelter with id %s." % shelter_id},
                            status_code=404)
    a = geo.anchor()
    lat = start_lat if start_lat is not None else a["lat"]
    lon = start_lon if start_lon is not None else a["lon"]
    planned = await route.plan(lat, lon, target["lat"], target["lon"])
    planned["shelter"] = target
    planned["from"] = {"lat": lat, "lon": lon,
                       "origin": "given" if start_lat is not None else "mission_anchor"}
    return JSONResponse(planned)


@app.get("/api/location")
async def api_location(latitude: Optional[float] = None,
                       longitude: Optional[float] = None) -> JSONResponse:
    return JSONResponse(geo.describe(latitude, longitude))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
