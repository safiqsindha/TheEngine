# THE ENGINE — Student Training Module 4: Pathfinding & Navigation
# Block F.8 (Part 4 of 6) | Audience: Veterans + Rookies | Time: ~50 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Explain what A* is and why we use it
2. Read a grid, identify obstacles, and trace a path by hand
3. Understand how the NavigationGrid converts between field meters and grid cells
4. Explain how dynamic obstacles (opponent robots) are stamped onto the grid
5. Describe the full pathfinding stack: Grid → A* → Avoidance Layer → Drive

---

## Section 1: Why Pathfinding? (5 min)

### The Problem

The robot knows WHERE it wants to go (the strategy engine picked a target). But the field isn't empty — there are walls, game elements, and opponent robots between here and there.

**Driving in a straight line would crash into things.**

### The Solution Stack

The Engine uses three layers, each solving a different problem:

```
┌─────────────────────────────────┐
│  Layer 3: Dynamic Avoidance     │  Real-time dodge (every 20ms)
│  (DynamicAvoidanceLayer.java)   │  Handles moving opponents
├─────────────────────────────────┤
│  Layer 2: A* Pathfinder         │  Plan around obstacles (on demand)
│  (AStarPathfinder.java)         │  Handles walls + static objects
├─────────────────────────────────┤
│  Layer 1: Navigation Grid       │  The map of the field
│  (NavigationGrid.java)          │  0 = passable, 1 = blocked
└─────────────────────────────────┘
```

Layer 1 is the map. Layer 2 plans a route. Layer 3 adjusts the route in real-time when opponents move.

---

## Section 2: The Navigation Grid (15 min)

**File:** `src/main/java/frc/lib/pathfinding/NavigationGrid.java`

### What Is It?

The FRC field is 16.54m × 8.21m (roughly 54 feet × 27 feet). We divide it into a grid of tiny squares:

```
Grid specs:
  164 columns × 82 rows
  Each cell = 0.10m × 0.10m (about 4 inches)
  Total cells = 13,448
```

Each cell is either **passable (0)** or **blocked (1)**:

```
0 0 0 0 1 1 0 0 0 0
0 0 0 0 1 1 0 0 0 0    1 = wall/obstacle
0 0 0 0 0 0 0 0 0 0    0 = open floor
0 0 0 0 0 0 0 0 0 0
```

### Loading the Grid

The grid is stored in `navgrid.json` (deployed to the roboRIO):

```json
{
    "grid": [[0, 0, 1, 0, ...], ...],
    "cell_size_m": 0.1,
    "columns": 164,
    "rows": 82
}
```

The NavigationGrid class loads this at startup:

```java
NavigationGrid grid = new NavigationGrid("src/main/deploy/navgrid.json");
```

### Coordinate Conversion

The grid works in cell coordinates (column, row). The robot works in field coordinates (x meters, y meters). Two methods convert between them:

**Field → Grid:**
```java
// Where is (3.5, 2.0) meters on the grid?
int[] cell = grid.toGridCoords(new Translation2d(3.5, 2.0));
// cell = [35, 20]  (3.5 / 0.1 = 35, 2.0 / 0.1 = 20)
```

**Grid → Field:**
```java
// Where is cell (35, 20) on the field?
Translation2d pos = grid.toFieldCoords(35, 20);
// pos = (3.55, 2.05)  — center of the cell
```

> **Rookie Checkpoint:** Why the center? Because cell (35, 20) covers the area from (3.5, 2.0) to (3.6, 2.1). The center is (3.55, 2.05). This gives the most accurate position within the cell.

### Passability Check

```java
boolean canGo = grid.isPassable(35, 20);
// Returns true if:
//   - Cell is within bounds (col 0-163, row 0-81)
//   - Static grid value is 0 (not a wall)
//   - No dynamic obstacle stamped on this cell
```

### Dynamic Obstacles: Opponents on the Grid

Here's the key innovation. The static grid only has walls and field elements. But opponents MOVE. Every robot loop cycle:

1. **Clear** all dynamic obstacles from last cycle
2. **Stamp** new bounding boxes from current opponent positions
3. **Plan** path using the updated grid

```java
// Each cycle:
grid.clearDynamicObstacles();

for (Translation2d opponent : detectedOpponents) {
    // Stamp a 0.8m × 0.8m box around each opponent (robot-sized)
    Translation2d min = opponent.minus(new Translation2d(0.4, 0.4));
    Translation2d max = opponent.plus(new Translation2d(0.4, 0.4));
    grid.setDynamicObstacle(min, max);
}
```

After stamping, any cell under an opponent's bounding box returns `isPassable() = false`:

```
Before:                     After stamping opponent at (5.0, 4.0):
0 0 0 0 0 0 0 0            0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0            0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0            0 0 0 X X X X 0    X = dynamic obstacle
0 0 0 0 0 0 0 0            0 0 0 X X X X 0
0 0 0 0 0 0 0 0            0 0 0 X X X X 0
0 0 0 0 0 0 0 0            0 0 0 0 0 0 0 0
```

> **Quick Check:** An opponent is at (8.0, 3.0). What grid cell is that?
>
> **Answer:** Column = 8.0 / 0.1 = **80**, Row = 3.0 / 0.1 = **30**. Cell (80, 30).

---

## Section 3: The A* Algorithm (20 min)

**File:** `src/main/java/frc/lib/pathfinding/AStarPathfinder.java`

### What A* Does

A* (pronounced "A-star") finds the **shortest path** from a start point to a goal point through a grid with obstacles. It's been used since 1968 and is THE standard pathfinding algorithm in robotics and video games.

### The Core Idea

A* explores cells in order of a score called **f-cost**:

```
f = g + h

g = actual cost to reach this cell from the start
h = estimated cost to reach the goal from this cell (the "heuristic")
```

Cells with low f-cost are explored first. This means A* naturally explores toward the goal, not randomly.

### Our Implementation Details

**8-directional movement:**
```
NW  N  NE        Cost for cardinal (N, S, E, W) = 1.0
 ╲  │  ╱         Cost for diagonal (NE, NW, SE, SW) = √2 ≈ 1.41
W ──●── E
 ╱  │  ╲         Why √2? Pythagorean theorem:
SW  S  SE        diagonal of a 1×1 square = √(1² + 1²) = √2
```

**Heuristic: Euclidean distance**
```java
float heuristic(int c1, int r1, int c2, int r2) {
    double dx = c1 - c2;
    double dy = r1 - r2;
    return (float) Math.sqrt(dx * dx + dy * dy);
}
```

This is the straight-line distance to the goal. It's **admissible** — it never overestimates the true cost — which guarantees A* finds the optimal path.

### Step-by-Step Walkthrough

Let's trace A* on a tiny 6×6 grid:

```
Grid (S = start, G = goal, # = obstacle):

S . . . . .     S = (0, 0)
. . # # . .     G = (5, 5)
. . # # . .     # = blocked cells
. . . . . .
. . . . . .
. . . . . G
```

**Step 1:** Start at S (0,0). g=0, h=7.07 (distance to G), f=7.07.

**Step 2:** Explore neighbors of S. The cell (1,1) going SE has g=1.41, h=5.66, f=7.07. The cell (1,0) going E has g=1.0, h=6.40, f=7.40. Pick lowest f first.

**Step 3-N:** Keep expanding the lowest-f cell. When we hit an obstacle, skip it. A* naturally routes AROUND the wall:

```
S → → . . .
↓ ↘ # # . .
. . # # . .
. . ↘ . . .
. . . ↘ . .
. . . . ↘ G

Path found! Cost ≈ 8.49 (mix of cardinal and diagonal moves)
```

### Special Cases in Our Code

**Start or goal on an obstacle?** A* snaps to the nearest passable cell using BFS (breadth-first search):

```java
if (!grid.isPassable(startCell[0], startCell[1])) {
    startCell = nearestPassable(startCell[0], startCell[1], grid);
    if (startCell == null) return Collections.emptyList();
}
```

**No path exists?** Returns an empty list. The caller falls back to a different target.

**Start equals goal?** Returns a single-element list (just the position itself).

### Path Reconstruction

A* tracks a `parent[]` array — for each cell, which cell did we come FROM? Once the goal is reached, we trace backwards:

```
Goal → parent → parent → parent → ... → Start
```

Then reverse the list to get Start → Goal order.

---

## Section 4: Putting It Together (5 min)

### The Full Call Chain

```java
// 1. Strategy picks a target
ScoredTarget best = strategy.evaluateTargets(state).get(0);

// 2. Update dynamic obstacles on the grid
grid.clearDynamicObstacles();
for (Translation2d opp : opponents) {
    grid.setDynamicObstacle(opp.minus(halfSize), opp.plus(halfSize));
}

// 3. A* finds a path around obstacles
List<Translation2d> waypoints = pathfinder.findPath(
    state.getRobotPose().getTranslation(),
    best.targetPose().getTranslation(),
    grid
);

// 4. PathPlannerLib follows the waypoints (smooth spline through them)
// 5. DynamicAvoidanceLayer adjusts velocity in real-time (Module 2, Section 5)
```

### When Does Re-Planning Happen?

- **Every 0.5 seconds** during execution (the re-evaluation cycle)
- **Immediately** when the Bot Aborter triggers (target changed)
- **On arrival** at the current target (pick next target, plan new path)

If the robot drifts more than 0.30m (`kReplanThresholdMeters`) from the planned path, a re-plan is triggered even outside the 0.5s cycle.

---

## Section 5: Hands-On Exercises

### Exercise A: Grid Paper Pathfinding (All Levels, 10 min)

Draw this grid on graph paper (or whiteboard). Each cell is 1 unit × 1 unit.

```
10×10 grid. S = start at (0,0). G = goal at (9,9).

. . . . # . . . . .
. . . . # . . . . .
. . . . # . . . . .
. . . . # . . . . .
. . . . . . . . . .     ← row 5 is clear (the gap!)
. . . . # . . . . .
. . . . # . . . . .
. . . . # . . . . .
. . . . # . . . . .
. . . . . . . . . G
```

**Tasks:**
1. Find the shortest 8-directional path from S to G
2. Count the cost (cardinal = 1.0, diagonal = 1.41)
3. How would the path change if row 5 was also blocked?
4. How would the path change if an opponent was stamped at (5, 5)?

---

### Exercise B: Coordinate Conversion Drill (All Levels, 5 min)

Given `cell_size_m = 0.1`, `columns = 164`, `rows = 82`:

| # | Input | Operation | Answer |
|---|-------|-----------|--------|
| 1 | Field (8.23, 4.11) | → Grid coords | ? |
| 2 | Grid (0, 0) | → Field coords (center) | ? |
| 3 | Grid (163, 81) | → Field coords (center) | ? |
| 4 | Field (0.0, 0.0) | → Grid coords | ? |
| 5 | Field (20.0, 10.0) | → Grid coords | ? |

**Answers:**
1. col = 82, row = 41 → **(82, 41)**
2. (0.05, 0.05) — center of first cell
3. (16.35, 8.15) — center of last cell
4. (0, 0) — origin maps to first cell
5. col = 163, row = 81 → **clamped to (163, 81)** — toGridCoords clamps to valid range!

---

### Exercise C: Dynamic Obstacle Stamping (All Levels, 5 min)

An opponent robot is at field position (5.0, 3.0). We stamp a 0.8m × 0.8m bounding box.

1. What are the min and max field coordinates of the bounding box?
2. What grid cells does the box cover? (min col, max col, min row, max row)
3. How many cells are blocked?

**Answers:**
1. min = (4.6, 2.6), max = (5.4, 3.4)
2. col: 46 to 54, row: 26 to 34 → 9 columns × 9 rows
3. **81 cells** blocked

---

### Exercise D: Read the Code (Veterans, 10 min)

Open `AStarPathfinder.java` and answer:

1. The `STEP_COST` array has 8 values. Which ones are 1.0 and which are √2? Map them to directions.
2. What's the `PriorityQueue` sorted by? What does this guarantee about the order cells are explored?
3. In `nearestPassable()`, what algorithm is used? Why not A* itself?
4. What happens to the path after `reconstructPath()`? (Hint: look at the last line of that method)

**Answers:**
1. Looking at DC/DR arrays: indices 1,3,4,6 have cost 1.0 (N, W, E, S = cardinal); indices 0,2,5,7 have cost √2 (NW, NE, SW, SE = diagonal)
2. Sorted by `a[0]` which is f-cost. This guarantees lowest-f cells are explored first (greedy toward the goal)
3. BFS (breadth-first search) — because we just need the NEAREST passable cell, not the shortest path to it. BFS finds nearest by distance in grid hops.
4. `Collections.reverse(path)` — the path is reconstructed from goal→start, then reversed to start→goal

---

### Exercise E: What If? (Discussion, All Levels)

1. **What if we used a 1m cell size instead of 0.1m?** How many cells? What problems would this cause?
   - 16 × 8 = 128 cells. Much faster, but a 1m cell is bigger than the robot — paths would clip obstacles because the grid can't represent gaps smaller than 1 meter.

2. **What if we used 4-directional movement instead of 8?** What would change?
   - Paths would be forced into staircase shapes (no diagonals). They'd be ~41% longer on average, wasting time.

3. **What if we didn't clear dynamic obstacles each cycle?** What would happen?
   - Opponent ghosts. Old positions would stay blocked forever. Eventually the entire field would be "blocked" and A* would find no path.

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **A*** | Pathfinding algorithm that finds the shortest path using g-cost + heuristic |
| **g-cost** | Actual accumulated cost from start to current cell |
| **h (heuristic)** | Estimated cost from current cell to goal (we use Euclidean distance) |
| **f-cost** | g + h. The total estimated cost. A* always explores lowest-f first. |
| **Admissible** | A heuristic that never overestimates. Euclidean is admissible for 8-dir grids. |
| **Navigation Grid** | 2D array representing the field. 0 = passable, 1 = obstacle. |
| **Dynamic Obstacle** | Temporary blocked cells (opponent positions), cleared and re-stamped each cycle |
| **BFS** | Breadth-first search. Explores all cells at distance 1, then distance 2, etc. Used to find nearest passable cell. |
| **Priority Queue** | Data structure that always gives you the smallest element first. Perfect for A*. |

---

## What's Next

**Module 5** covers the **Vision & YOLO Pipeline** — how a camera image becomes a list of field-relative fuel positions that feed into everything you've learned so far.

---

*Module 4 of 6 | THE ENGINE Student Training | Team 2950 The Devastators*
