"""Getting a vehicle from one coordinate to another.

Two different questions live under the word "route" in this codebase and they must not be
confused. server/pathing.py plans the rover through the survey grid, over the hazard field
it costs against, and it is the one that decides whether anybody walks into a cell. This
module does the other thing: roads, between two points on a map, for the ambulance meeting
the rover's survivors at a shelter. It knows nothing about hazards and must never be read
as saying a road is safe.

It came in with the teammates' src/route_engine.py, with one change that matters.
Upstream, every call reached for a public routing service and fell back to a straight line
when that failed. Here the network is opt-in: with RESQ_OSRM_URL unset -- the default, and
what a Pi on a radio link runs -- no request is attempted at all and every answer is the
haversine estimate. The fallback is not an error path in the field. It is the field.

Both answers carry `source`, so nothing downstream can mistake an estimate for a routed
distance.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from . import config, geo

SOURCE_ROUTED = "osrm"
SOURCE_ESTIMATE = "straight_line_estimate"


def _line(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Dict[str, Any]:
    return {"type": "LineString",
            "coordinates": [[start_lon, start_lat], [end_lon, end_lat]]}


# Said on every estimate, whatever the reason for it. A straight line between two points
# is a lower bound on the road between them, so the real drive is always at least this and
# usually longer. The reason changes; the caveat does not, because a client that drops the
# reason must not end up presenting a lower bound as a drive time.
ESTIMATE_CAVEAT = "Straight-line estimate. A road route is at least this long."


def estimate(start_lat: float, start_lon: float, end_lat: float, end_lon: float,
             because: Optional[str] = None) -> Dict[str, Any]:
    """Distance as the crow flies, at a city driving average. No network, ever."""
    km = geo.haversine_km(start_lat, start_lon, end_lat, end_lon)
    minutes = km / geo.DRIVE_KMH * 60.0
    out = {
        "success": True,
        "source": SOURCE_ESTIMATE,
        "distance_m": round(km * 1000),
        "distance_km": round(km, 2),
        "duration_seconds": round(minutes * 60),
        "duration_minutes": round(minutes, 1),
        "geometry": _line(start_lat, start_lon, end_lat, end_lon),
        "steps": [],
        "note": ESTIMATE_CAVEAT + (" " + because if because else ""),
    }
    return out


def _fetch_osrm(start_lat: float, start_lon: float,
                end_lat: float, end_lon: float) -> Dict[str, Any]:
    """Blocking. Called in a worker thread, never on the loop."""
    url = "%s/route/v1/driving/%s,%s;%s,%s?%s" % (
        config.OSRM_URL, start_lon, start_lat, end_lon, end_lat,
        urllib.parse.urlencode({"overview": "full", "geometries": "geojson",
                                "steps": "true"}))
    request = urllib.request.Request(url, headers={"User-Agent": "africa-resq"})
    with urllib.request.urlopen(request, timeout=config.OSRM_TIMEOUT_S) as response:
        body = json.loads(response.read().decode("utf-8"))

    if body.get("code") != "Ok" or not body.get("routes"):
        raise RuntimeError(body.get("message") or "no route")

    best = body["routes"][0]
    return {
        "success": True,
        "source": SOURCE_ROUTED,
        "distance_m": round(best["distance"]),
        "distance_km": round(best["distance"] / 1000.0, 2),
        "duration_seconds": round(best["duration"]),
        "duration_minutes": round(best["duration"] / 60.0, 1),
        "geometry": best.get("geometry"),
        "steps": best.get("legs") or [],
    }


async def plan(start_lat: float, start_lon: float,
               end_lat: float, end_lon: float) -> Dict[str, Any]:
    """A road route if this deployment has one to reach, an estimate otherwise.

    Never raises and never blocks the broadcast: the request runs in a worker thread with
    a timeout, and anything that goes wrong with it degrades to the estimate with the
    reason attached rather than failing the caller.
    """
    if not config.OSRM_URL:
        return estimate(start_lat, start_lon, end_lat, end_lon,
                        "No routing service is configured, so nothing was asked of "
                        "the network.")
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_osrm, start_lat, start_lon, end_lat, end_lon),
            timeout=config.OSRM_TIMEOUT_S + 1.0)
    except Exception as exc:
        reason = str(exc).strip() or exc.__class__.__name__
        return estimate(start_lat, start_lon, end_lat, end_lon,
                        "The routing service did not answer (%s)." % reason[:120])
