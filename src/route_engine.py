import requests


class RouteEngine:

    def get_route(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon
    ):

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
            return {
                "success": False,
                "message": "No route found"
            }

        route = data["routes"][0]

        return {
            "success": True,
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