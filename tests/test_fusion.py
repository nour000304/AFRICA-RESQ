"""Survivor confirmation. The claims the README makes about fusion, as tests."""
from __future__ import annotations

from server.fusion import confidence_band, fuse_person
from server.schemas import Atmosphere, Detection, Thermal

from conftest import CLEAN_AIR, blob, person


def _fuse(conf=0.9, thermal=None, atmo=None, inside=True):
    return fuse_person(
        Detection.parse(person(conf)),
        Thermal.parse(thermal if thermal is not None else {"available": False, "blobs": []}),
        Atmosphere.parse(atmo or {}),
        inside_search_area=inside,
    )


def test_agreement_compounds():
    camera_only = _fuse(0.9)
    confirmed = _fuse(0.9, {"available": True, "blobs": [blob()]})
    assert confirmed["confidence"] > camera_only["confidence"]
    assert confirmed["thermal_confirmed"] is True


def test_a_working_array_that_sees_nothing_is_evidence_against():
    """Not neutral. The README calls this out and the number has to back it up."""
    camera_only = _fuse(0.9)                                   # no array fitted
    array_sees_nothing = _fuse(0.9, {"available": True, "blobs": []})
    assert array_sees_nothing["confidence"] < camera_only["confidence"]
    assert array_sees_nothing["thermal_confirmed"] is False


def test_an_unavailable_sensor_contributes_exactly_zero():
    r = _fuse(0.9)
    thermal_term = next(t for t in r["terms"] if t["source"] == "thermal")
    assert thermal_term["delta"] == 0.0
    assert "thermal" in r["missing_evidence"]


def test_thermal_is_discounted_in_a_hot_scene():
    cool = _fuse(0.9, {"available": True, "blobs": [blob()]}, {"temp_c": 20.0})
    hot = _fuse(0.9, {"available": True, "blobs": [blob()]}, {"temp_c": 55.0})
    cool_delta = next(t for t in cool["terms"] if t["source"] == "thermal")["delta"]
    hot_delta = next(t for t in hot["terms"] if t["source"] == "thermal")["delta"]
    assert hot_delta < cool_delta
    assert "discounted" in next(t for t in hot["terms"] if t["source"] == "thermal")["detail"]


def test_heat_outside_the_human_band_does_not_confirm_a_person():
    """A 300 C blob is a fire. Agreeing in position does not make it a survivor."""
    body = _fuse(0.9, {"available": True, "blobs": [blob(peak_c=36.4)]})
    metal = _fuse(0.9, {"available": True, "blobs": [blob(peak_c=300.0)]})
    assert metal["confidence"] < body["confidence"]


def test_a_camera_only_contact_is_not_promoted_to_confirmed():
    """The README's claim. A single modality must not reach the top band alone."""
    r = _fuse(0.95)
    assert confidence_band(r["confidence"]) != "confirmed"


def test_thermal_agreement_requires_overlapping_boxes():
    """Heat on the far side of the room is not corroboration of this person."""
    elsewhere = _fuse(0.9, {"available": True,
                            "blobs": [blob(bbox=[0.02, 0.02, 0.05, 0.05])]})
    assert elsewhere["thermal_confirmed"] is False


def test_unsurvivable_heat_counts_against():
    survivable = _fuse(0.9, atmo=CLEAN_AIR)
    furnace = _fuse(0.9, atmo=dict(CLEAN_AIR, temp_c=90.0))
    assert furnace["confidence"] < survivable["confidence"]


def test_outside_the_search_area_counts_against():
    assert _fuse(0.9, inside=False)["confidence"] < _fuse(0.9, inside=True)["confidence"]


def test_terms_sum_to_the_reported_log_odds():
    """The chips under a survivor are the arithmetic, not a summary of it."""
    r = _fuse(0.9, {"available": True, "blobs": [blob()]}, CLEAN_AIR)
    assert abs(sum(t["delta"] for t in r["terms"]) - r["log_odds"]) < 0.01


def test_bands_are_ordered():
    assert confidence_band(0.9) == "confirmed"
    assert confidence_band(0.7) == "probable"
    assert confidence_band(0.4) == "possible"
    assert confidence_band(0.1) == "weak"
