import math

from src.shelter_data import SHELTERS, CITIES


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_r)
        * math.cos(lat2_r)
        * math.sin(d_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return EARTH_RADIUS_KM * c


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, in degrees."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)

    d_lon = math.radians(lon2 - lon1)

    y = math.sin(d_lon) * math.cos(lat2_r)
    x = (
        math.cos(lat1_r) * math.sin(lat2_r)
        - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(d_lon)
    )

    bearing = math.degrees(math.atan2(y, x))

    return (bearing + 360) % 360


def compass_point(bearing):
    points = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW"
    ]

    index = round(bearing / 22.5) % 16

    return points[index]


class ShelterEngine:

    def list_shelters(self, city=None):
        if not city:
            return SHELTERS

        query = city.strip().lower()

        return [
            shelter
            for shelter in SHELTERS
            if query in shelter["city"].lower()
        ]

    def list_cities(self):
        return CITIES

    def find_nearest(self, latitude, longitude, limit=3):
        results = []

        for shelter in SHELTERS:
            distance = haversine_km(
                latitude,
                longitude,
                shelter["lat"],
                shelter["lon"]
            )

            bearing = bearing_deg(
                latitude,
                longitude,
                shelter["lat"],
                shelter["lon"]
            )

            # ~5 km/h walking, ~30 km/h emergency driving
            walk_minutes = round((distance / 5.0) * 60)
            drive_minutes = round((distance / 30.0) * 60)

            result = {
                "shelter": shelter,
                "distance_km": round(distance, 2),
                "bearing_deg": round(bearing, 1),
                "direction": compass_point(bearing),
                "estimated_walk_minutes": walk_minutes,
                "estimated_drive_minutes": drive_minutes
            }

            results.append(result)

        results.sort(key=lambda r: r["distance_km"])

        return results[:limit]

    def get(self, shelter_id):
        for shelter in SHELTERS:
            if shelter["id"].lower() == shelter_id.lower():
                return shelter

        return None