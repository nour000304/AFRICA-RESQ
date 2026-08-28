"""The wire contract. Rule 1: a sensor you cannot read is null, never a default."""
from __future__ import annotations

from server.schemas import Atmosphere, RoverFrame, Thermal

from conftest import CLEAN_AIR, frame


def test_omitted_atmosphere_field_is_none_not_zero():
    a = Atmosphere.parse({"temp_c": 21.0})
    assert a.temp_c == 21.0
    for missing in ("co_ppm", "lel_pct", "o2_pct", "pm25_ugm3"):
        assert getattr(a, missing) is None, "%s must be None, not a default" % missing


def test_explicit_null_stays_none():
    a = Atmosphere.parse({"o2_pct": None, "co_ppm": None})
    assert a.o2_pct is None and a.co_ppm is None


def test_unparseable_reading_is_none_rather_than_a_crash():
    """A garbled radio frame must not take the command server down mid-incident."""
    a = Atmosphere.parse({"co_ppm": "n/a", "o2_pct": "", "lel_pct": []})
    assert (a.co_ppm, a.o2_pct, a.lel_pct) == (None, None, None)


def test_zero_is_a_reading_and_survives():
    """0 % LEL is a measurement. It must never be confused with 'not measured'."""
    a = Atmosphere.parse({"lel_pct": 0.0})
    assert a.lel_pct == 0.0
    assert "combustible gas" not in a.missing()


def test_missing_lists_exactly_the_unread_sensors():
    assert Atmosphere.parse(CLEAN_AIR).missing() == []
    assert set(Atmosphere.parse({"temp_c": 20.0}).missing()) == {
        "CO", "combustible gas", "oxygen", "smoke density"}


def test_absent_thermal_block_is_unavailable_not_empty_and_working():
    assert Thermal.parse(None).available is False
    assert RoverFrame.parse({}).thermal.available is False


def test_detection_bbox_is_four_floats():
    f = RoverFrame.parse({"detections": [
        {"cls": "fire", "conf": 0.9, "bbox": [0.1, 0.2, 0.3, 0.4, 0.5]}]})
    assert f.detections[0].bbox == [0.1, 0.2, 0.3, 0.4]


def test_pose_zone_is_optional():
    assert RoverFrame.parse({"pose": {"x": 1.0, "y": 2.0}}).pose.zone == "--"


def test_round_trip_through_to_dict():
    f = frame(atmosphere=CLEAN_AIR)
    assert RoverFrame.parse(f.to_dict()).atmosphere.o2_pct == 20.9
