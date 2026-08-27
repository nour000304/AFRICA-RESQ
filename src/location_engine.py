class LocationEngine:

    def __init__(self):
        self.country = "Morocco"

    def validate_location(self, latitude, longitude):

        # Approximate Morocco boundaries
        if not (27.0 <= latitude <= 36.0):
            return False

        if not (-13.5 <= longitude <= -1.0):
            return False

        return True

    def get_location(self, latitude, longitude):

        if not self.validate_location(latitude, longitude):
            return {
                "valid": False,
                "country": None,
                "latitude": latitude,
                "longitude": longitude
            }

        return {
            "valid": True,
            "country": "Morocco",
            "latitude": latitude,
            "longitude": longitude
        }