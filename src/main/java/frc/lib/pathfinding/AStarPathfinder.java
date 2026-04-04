package frc.lib.pathfinding;

import edu.wpi.first.math.geometry.Translation2d;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

/**
 * Pure-Java A* pathfinder over a {@link NavigationGrid}.
 *
 * <p>Used by AutonomousStrategy for cost estimation (travel distance / reachability).
 * PathPlannerLib handles actual robot path following; this class is for decision-engine scoring
 * only.
 *
 * <p>Supports 8-directional movement (cardinal + diagonal). Diagonal cost = √2.
 */
public final class AStarPathfinder {

  private static final float SQRT2 = (float) Math.sqrt(2.0);

  // 8-directional neighbourhood: (dc, dr, cost)
  private static final int[] DC = {-1, 0, 1, -1, 1, -1, 0, 1};
  private static final int[] DR = {-1, -1, -1, 0, 0, 1, 1, 1};
  private static final float[] STEP_COST = {SQRT2, 1.0f, SQRT2, 1.0f, 1.0f, SQRT2, 1.0f, SQRT2};

  /**
   * Find a path from {@code start} to {@code goal} using A* on the given grid.
   *
   * <p>If start or goal falls on an obstacle, the nearest passable cell is used instead. Returns an
   * empty list if no path exists.
   *
   * @param start field-space start position (meters)
   * @param goal field-space goal position (meters)
   * @param grid the navigation grid (may contain dynamic obstacles)
   * @return ordered list of field-space waypoints from start to goal, or empty if unreachable
   */
  public List<Translation2d> findPath(
      Translation2d start, Translation2d goal, NavigationGrid grid) {
    int cols = grid.getColumns();
    int rows = grid.getRows();

    int[] startCell = grid.toGridCoords(start);
    int[] goalCell = grid.toGridCoords(goal);

    // Snap start/goal to nearest passable cell if needed
    if (!grid.isPassable(startCell[0], startCell[1])) {
      startCell = nearestPassable(startCell[0], startCell[1], grid);
      if (startCell == null) return Collections.emptyList();
    }
    if (!grid.isPassable(goalCell[0], goalCell[1])) {
      goalCell = nearestPassable(goalCell[0], goalCell[1], grid);
      if (goalCell == null) return Collections.emptyList();
    }

    int startId = startCell[1] * cols + startCell[0];
    int goalId = goalCell[1] * cols + goalCell[0];

    // Start == goal
    if (startId == goalId) {
      List<Translation2d> single = new ArrayList<>(1);
      single.add(grid.toFieldCoords(startCell[0], startCell[1]));
      return single;
    }

    float[] gCost = new float[rows * cols];
    Arrays.fill(gCost, Float.MAX_VALUE);
    gCost[startId] = 0.0f;

    int[] parent = new int[rows * cols];
    Arrays.fill(parent, -1);

    boolean[] closed = new boolean[rows * cols];

    // Priority queue: float[0] = fCost, float[1] = nodeId (fits in float: max 13448)
    PriorityQueue<float[]> open = new PriorityQueue<>(Comparator.comparingDouble(a -> a[0]));
    open.offer(
        new float[] {heuristic(startCell[0], startCell[1], goalCell[0], goalCell[1]), startId});

    while (!open.isEmpty()) {
      float[] curr = open.poll();
      int currId = (int) curr[1];

      if (closed[currId]) continue;
      closed[currId] = true;

      if (currId == goalId) {
        return reconstructPath(parent, goalId, cols, grid);
      }

      int currCol = currId % cols;
      int currRow = currId / cols;

      for (int i = 0; i < 8; i++) {
        int nc = currCol + DC[i];
        int nr = currRow + DR[i];
        if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
        if (!grid.isPassable(nc, nr)) continue;

        int nId = nr * cols + nc;
        if (closed[nId]) continue;

        float ng = gCost[currId] + STEP_COST[i];
        if (ng < gCost[nId]) {
          gCost[nId] = ng;
          parent[nId] = currId;
          float f = ng + heuristic(nc, nr, goalCell[0], goalCell[1]);
          open.offer(new float[] {f, nId});
        }
      }
    }

    return Collections.emptyList(); // unreachable
  }

  // ---- private helpers ----

  /** Euclidean heuristic in grid cells (admissible for 8-directional movement). */
  private static float heuristic(int c1, int r1, int c2, int r2) {
    double dx = c1 - c2;
    double dy = r1 - r2;
    return (float) Math.sqrt(dx * dx + dy * dy);
  }

  /**
   * BFS from (col, row) to find the nearest passable cell. Returns null if none found within the
   * grid bounds.
   */
  private static int[] nearestPassable(int col, int row, NavigationGrid grid) {
    int cols = grid.getColumns();
    int rows = grid.getRows();
    boolean[] visited = new boolean[rows * cols];
    int[] queueCol = new int[rows * cols];
    int[] queueRow = new int[rows * cols];
    int head = 0, tail = 0;
    queueCol[tail] = col;
    queueRow[tail] = row;
    tail++;
    visited[row * cols + col] = true;

    while (head < tail) {
      int c = queueCol[head];
      int r = queueRow[head];
      head++;
      if (grid.isPassable(c, r)) return new int[] {c, r};
      for (int i = 0; i < 8; i++) {
        int nc = c + DC[i];
        int nr = r + DR[i];
        if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
        int nId = nr * cols + nc;
        if (!visited[nId]) {
          visited[nId] = true;
          queueCol[tail] = nc;
          queueRow[tail] = nr;
          tail++;
        }
      }
    }
    return null;
  }

  /** Reconstruct path from parent array, returning field-space waypoints. */
  private static List<Translation2d> reconstructPath(
      int[] parent, int goalId, int cols, NavigationGrid grid) {
    List<Translation2d> path = new ArrayList<>();
    int curr = goalId;
    while (curr != -1) {
      int c = curr % cols;
      int r = curr / cols;
      path.add(grid.toFieldCoords(c, r));
      curr = parent[curr];
    }
    Collections.reverse(path);
    return path;
  }
}
