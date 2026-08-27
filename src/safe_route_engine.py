from src.safe_path import SafePathPlanner


class SafeRouteEngine:

    def __init__(self, rows=20, cols=20):
        self.rows = rows
        self.cols = cols

    def create_grid(self, hazards=None):

        grid = [
            [0 for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

        if not hazards:
            return grid

        for hazard in hazards:

            row = hazard.get("row")
            col = hazard.get("col")
            score = hazard.get("score", 0)

            if (
                row is not None
                and col is not None
                and 0 <= row < self.rows
                and 0 <= col < self.cols
            ):
                grid[row][col] = score

        return grid

    def find_safe_route(
        self,
        start,
        goal,
        hazards=None
    ):

        grid = self.create_grid(hazards)

        planner = SafePathPlanner(grid)

        path = planner.find_path(
            start,
            goal
        )

        if path is None:

            return {
                "success": False,
                "message": "No safe route found"
            }

        return {
            "success": True,
            "path": path
        }

    def find_route_from_grid(
        self,
        start,
        goal,
        grid
    ):

        if not grid:
            return {
                "success": False,
                "message": "Hazard grid is empty"
            }

        planner = SafePathPlanner(grid)

        path = planner.find_path(
            start,
            goal
        )

        if path is None:

            return {
                "success": False,
                "message": "No safe route found"
            }

        return {
            "success": True,
            "path": path
        }