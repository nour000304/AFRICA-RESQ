from shelter_engine import ShelterEngine
from shelter_data import SHELTERS, CITIES


def test_shelter_dataset_is_populated():
    assert len(SHELTERS) >= 20


def test_shelter_dataset_covers_multiple_egyptian_cities():
    assert len(CITIES) >= 8
    assert "Cairo" in CITIES
    assert "Alexandria" in CITIES


def test_every_shelter_has_valid_coordinates():
    for shelter in SHELTERS:
        assert 22.0 <= shelter["lat"] <= 31.7
        assert 24.7 <= shelter["lon"] <= 37.0
        assert shelter["id"]
        assert shelter["name"]
        assert shelter["capacity"] > 0


def test_list_shelters_all():
    engine = ShelterEngine()
    assert len(engine.list_shelters()) == len(SHELTERS)


def test_list_shelters_by_city():
    engine = ShelterEngine()
    results = engine.list_shelters("alexandria")
    assert len(results) > 0
    assert all(r["city"].lower() == "alexandria" for r in results)


def test_find_nearest_returns_sorted():
    engine = ShelterEngine()
    # Tahrir Square, Cairo
    results = engine.find_nearest(30.0477, 31.2336, limit=3)
    assert len(results) == 3
    assert results[0]["distance_km"] <= results[1]["distance_km"]
    assert results[1]["distance_km"] <= results[2]["distance_km"]
    assert results[0]["direction"] in ("N", "S", "E", "W", "NE", "NW", "SE", "SW",
                                       "NNE", "ENE", "ESE", "SSE", "SSW", "WSW", "WNW", "NNW")


def test_find_nearest_from_cairo_finds_cairo_shelter():
    engine = ShelterEngine()
    results = engine.find_nearest(30.0477, 31.2336, limit=1)
    # nearest should be within a few km of Tahrir
    assert results[0]["distance_km"] < 10


def test_nearest_distance_is_sane():
    engine = ShelterEngine()
    results = engine.find_nearest(30.0444, 31.2357, limit=1)
    assert results[0]["distance_km"] >= 0
    assert results[0]["estimated_walk_minutes"] >= 0
    assert results[0]["estimated_drive_minutes"] >= 0


def test_get_shelter_by_id():
    engine = ShelterEngine()
    assert engine.get("CAI-01") is not None
    assert engine.get("cai-01") is not None
    assert engine.get("DOES-NOT-EXIST") is None


def test_haversine_known_distance():
    from shelter_engine import haversine_km
    # Cairo to Alexandria approx 180-215 km by great circle
    km = haversine_km(30.0444, 31.2357, 31.2001, 29.9187)
    assert 170 < km < 230