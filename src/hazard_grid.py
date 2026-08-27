from src.zone_mapper import ZoneMapper


class HazardGrid:

    def __init__(self, cols=20, rows=20):
        self.cols = cols
        self.rows = rows

        self.zone_mapper = ZoneMapper(
            cols=cols,
            rows=rows,
            frame_width=640,
            frame_height=480
        )

    def build(self, detections):

        grid = [
            [0 for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

        for detection in detections:

            location = detection.get("location")

            if not location:
                continue

            x, y = location

            cell_width = 640 / self.cols
            cell_height = 480 / self.rows

            col = int(x / cell_width)
            row = int(y / cell_height)

            col = min(
                max(col, 0),
                self.cols - 1
            )

            row = min(
                max(row, 0),
                self.rows - 1
            )

            confidence = detection.get(
                "confidence",
                0
            )

            score = round(
                confidence * 100
            )

            grid[row][col] = max(
                grid[row][col],
                score
            )

        return grid