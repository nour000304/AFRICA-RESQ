"""Where the survey grid sits on Earth.

The grid is metres from its south-west corner and stays that way: a rescue team calls
"survivor in B3", not a pair of decimals. But a shelter is three kilometres away and a
road route is a road route, and neither of those questions can be asked in metres from a
corner. This module is the single joint between the two frames -- everything above it
gets a latitude and a longitude, and nothing below it has to learn what GPS is.

The anchor is configuration, not a reading. `config.ORIGIN_LAT/LON` is where the corner
was surveyed and `config.GRID_BEARING` is the true bearing of the grid's +y axis, so a
grid laid out along a street rather than along the meridian still resolves correctly.
Both are declared by whoever set the mission up; nothing here infers them.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from . import config, grid

EARTH_RADIUS_KM = 6371.0
M_PER_DEG_LAT = 111_320.0

# Walking pace, and the speed an emergency vehicle actually averages through a city --
# not a road speed limit. Both are estimates and are labelled as such wherever they land.
WALK_KMH = 5.0
DRIVE_KMH = 30.0

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def anchor() -> Dict[str, float]:
    return {"lat": config.ORIGIN_LAT, "lon": config.ORIGIN_LON,
            "bearing_deg": config.GRID_BEARING}


def latlon_of(x_m: float, y_m: float) -> Tuple[float, float]:
    """Grid metres -> (lat, lon).

    A flat-earth offset from the origin. Over a 24 x 18 m survey area the curvature
    error is far below a centimetre, and the grid is never larger than one incident.
    """
    b = math.radians(config.GRID_BEARING)
    north_m = y_m * math.cos(b) - x_m * math.sin(b)
    east_m = y_m * math.sin(b) + x_m * math.cos(b)

    lat = config.ORIGIN_LAT + north_m / M_PER_DEG_LAT
    # Longitude degrees shrink towards the poles. Taken at the origin, not at the
    # destination, so the transform stays invertible.
    scale = M_PER_DEG_LAT * math.cos(math.radians(config.ORIGIN_LAT))
    lon = config.ORIGIN_LON + east_m / max(1e-9, scale)
    return (lat, lon)


def latlon_of_zone(zone: str) -> Tuple[float, float]:
    """The centre of a survey cell, on Earth."""
    x, y = grid.center_of(zone)
    return latlon_of(x, y)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing from the first point to the second, 0-360 clockwise of north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass_point(bearing: float) -> str:
    """A bearing as something sayable over a radio."""
    return COMPASS[int(round((bearing % 360.0) / 22.5)) % 16]


def walk_minutes(distance_km: float) -> int:
    return int(round(distance_km / WALK_KMH * 60))


def drive_minutes(distance_km: float) -> int:
    return int(round(distance_km / DRIVE_KMH * 60))


def in_region(lat: Optional[float], lon: Optional[float]) -> bool:
    """Is this coordinate inside the region the shelter dataset covers?"""
    if lat is None or lon is None:
        return False
    min_lat, min_lon, max_lat, max_lon = config.REGION_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def describe(lat: Optional[float], lon: Optional[float]) -> Dict[str, object]:
    """The shape `GET /api/location` answers with."""
    if lat is None or lon is None:
        return {"valid": False, "region": None, "latitude": lat, "longitude": lon,
                "message": "No coordinate given."}
    if not in_region(lat, lon):
        return {"valid": False, "region": None, "latitude": lat, "longitude": lon,
                "message": "Outside %s, the region this deployment has shelter data for."
                           % config.REGION_NAME}
    return {"valid": True, "region": config.REGION_NAME,
            "latitude": lat, "longitude": lon}
