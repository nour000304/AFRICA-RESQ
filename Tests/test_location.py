from location_engine import LocationEngine


def test_cairo_is_valid():
    engine = LocationEngine()
    result = engine.get_location(30.0444, 31.2357)
    assert result["valid"] is True
    assert result["country"] == "Egypt"


def test_alexandria_is_valid():
    engine = LocationEngine()
    assert engine.validate_location(31.2001, 29.9187) is True


def test_old_morocco_defaults_now_invalid():
    engine = LocationEngine()
    assert engine.validate_location(31.63, -7.99) is False


def test_outside_egypt_invalid():
    engine = LocationEngine()
    results = [
        engine.validate_location(48.85, 2.35),    # Paris
        engine.validate_location(51.50, -0.12),   # London
        engine.validate_location(0.0, 0.0)        # Gulf of Guinea
    ]
    assert all(r is False for r in results)


def test_invalid_returns_message():
    engine = LocationEngine()
    result = engine.get_location(48.85, 2.35)
    assert result["valid"] is False
    assert result["country"] is None
    assert "message" in result