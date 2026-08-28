"""The survey grid the whole mission speaks in.

Rescue teams call locations by cell -- "survivor in B3" -- so every layer here uses the
same letter/number vocabulary the dashboard prints and the radio callouts use.
"""
from __future__ import annotations

from typing import List, Tuple

COLS = "ABCDEFGH"
ROWS = 6
CELL_M = 3.0                      # each cell is 3 x 3 metres
WIDTH_M = len(COLS) * CELL_M      # 24 m east-west
HEIGHT_M = ROWS * CELL_M          # 18 m north-south


def zone_of(x: float, y: float) -> str:
    """Metres -> cell name. Positions outside the grid clamp to the edge cell."""
    ci = min(len(COLS) - 1, max(0, int(x // CELL_M)))
    ri = min(ROWS - 1, max(0, int(y // CELL_M)))
    return "%s%d" % (COLS[ci], ri + 1)


def index_of(zone: str) -> Tuple[int, int]:
    """Cell name -> (column index, row index). Unknown names fall back to A1."""
    if not zone or len(zone) < 2 or zone[0].upper() not in COLS:
        return (0, 0)
    try:
        return (COLS.index(zone[0].upper()), int(zone[1:]) - 1)
    except ValueError:
        return (0, 0)


def center_of(zone: str) -> Tuple[float, float]:
    ci, ri = index_of(zone)
    return ((ci + 0.5) * CELL_M, (ri + 0.5) * CELL_M)


def name_of(ci: int, ri: int) -> str:
    return "%s%d" % (COLS[ci], ri + 1)


def all_zones() -> List[str]:
    return [name_of(c, r) for r in range(ROWS) for c in range(len(COLS))]


def neighbors(ci: int, ri: int) -> List[Tuple[int, int]]:
    """4-connected. Rescue routes are described as turns, not diagonals."""
    out = []
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c, r = ci + dc, ri + dr
        if 0 <= c < len(COLS) and 0 <= r < ROWS:
            out.append((c, r))
    return out
