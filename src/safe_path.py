import heapq


class SafePathPlanner:

    def __init__(self, grid):
        self.grid = grid
        self.rows = len(grid)
        self.cols = len(grid[0])

    def heuristic(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def get_neighbors(self, node):

        row, col = node

        directions = [
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1)
        ]

        neighbors = []

        for dr, dc in directions:

            new_row = row + dr
            new_col = col + dc

            if (
                0 <= new_row < self.rows
                and 0 <= new_col < self.cols
            ):
                neighbors.append((new_row, new_col))

        return neighbors

    def find_path(self, start, goal):

        queue = []

        heapq.heappush(
            queue,
            (0, start)
        )

        came_from = {
            start: None
        }

        cost_so_far = {
            start: 0
        }

        while queue:

            _, current = heapq.heappop(queue)

            if current == goal:
                break

            for neighbor in self.get_neighbors(current):

                hazard_cost = self.grid[neighbor[0]][neighbor[1]]

                new_cost = (
                    cost_so_far[current]
                    + 1
                    + hazard_cost
                )

                if (
                    neighbor not in cost_so_far
                    or new_cost < cost_so_far[neighbor]
                ):

                    cost_so_far[neighbor] = new_cost

                    priority = (
                        new_cost
                        + self.heuristic(neighbor, goal)
                    )

                    heapq.heappush(
                        queue,
                        (priority, neighbor)
                    )

                    came_from[neighbor] = current

        if goal not in came_from:
            return None

        path = []

        current = goal

        while current is not None:

            path.append(current)

            current = came_from[current]

        path.reverse()

        return path