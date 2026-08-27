import math

import requests


EARTH_RADIUS_KM = 6371.0


class RouteEngine:

    def get_route(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon
    ):

        try:

            return self._osrm_route(
                start_lat,
                start_lon,
                end_lat,
                end_lon
            )

        except Exception as e:

            # Fallback: approximate straight-line route so the demo
            # always returns something useful (e.g. offline demo)
            return self._fallback_route(
                start_lat,
                start_lon,
                end_lat,
                end_lon,
                str(e)
            )

    def _osrm_route(self, start_lat, start_lon, end_lat, end_lon):

        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{start_lon},{start_lat};"
            f"{end_lon},{end_lat}"
        )

        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true"
        }

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok":
            raise RuntimeError("OSRM returned no route")

        route = data["routes"][0]

        return {
            "success": True,
            "source": "osrm",
            "distance_m": round(route["distance"]),
            "distance_km": round(
                route["distance"] / 1000,
                2
            ),
            "duration_seconds": round(
                route["duration"]
            ),
            "duration_minutes": round(
                route["duration"] / 60,
                1
            ),
            "geometry": route["geometry"],
            "steps": route.get("legs", [])
        }

    def _haversine_km(self, lat1, lon1, lat2, lon2):

        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)

        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(lat1_r) * math.cos(lat2_r)
            * math.sin(d_lon / 2) ** 2
        )

        c = 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )

        return EARTH_RADIUS_KM * c

    def _fallback_route(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon,
        error
    ):

        distance_km = self._haversine_km(
            start_lat,
            start_lon,
            end_lat,
            end_lon
        )

        # Assume 30 km/h average emergency driving speed
        duration_minutes = (distance_km / 30.0) * 60

        geometry = {
            "type": "LineString",
            "coordinates": [
                [start_lon, start_lat],
                [end_lon, end_lat]
            ]
        }

        note = "Approximate route ({})".format(
            " ".join(str(e).split()[:6])
        )

        return {
            "success": True,
            "source": "straight_line_fallback",
            "distance_m": round(distance_km * 1000),
            "distance_km": round(distance_km, 2),
            "duration_seconds": round(duration_minutes * 60),
            "duration_minutes": round(duration_minutes, 1),
            "geometry": geometry,
            "steps": [],
            "note": note
        }