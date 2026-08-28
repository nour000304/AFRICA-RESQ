"""Routing between two coordinates.

The claims: with no routing service configured nothing is asked of the network, a service
that fails costs an estimate rather than the request, and no answer can be mistaken for
the other kind.

This is the road route for the vehicle meeting the survivors. The rover's route through
the grid is server/pathing.py, is the only one that knows about hazards, and is tested in
test_grid_and_pathing.py.
"""
from __future__ import annotations

import asyncio

import pytest

from server import config, geo, route


def plan(*args):
    return asyncio.run(route.plan(*args))


CAIRO = (30.0444, 31.2357)
STADIUM = (30.069113, 31.312407)


def test_with_no_service_configured_nothing_touches_the_network(monkeypatch):
    """The field default. A Pi on a radio link must not block on a public service."""
    monkeypatch.setattr(config, "OSRM_URL", "")

    def explode(*a, **k):
        raise AssertionError("a request was attempted with no service configured")
    monkeypatch.setattr(route, "_fetch_osrm", explode)

    answer = plan(*CAIRO, *STADIUM)
    assert answer["success"] and answer["source"] == route.SOURCE_ESTIMATE
    assert "nothing was asked of the network" in answer["note"]


def test_an_estimate_says_it_is_one(monkeypatch):
    monkeypatch.setattr(config, "OSRM_URL", "")
    answer = plan(*CAIRO, *STADIUM)
    assert answer["source"] != route.SOURCE_ROUTED
    assert "estimate" in answer["note"].lower()


def test_the_estimate_is_the_distance_on_the_ground(monkeypatch):
    monkeypatch.setattr(config, "OSRM_URL", "")
    answer = plan(*CAIRO, *STADIUM)
    km = geo.haversine_km(*CAIRO, *STADIUM)
    assert answer["distance_km"] == pytest.approx(round(km, 2))
    assert answer["distance_m"] == round(km * 1000)


def test_a_straight_line_is_never_longer_than_the_road(monkeypatch):
    """Which is why it is safe to present as "at least" and never as "about"."""
    monkeypatch.setattr(config, "OSRM_URL", "")
    answer = plan(*CAIRO, *STADIUM)
    assert answer["distance_km"] <= 20.0
    assert "at least" in answer["note"]


def test_the_geometry_is_drawable_geojson(monkeypatch):
    monkeypatch.setattr(config, "OSRM_URL", "")
    geometry = plan(*CAIRO, *STADIUM)["geometry"]
    assert geometry["type"] == "LineString"
    # GeoJSON is longitude first. Getting this backwards puts Cairo in the Indian Ocean.
    assert geometry["coordinates"][0] == [CAIRO[1], CAIRO[0]]
    assert geometry["coordinates"][-1] == [STADIUM[1], STADIUM[0]]


def test_a_service_that_fails_costs_an_estimate_and_not_the_request(monkeypatch):
    monkeypatch.setattr(config, "OSRM_URL", "https://routing.invalid")

    def fail(*a, **k):
        raise OSError("Name or service not known")
    monkeypatch.setattr(route, "_fetch_osrm", fail)

    answer = plan(*CAIRO, *STADIUM)
    assert answer["success"] and answer["source"] == route.SOURCE_ESTIMATE
    assert "did not answer" in answer["note"]
    assert "Name or service not known" in answer["note"]


def test_a_service_that_hangs_does_not_hang_the_caller(monkeypatch):
    """Timed around the call, not around the loop.

    asyncio.run waits for its thread pool on the way out, so a test that timed the whole
    of it would be measuring the abandoned worker draining rather than what the request
    cost -- which on a live server, whose loop outlives every request, is nothing.
    """
    import time
    monkeypatch.setattr(config, "OSRM_URL", "https://routing.invalid")
    monkeypatch.setattr(config, "OSRM_TIMEOUT_S", 0.05)
    monkeypatch.setattr(route, "_fetch_osrm", lambda *a, **k: time.sleep(5))

    async def timed():
        started = time.monotonic()
        answer = await route.plan(*CAIRO, *STADIUM)
        return time.monotonic() - started, answer

    took, answer = asyncio.run(timed())
    assert took < 3.0, "the caller waited on a service that never answered"
    assert answer["source"] == route.SOURCE_ESTIMATE
    assert "did not answer" in answer["note"]


def test_a_routed_answer_is_labelled_as_routed(monkeypatch):
    monkeypatch.setattr(config, "OSRM_URL", "https://routing.example")
    monkeypatch.setattr(route, "_fetch_osrm", lambda *a, **k: {
        "success": True, "source": route.SOURCE_ROUTED, "distance_m": 9100,
        "distance_km": 9.1, "duration_seconds": 780, "duration_minutes": 13.0,
        "geometry": {"type": "LineString", "coordinates": []}, "steps": []})

    answer = plan(*CAIRO, *STADIUM)
    assert answer["source"] == route.SOURCE_ROUTED
    assert "note" not in answer, "a routed answer needs no apology"
