"""Deployment configuration, read once from the environment.

Two separate secrets, because the two risks are different:

  RESQ_ROVER_TOKEN     lets a client push telemetry. Without it, anyone who finds the
                       host can invent survivors and hazards on a live rescue board.
  RESQ_OPERATOR_TOKEN  lets a client send commands. Without it, anyone who finds the
                       host can stop, release or drive the rover.

Watching is not gated. A dashboard with no operator token connects read-only: it renders
everything and its controls stay locked. That is deliberate -- during an incident, more
people needing to see the board than to drive it is the normal case.

Leaving a token empty does not open the door to the internet. It relaxes the check for
clients on loopback or a private network only -- a laptop, a field radio link, the rover
on the same LAN. A request arriving from a public address with no token is refused
whether or not a token was configured, so a misconfigured deployment fails closed rather
than publishing a remotely stoppable robot.
"""
from __future__ import annotations

import hmac
import ipaddress
import os


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


ROVER_TOKEN = _env("RESQ_ROVER_TOKEN")
OPERATOR_TOKEN = _env("RESQ_OPERATOR_TOKEN")
MISSION_ID = _env("RESQ_MISSION_ID", "RESQ-001")
BROADCAST_HZ = float(_env("RESQ_BROADCAST_HZ", "8"))

ROVER_AUTH_REQUIRED = bool(ROVER_TOKEN)
OPERATOR_AUTH_REQUIRED = bool(OPERATOR_TOKEN)


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


def _flag(name: str, default: bool = True) -> bool:
    v = _env(name).lower()
    if not v:
        return default
    return v not in ("0", "false", "no", "off")


# Where the survey grid sits on Earth. The grid itself is metres from its south-west
# corner and stays that way -- rescue teams call cells, not coordinates. This is the one
# place the two frames meet, so a shelter three kilometres away can be given a bearing
# from cell D3. GRID_BEARING is the true compass bearing of the grid's +y axis, so 0
# means the grid's north edge faces true north; 90 means it has been laid out facing east.
#
# The default is a downtown Cairo incident site, which makes the shipped demo answer
# "nearest shelter" without anyone configuring anything.
ORIGIN_LAT = _float("RESQ_ORIGIN_LAT", 30.0444)
ORIGIN_LON = _float("RESQ_ORIGIN_LON", 31.2357)
GRID_BEARING = _float("RESQ_GRID_BEARING", 0.0)

# The region the shelter dataset covers. A coordinate outside it is a mistake worth
# saying out loud rather than answering with the nearest shelter on another continent.
REGION_NAME = _env("RESQ_REGION_NAME", "Egypt")
REGION_BBOX = (
    _float("RESQ_REGION_MIN_LAT", 22.0), _float("RESQ_REGION_MIN_LON", 24.7),
    _float("RESQ_REGION_MAX_LAT", 31.7), _float("RESQ_REGION_MAX_LON", 37.0),
)

# The mission record. Off is a legitimate choice -- a demo box does not need a ledger --
# but the default is on, because a rescue that leaves no trace cannot be reviewed.
RECORD = _flag("RESQ_RECORD", True)
RECORD_DIR = _env("RESQ_RECORD_DIR", "/data" if os.path.isdir("/data") else "data")
RECORD_THROTTLE_S = _float("RESQ_RECORD_THROTTLE_S", 2.0)

# Empty means no request ever leaves this machine and every route is the straight-line
# estimate. That is the field default: a Pi on a radio link must not block on a public
# routing service. Set it to https://router.project-osrm.org to use real road routing.
OSRM_URL = _env("RESQ_OSRM_URL").rstrip("/")
OSRM_TIMEOUT_S = _float("RESQ_OSRM_TIMEOUT_S", 6.0)


def check(expected: str, given: str) -> bool:
    """Constant-time compare. An empty expected token means the check is disabled."""
    if not expected:
        return True
    return hmac.compare_digest(expected, given or "")


def is_local(host: str) -> bool:
    """True for loopback, private and link-local addresses.

    Behind nginx this is the real client address, because uvicorn runs with
    --proxy-headers and reads X-Forwarded-For.
    """
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def may_ingest(token: str, host: str) -> bool:
    if ROVER_AUTH_REQUIRED:
        return check(ROVER_TOKEN, token)
    return is_local(host)


def may_command(token: str, host: str) -> bool:
    if OPERATOR_AUTH_REQUIRED:
        return check(OPERATOR_TOKEN, token)
    return is_local(host)


def warnings() -> list:
    out = []
    if not ROVER_AUTH_REQUIRED:
        out.append("RESQ_ROVER_TOKEN is unset: telemetry is accepted from private "
                   "networks only, and refused from the internet.")
    if not OPERATOR_AUTH_REQUIRED:
        out.append("RESQ_OPERATOR_TOKEN is unset: commands are accepted from private "
                   "networks only, and refused from the internet.")
    return out
