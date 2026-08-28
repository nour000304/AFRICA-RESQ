"""Wire contract between a rover and the AFRICA RESQ command server.

One rover pushes RoverFrame objects over `ws://<host>/ws/rover` (or POSTs them to
/api/frame). Everything downstream -- fusion, risk, priority, pathing -- reads only
what is defined here, so a simulator and real hardware are interchangeable.

Missing sensor blocks are represented as None, never as a safe default. A sensor the
rover could not read must arrive as null so the risk engine can report it unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def _f(d: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    v = d.get(key, default)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Pose:
    """Where the rover is, in metres from the south-west corner of the search area."""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0          # degrees, 0 = +x (east)
    zone: str = "--"              # survey cell, e.g. "B3"

    @staticmethod
    def parse(d: Optional[Dict[str, Any]]) -> "Pose":
        d = d or {}
        return Pose(
            x=_f(d, "x", 0.0) or 0.0,
            y=_f(d, "y", 0.0) or 0.0,
            heading=_f(d, "heading", 0.0) or 0.0,
            zone=str(d.get("zone", "--")),
        )


@dataclass
class Robot:
    battery_pct: Optional[float] = None
    link_quality: Optional[float] = None   # 0..1
    status: str = "idle"                   # idle | searching | holding | returning | stopped
    tilt_deg: Optional[float] = None
    speed_mps: Optional[float] = None

    @staticmethod
    def parse(d: Optional[Dict[str, Any]]) -> "Robot":
        d = d or {}
        return Robot(
            battery_pct=_f(d, "battery_pct"),
            link_quality=_f(d, "link_quality"),
            status=str(d.get("status", "idle")),
            tilt_deg=_f(d, "tilt_deg"),
            speed_mps=_f(d, "speed_mps"),
        )


@dataclass
class Atmosphere:
    """Environmental block. Any field may be None -- that means 'not measured'."""
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    co_ppm: Optional[float] = None        # carbon monoxide
    lel_pct: Optional[float] = None       # combustible gas, % of lower explosive limit
    o2_pct: Optional[float] = None        # oxygen by volume
    pm25_ugm3: Optional[float] = None     # particulates, proxy for smoke density

    @staticmethod
    def parse(d: Optional[Dict[str, Any]]) -> "Atmosphere":
        d = d or {}
        return Atmosphere(
            temp_c=_f(d, "temp_c"),
            humidity_pct=_f(d, "humidity_pct"),
            co_ppm=_f(d, "co_ppm"),
            lel_pct=_f(d, "lel_pct"),
            o2_pct=_f(d, "o2_pct"),
            pm25_ugm3=_f(d, "pm25_ugm3"),
        )

    def missing(self) -> List[str]:
        names = {
            "temp_c": "temperature",
            "co_ppm": "CO",
            "lel_pct": "combustible gas",
            "o2_pct": "oxygen",
            "pm25_ugm3": "smoke density",
        }
        return [label for key, label in names.items() if getattr(self, key) is None]


@dataclass
class Detection:
    """One vision detection. bbox is [x, y, w, h] normalised 0..1 against the frame."""
    cls: str = "unknown"
    conf: float = 0.0
    bbox: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    track_id: Optional[str] = None

    @staticmethod
    def parse(d: Dict[str, Any]) -> "Detection":
        bbox = d.get("bbox") or [0, 0, 0, 0]
        return Detection(
            cls=str(d.get("cls", "unknown")),
            conf=float(d.get("conf", 0.0)),
            bbox=[float(v) for v in bbox][:4],
            track_id=(str(d["track_id"]) if d.get("track_id") is not None else None),
        )


@dataclass
class ThermalBlob:
    """A heat region from the thermal array, with its own human-likeness estimate."""
    peak_c: float = 0.0
    bbox: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    human_like: float = 0.0     # 0..1, shape + temperature band score
    track_id: Optional[str] = None

    @staticmethod
    def parse(d: Dict[str, Any]) -> "ThermalBlob":
        bbox = d.get("bbox") or [0, 0, 0, 0]
        return ThermalBlob(
            peak_c=float(d.get("peak_c", 0.0)),
            bbox=[float(v) for v in bbox][:4],
            human_like=float(d.get("human_like", 0.0)),
            track_id=(str(d["track_id"]) if d.get("track_id") is not None else None),
        )


@dataclass
class Thermal:
    available: bool = False
    max_c: Optional[float] = None
    min_c: Optional[float] = None
    blobs: List[ThermalBlob] = field(default_factory=list)

    @staticmethod
    def parse(d: Optional[Dict[str, Any]]) -> "Thermal":
        if d is None:
            return Thermal(available=False)
        return Thermal(
            available=bool(d.get("available", True)),
            max_c=_f(d, "max_c"),
            min_c=_f(d, "min_c"),
            blobs=[ThermalBlob.parse(b) for b in (d.get("blobs") or [])],
        )


@dataclass
class Ranges:
    """Short-range obstacle distances in metres. None = that sensor is out."""
    front_m: Optional[float] = None
    left_m: Optional[float] = None
    right_m: Optional[float] = None
    rear_m: Optional[float] = None

    @staticmethod
    def parse(d: Optional[Dict[str, Any]]) -> "Ranges":
        d = d or {}
        return Ranges(
            front_m=_f(d, "front_m"),
            left_m=_f(d, "left_m"),
            right_m=_f(d, "right_m"),
            rear_m=_f(d, "rear_m"),
        )


@dataclass
class RoverFrame:
    """One tick of everything the rover knows. Sent at 2-10 Hz."""
    mission_id: str = "RESQ-001"
    seq: int = 0
    t: float = 0.0                     # rover clock, unix seconds
    mode: str = "assisted"             # manual | assisted | autonomous
    pose: Pose = field(default_factory=Pose)
    robot: Robot = field(default_factory=Robot)
    atmosphere: Atmosphere = field(default_factory=Atmosphere)
    detections: List[Detection] = field(default_factory=list)
    thermal: Thermal = field(default_factory=Thermal)
    ranges: Ranges = field(default_factory=Ranges)
    frame_jpeg: Optional[str] = None   # base64 data URI; omitted -> dashboard draws a sim view
    notes: Optional[str] = None

    @staticmethod
    def parse(d: Dict[str, Any]) -> "RoverFrame":
        return RoverFrame(
            mission_id=str(d.get("mission_id", "RESQ-001")),
            seq=int(d.get("seq", 0)),
            t=float(d.get("t", 0.0)),
            mode=str(d.get("mode", "assisted")),
            pose=Pose.parse(d.get("pose")),
            robot=Robot.parse(d.get("robot")),
            atmosphere=Atmosphere.parse(d.get("atmosphere")),
            detections=[Detection.parse(x) for x in (d.get("detections") or [])],
            thermal=Thermal.parse(d.get("thermal")),
            ranges=Ranges.parse(d.get("ranges")),
            frame_jpeg=d.get("frame_jpeg"),
            notes=d.get("notes"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
