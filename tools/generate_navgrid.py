#!/usr/bin/env python3
"""
Generate navigation grid (navgrid.json) for the 2026 FRC REBUILT field.

Field dimensions: 54ft x 27ft = 16.46m x 8.23m
Resolution: 10cm per cell = 165 columns x 82 rows
Origin: (0,0) is the bottom-left corner (blue alliance driver station wall)

Obstacle sources (from 2026 Game Manual):
- HUBs: ~48in (1.22m) diameter cylinders, one per alliance
- TOWERs: 49.25in x 45.0in (1.25m x 1.14m), one per alliance
- BUMPs: 73.0in x 44.4in (1.85m x 1.13m), 6.5in tall, 4 total
- TRENCHes: 65.65in x 47.0in (1.67m x 1.19m), 4 total (columns/supports are obstacles)
- DEPOTs: wall-mounted, 2 total
- OUTPOST walls: along alliance walls
- Guardrails: field perimeter

Note: BUMPs are drive-over obstacles (6.5in tall). TRENCHes are drive-under obstacles
(22.25in clearance). Whether these are passable depends on your robot's height.
This grid marks TRENCH supports as obstacles (conservative) and BUMPs as passable
(most swerve robots can drive over 6.5in bumps). Adjust traversability flags based
on your robot's dimensions.
"""

import json
import math

# Field dimensions in meters
FIELD_LENGTH = 16.46  # 54 ft
FIELD_WIDTH = 8.23    # 27 ft
CELL_SIZE = 0.10      # 10cm per cell

COLS = int(FIELD_LENGTH / CELL_SIZE)  # 165
ROWS = int(FIELD_WIDTH / CELL_SIZE)   # 82

# Robot inflation radius (half robot width + bumper, ~18 inches = 0.46m)
# We inflate obstacles by this amount so the center of the robot can't enter
INFLATE = 0.46

def meters_to_cell(x, y):
    """Convert field coordinates (meters) to grid cell (col, row)."""
    col = int(x / CELL_SIZE)
    row = int(y / CELL_SIZE)
    return (max(0, min(col, COLS-1)), max(0, min(row, ROWS-1)))

def mark_rect(grid, x_min, y_min, x_max, y_max, value=1):
    """Mark a rectangular region as occupied (value=1) or passable (value=0)."""
    c1, r1 = meters_to_cell(x_min - INFLATE, y_min - INFLATE)
    c2, r2 = meters_to_cell(x_max + INFLATE, y_max + INFLATE)
    for r in range(max(0, r1), min(ROWS, r2+1)):
        for c in range(max(0, c1), min(COLS, c2+1)):
            grid[r][c] = value

def mark_circle(grid, cx, cy, radius, value=1):
    """Mark a circular region as occupied."""
    inflated_r = radius + INFLATE
    c1, r1 = meters_to_cell(cx - inflated_r, cy - inflated_r)
    c2, r2 = meters_to_cell(cx + inflated_r, cy + inflated_r)
    for r in range(max(0, r1), min(ROWS, r2+1)):
        for c in range(max(0, c1), min(COLS, c2+1)):
            cell_x = c * CELL_SIZE + CELL_SIZE/2
            cell_y = r * CELL_SIZE + CELL_SIZE/2
            if math.sqrt((cell_x - cx)**2 + (cell_y - cy)**2) <= inflated_r:
                grid[r][c] = value

# Initialize grid: 0 = passable, 1 = obstacle
grid = [[0 for _ in range(COLS)] for _ in range(ROWS)]

# ─── FIELD PERIMETER (guardrails) ───
# Mark 1-cell border as impassable
for c in range(COLS):
    for r_border in range(int(INFLATE / CELL_SIZE) + 1):
        grid[r_border][c] = 1
        grid[ROWS - 1 - r_border][c] = 1
for r in range(ROWS):
    for c_border in range(int(INFLATE / CELL_SIZE) + 1):
        grid[r][c_border] = 1
        grid[r][COLS - 1 - c_border] = 1

# ─── HUBs (cylindrical, ~1.22m diameter) ───
# Blue HUB: centered approximately at (3.39m, 4.11m) - left side
# Red HUB: centered approximately at (13.07m, 4.11m) - right side
HUB_RADIUS = 0.61  # ~24 inches radius
mark_circle(grid, 3.39, 4.11, HUB_RADIUS)
mark_circle(grid, 13.07, 4.11, HUB_RADIUS)

# ─── TOWERs (1.25m x 1.14m rectangular) ───
# Blue TOWER: approximately at (1.22m, 4.11m center)
# Red TOWER: approximately at (15.24m, 4.11m center)
TOWER_W = 1.25
TOWER_D = 1.14
mark_rect(grid,
    1.22 - TOWER_W/2, 4.11 - TOWER_D/2,
    1.22 + TOWER_W/2, 4.11 + TOWER_D/2)
mark_rect(grid,
    15.24 - TOWER_W/2, 4.11 - TOWER_D/2,
    15.24 + TOWER_W/2, 4.11 + TOWER_D/2)

# ─── BUMPs (1.85m x 1.13m, 4 total) ───
# BUMPs are drive-over (6.5in = 16.5cm tall). Most swerve bots can handle this.
# Mark as traversable by default. Set BUMP_PASSABLE = False if your robot can't.
BUMP_PASSABLE = True
BUMP_W = 1.85
BUMP_D = 1.13
# Approximate positions: 2 per alliance side, flanking the HUB
bump_positions = [
    (3.39, 2.05),   # Blue left bump
    (3.39, 6.17),   # Blue right bump
    (13.07, 2.05),  # Red left bump
    (13.07, 6.17),  # Red right bump
]
if not BUMP_PASSABLE:
    for bx, by in bump_positions:
        mark_rect(grid, bx - BUMP_W/2, by - BUMP_D/2, bx + BUMP_W/2, by + BUMP_D/2)

# ─── TRENCHes (support columns are obstacles) ───
# TRENCH opening: 50.34in (1.28m) wide, 22.25in (56.5cm) tall clearance
# TRENCH supports/columns: ~7.5in (0.19m) wide on each side
# 4 TRENCHes total, 2 per guardrail side
# Approximate positions along guardrails
TRENCH_SUPPORT_W = 0.19
TRENCH_TOTAL_W = 1.67
TRENCH_D = 1.19
# Near-side guardrail (y ≈ 0.60m from wall)
trench_positions = [
    (5.50, 0.60),   # Blue near trench
    (10.96, 0.60),  # Red near trench
    (5.50, 7.63),   # Blue far trench
    (10.96, 7.63),  # Red far trench
]
for tx, ty in trench_positions:
    # Mark the support columns on each side (not the open space under the arm)
    # Left support
    mark_rect(grid,
        tx - TRENCH_TOTAL_W/2, ty - TRENCH_D/2,
        tx - TRENCH_TOTAL_W/2 + TRENCH_SUPPORT_W, ty + TRENCH_D/2)
    # Right support
    mark_rect(grid,
        tx + TRENCH_TOTAL_W/2 - TRENCH_SUPPORT_W, ty - TRENCH_D/2,
        tx + TRENCH_TOTAL_W/2, ty + TRENCH_D/2)

# ─── DEPOTs (wall-mounted, 2 total) ───
# Depots are recessed into the guardrails. Mark the protruding walls.
DEPOT_W = 1.50
DEPOT_D = 0.60
depot_positions = [
    (8.23, 0.30),   # Center-left depot (near wall)
    (8.23, 7.93),   # Center-right depot (far wall)
]
for dx, dy in depot_positions:
    mark_rect(grid, dx - DEPOT_W/2, dy - DEPOT_D/2, dx + DEPOT_W/2, dy + DEPOT_D/2)

# ─── OUTPOSTs (alliance wall structures) ───
# Outpost walls protrude from alliance walls
OUTPOST_W = 2.00
OUTPOST_D = 0.80
mark_rect(grid, 0.0, 4.11 - OUTPOST_W/2, OUTPOST_D, 4.11 + OUTPOST_W/2)  # Blue
mark_rect(grid, FIELD_LENGTH - OUTPOST_D, 4.11 - OUTPOST_W/2, FIELD_LENGTH, 4.11 + OUTPOST_W/2)  # Red

# ─── Count stats ───
total_cells = ROWS * COLS
obstacle_cells = sum(sum(row) for row in grid)
passable_cells = total_cells - obstacle_cells

# ─── Build output ───
output = {
    "field_length_m": FIELD_LENGTH,
    "field_width_m": FIELD_WIDTH,
    "cell_size_m": CELL_SIZE,
    "columns": COLS,
    "rows": ROWS,
    "robot_inflation_m": INFLATE,
    "bump_passable": BUMP_PASSABLE,
    "stats": {
        "total_cells": total_cells,
        "obstacle_cells": obstacle_cells,
        "passable_cells": passable_cells,
        "obstacle_percent": round(obstacle_cells / total_cells * 100, 1)
    },
    "obstacles_legend": {
        "0": "passable",
        "1": "obstacle (impassable)"
    },
    "grid": grid
}

# Write to file
output_path = "navgrid.json"
with open(output_path, "w") as f:
    json.dump(output, f, separators=(",", ":"))

print(f"Navigation grid generated: {COLS}x{ROWS} = {total_cells} cells")
print(f"Obstacles: {obstacle_cells} ({output['stats']['obstacle_percent']}%)")
print(f"Passable: {passable_cells}")
print(f"Written to {output_path}")
