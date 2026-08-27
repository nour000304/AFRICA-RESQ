class LocationEngine:

    def __init__(self):
        self.country = "Egypt"

        # Approximate Egypt boundaries
        self.min_lat = 22.0
        self.max_lat = 31.7
        self.min_lon = 24.7
        self.max_lon = 37.0

    def validate_location(self, latitude, longitude):

        if not (self.min_lat <= latitude <= self.max_lat):
            return False

        if not (self.min_lon <= longitude <= self.max_lon):
            return False

        return True

    def get_location(self, latitude, longitude):

        if not self.validate_location(latitude, longitude):
            return {
                "valid": False,
                "country": None,
                "latitude": latitude,
                "longitude": longitude,
                "message": "Location is outside the supported region"
            }

        return {
            "valid": True,
            "country": "Egypt",
            "latitude": latitude,
            "longitude": longitude
        }