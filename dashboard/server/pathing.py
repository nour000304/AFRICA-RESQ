"""Risk-aware route planning across the survey grid.

The shortest route through a burning building is rarely the one you send people down.
Two routes are always produced from the same hazard map -- the fastest and the safest --
so the operator sees the trade they are being asked to accept rather than a single
recommendation with no alternative.

Cost model: every step pays its 3 m of distance plus a penalty proportional to the risk
of the cell entered. Cells above the impassable threshold are removed from the graph.
"""
from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional, Tuple

from . import grid

RISK_WEIGHT = 0.6          # metres of detour an operator should accept per risk point
IMPASSABLE = 78.0          # a cell this hot / this gassy is not a route at any distance


def hazard_field(hazards: List[Dict[str, Any]]) -> Dict[str, float]:
    """Spread each hazard's severity over the grid with distance falloff.

    A fire in C4 makes C4 lethal, B4 and C3 dangerous, and A1 irrelevant. Overlapping
    hazards accumulate, because two half-problems in one cell is a whole problem.
    """
    field: Dict[str, float] = {z: 0.0 for z in grid.all_zones()}
    for h in hazards:
        hx, hy = grid.center_of(h.get("zone", "A1"))
        sev = float(h.get("severity", 50.0))
        reach = float(h.get("reach_m", 5.0))
        for z in field:
            zx, zy = grid.center_of(z)
            d = math.hypot(zx - hx, zy - hy)
            if d <= reach:
                field[z] += sev * (1.0 - d / reach) ** 1.5
    return {z: min(100.0, v) for z, v in field.items()}


def _search(start: str, goal: str, field: Dict[str, float], risk_weight: float) -> Optional[List[str]]:
    sc, sr = grid.index_of(start)
    gc, gr = grid.index_of(goal)
    if risk_weight > 0 and field.get(goal, 0.0) >= IMPASSABLE:
        risk_weight = risk_weight    # the goal may be hot; we still have to reach it
    open_heap: List[Tuple[float, Tuple[int, int]]] = [(0.0, (sc, sr))]
    came: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {(sc, sr): None}
    cost: Dict[Tuple[int, int], float] = {(sc, sr): 0.0}
    while open_heap:
        _, cur = heapq.heappop(open_heap)
        if cur == (gc, gr):
            break
        for nxt in grid.neighbors(*cur):
            zone = grid.name_of(*nxt)
            risk = field.get(zone, 0.0)
            if risk_weight > 0 and risk >= IMPASSABLE and nxt != (gc, gr):
                continue
            step = grid.CELL_M + risk_weight * risk
            new = cost[cur] + step
            if new < cost.get(nxt, float("inf")):
                cost[nxt] = new
                h = (abs(nxt[0] - gc) + abs(nxt[1] - gr)) * grid.CELL_M
                heapq.heappush(open_heap, (new + h, nxt))
                came[nxt] = cur
    if (gc, gr) not in came:
        return None
    path, node = [], (gc, gr)
    while node is not None:
        path.append(grid.name_of(*node))
        node = came[node]
    return list(reversed(path))


def _describe(path: List[str], field: Dict[str, float]) -> Dict[str, Any]:
    # The rover's own cell is excluded: the team is not standing where the rover is, and
    # a gas reading taken at the start point should not condemn every route out of it.
    risks = [field.get(z, 0.0) for z in path[1:]] or [field.get(path[0], 0.0)]
    peak = max(risks) if risks else 0.0
    return {
        "path": path,
        "distance_m": round((len(path) - 1) * grid.CELL_M, 1),
        "peak_risk": round(peak, 1),
        "mean_risk": round(sum(risks) / len(risks), 1) if risks else 0.0,
        "worst_zone": path[1:][risks.index(peak)] if len(path) > 1 else path[0],
        "band": "LOW" if peak < 25 else "MEDIUM" if peak < 50 else "HIGH" if peak < 75 else "CRITICAL",
    }


def plan(start: str, goal: str, hazards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the fastest route, the safest route, and which one to send."""
    field = hazard_field(hazards)
    fastest_path = _search(start, goal, field, risk_weight=0.0)
    safest_path = _search(start, goal, field, risk_weight=RISK_WEIGHT)

    if fastest_path is None:
        return {"reachable": False, "field": field, "reason": "No route to %s." % goal}

    fastest = _describe(fastest_path, field)
    fastest["name"] = "Route A"
    if safest_path is None:
        return {
            "reachable": True, "field": field, "fastest": fastest, "safest": None,
            "chosen": "A", "recommended": fastest,
            "reason": "Only Route A reaches %s. Every alternative is blocked by hazard." % goal,
        }

    safest = _describe(safest_path, field)
    safest["name"] = "Route B"

    same = safest["path"] == fastest["path"]
    if same:
        chosen, rec = "A", fastest
        reason = "Route A is both the shortest and the safest way to %s." % goal
    elif safest["peak_risk"] + 8 < fastest["peak_risk"]:
        chosen, rec = "B", safest
        detour = safest["distance_m"] - fastest["distance_m"]
        cost = "at the same distance" if detour < 0.5 else "%.0f m longer" % detour
        reason = ("Route B, %s, keeps peak risk at %.0f instead of %.0f in %s."
                  % (cost, safest["peak_risk"], fastest["peak_risk"], fastest["worst_zone"]))
    else:
        chosen, rec = "A", fastest
        reason = ("Route A. The safer alternative costs %.0f m and only removes %.0f risk points."
                  % (safest["distance_m"] - fastest["distance_m"],
                     fastest["peak_risk"] - safest["peak_risk"]))

    return {
        "reachable": True, "field": field, "fastest": fastest, "safest": safest,
        "chosen": chosen, "recommended": rec, "reason": reason, "identical": same,
    }
