"""The shelter dataset and the search over it.

The claims: every record is complete and inside the region it says it covers, ids are
unique, the nearest shelter is actually the nearest one, and none of it touches a network.
"""
from __future__ import annotations

import pytest

from server import config, geo, shelters

REQUIRED = ("id", "name", "city", "governorate", "type", "lat", "lon",
            "capacity", "address", "contact")


def test_the_dataset_survived_the_merge_intact():
    assert len(shelters.SHELTERS) == 38
    assert len(shelters.CITIES) == 13


def test_every_record_is_complete():
    for s in shelters.SHELTERS:
        for key in REQUIRED:
            assert key in s and s[key] not in (None, ""), "%s is missing %s" % (s.get("id"), key)


def test_ids_are_unique():
    ids = [s["id"] for s in shelters.SHELTERS]
    assert len(set(ids)) == len(ids)


def test_every_shelter_is_inside_the_region_the_deployment_covers():
    """A shelter outside the bounds would be offered to someone who cannot reach it."""
    for s in shelters.SHELTERS:
        assert geo.in_region(s["lat"], s["lon"]), "%s is outside %s" % (s["id"], config.REGION_NAME)


def test_coordinates_are_numbers_not_strings():
    for s in shelters.SHELTERS:
        assert isinstance(s["lat"], float) and isinstance(s["lon"], float)


def test_every_city_in_the_list_actually_has_a_shelter():
    for city in shelters.cities():
        assert shelters.by_city(city), "%s is offered but holds nothing" % city


def test_nearest_is_sorted_and_honours_the_limit():
    found = shelters.nearest(30.0444, 31.2357, limit=5)
    assert len(found) == 5
    assert found == sorted(found, key=lambda r: r["distance_km"])


def test_nearest_finds_the_shelter_you_are_standing_on():
    """Stand on Cairo International Stadium and it must come back first, at ~0 km."""
    stadium = shelters.get("CAI-01")
    found = shelters.nearest(stadium["lat"], stadium["lon"], limit=1)
    assert found[0]["shelter"]["id"] == "CAI-01"
    assert found[0]["distance_km"] == pytest.approx(0.0, abs=0.01)


def test_nearest_carries_a_bearing_you_can_say_out_loud():
    found = shelters.nearest(30.0444, 31.2357, limit=1)[0]
    assert 0.0 <= found["bearing_deg"] < 360.0
    assert found["direction"] in geo.COMPASS
    assert found["estimated_walk_minutes"] >= found["estimated_drive_minutes"]


def test_with_no_coordinate_it_answers_about_this_incident():
    """The operator asking "where do we take them" means from here, and the server knows here."""
    anchored = shelters.nearest(limit=1)
    explicit = shelters.nearest(config.ORIGIN_LAT, config.ORIGIN_LON, limit=1)
    assert anchored[0]["shelter"]["id"] == explicit[0]["shelter"]["id"]


def test_the_city_filter_does_not_punish_typing_under_pressure():
    assert shelters.by_city("cairo") == shelters.by_city("CAIRO")
    assert shelters.by_city("  Cairo  ")
    assert all(s["city"] == "Cairo" for s in shelters.by_city("Cairo"))


def test_no_city_means_every_city():
    assert len(shelters.by_city(None)) == len(shelters.SHELTERS)
    assert len(shelters.by_city("")) == len(shelters.SHELTERS)


def test_an_unknown_shelter_is_none_and_not_a_crash():
    assert shelters.get("NOPE-99") is None
    assert shelters.get("") is None
    assert shelters.get(None) is None


def test_a_shelter_id_is_matched_however_it_was_typed():
    assert shelters.get("cai-01")["id"] == "CAI-01"
    assert shelters.get(" CAI-01 ")["id"] == "CAI-01"


def test_narrowing_to_a_city_narrows_the_search():
    found = shelters.nearest(30.0444, 31.2357, limit=3, city="Luxor")
    assert found and all(r["shelter"]["city"] == "Luxor" for r in found)
