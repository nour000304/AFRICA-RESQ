class ZoneMapper:

    def __init__(self, cols=6, rows=6, frame_width=640, frame_height=480):
        self.cols = cols
        self.rows = rows
        self.frame_width = frame_width
        self.frame_height = frame_height

    def get_zone(self, x, y):

        cell_width = self.frame_width / self.cols
        cell_height = self.frame_height / self.rows

        col = int(x / cell_width)
        row = int(y / cell_height)

        col = min(col, self.cols - 1)
        row = min(row, self.rows - 1)

        column_letter = chr(ord("A") + col)

        return f"{column_letter}{row + 1}"