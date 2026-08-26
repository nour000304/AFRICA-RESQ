from safe_path import SafePathPlanner


# 0 = safe
# 5 = medium hazard
# 100 = very dangerous

grid = [
    [0,   0,   0,   0,   0],
    [0, 100, 100, 100,   0],
    [0,   5,   5,   5,   0],
    [0,   0,   0,   0,   0],
    [0,   0,   0,   0,   0]
]

planner = SafePathPlanner(grid)

start = (0, 0)
goal = (0, 4)

path = planner.find_path(start, goal)

print("Safest path:")
print(path)