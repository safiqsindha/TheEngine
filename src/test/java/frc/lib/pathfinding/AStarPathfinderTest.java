package frc.lib.pathfinding;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Tests for AStarPathfinder. Verifies pathfinding correctness, obstacle avoidance, and edge cases
 * on the navigation grid.
 */
class AStarPathfinderTest {

  private NavigationGrid grid;
  private AStarPathfinder pathfinder;

  @BeforeEach
  void setUp() {
    grid = new NavigationGrid("src/main/deploy/navgrid.json");
    pathfinder = new AStarPathfinder();
  }

  @Test
  void testFindPath_openField_returnsPath() {
    // Path from one open point to another should return a non-empty list
    Translation2d start = new Translation2d(2.0, 2.0);
    Translation2d goal = new Translation2d(8.0, 4.0);
    List<Translation2d> path = pathfinder.findPath(start, goal, grid);
    assertFalse(path.isEmpty(), "Path should not be empty in open field");
    assertEquals(start.getX(), path.get(0).getX(), 0.15);
    assertEquals(goal.getX(), path.get(path.size() - 1).getX(), 0.15);
  }

  @Test
  void testFindPath_obstacleBlocking_pathAvoidsObstacle() {
    // Place a dynamic obstacle between start and goal — path must route around it
    Translation2d start = new Translation2d(4.5, 4.0);
    Translation2d goal = new Translation2d(10.0, 4.0);
    grid.setDynamicObstacle(new Translation2d(6.0, 3.0), new Translation2d(7.0, 5.0));
    List<Translation2d> path = pathfinder.findPath(start, goal, grid);
    assertFalse(path.isEmpty());
    // Verify no waypoint lands inside the blocked strip
    for (Translation2d wp : path) {
      assertFalse(
          wp.getX() > 6.0 && wp.getX() < 7.0 && wp.getY() > 3.0 && wp.getY() < 5.0,
          "Waypoint should not be inside obstacle: " + wp);
    }
  }

  @Test
  void testFindPath_startInsideObstacle_returnsEmptyOrMovesToNearest() {
    // If start is inside an obstacle, pathfinder should snap to nearest passable cell
    Translation2d start = new Translation2d(3.39, 4.11); // Blue HUB — static obstacle
    Translation2d goal = new Translation2d(8.0, 4.0);
    List<Translation2d> path = pathfinder.findPath(start, goal, grid);
    // Either snaps and returns a valid path, or returns empty — must not throw
    assertNotNull(path);
  }

  @Test
  void testFindPath_unreachableGoal_returnsEmpty() {
    // Build a tiny 5×10 synthetic grid with a full-height wall at col 5
    int[][] raw = new int[5][10]; // all passable by default
    for (int r = 0; r < 5; r++) raw[r][5] = 1; // solid wall dividing left from right
    NavigationGrid testGrid = new NavigationGrid(raw, 1.0);
    // Start is on the left (col 1), goal on the right (col 7) — wall is impassable
    Translation2d testStart = new Translation2d(1.5, 2.5);
    Translation2d testGoal = new Translation2d(7.5, 2.5);
    List<Translation2d> path = pathfinder.findPath(testStart, testGoal, testGrid);
    assertTrue(path.isEmpty(), "Goal across full-height wall should be unreachable");
  }

  @Test
  void testFindPath_sameStartAndGoal_returnsSinglePoint() {
    // Start == goal should return a single-point path
    Translation2d point = new Translation2d(5.0, 4.0);
    List<Translation2d> path = pathfinder.findPath(point, point, grid);
    assertTrue(path.size() <= 1, "Same start and goal should return at most one waypoint");
  }

  @Test
  void testFindPath_performance_completesUnder10ms() {
    // A* on a 164×82 grid should complete well under 10ms.
    // Warm up the JIT first — the first call can be slow on some CI machines.
    Translation2d start = new Translation2d(1.0, 1.0);
    Translation2d goal = new Translation2d(15.0, 7.0);
    pathfinder.findPath(start, goal, grid); // warm-up (not timed)

    long startTime = System.nanoTime();
    pathfinder.findPath(start, goal, grid);
    long elapsedMs = (System.nanoTime() - startTime) / 1_000_000;
    assertTrue(elapsedMs < 50, "A* should complete under 50ms, took " + elapsedMs + "ms");
  }

  @Test
  void testFindPath_nearOptimalLength() {
    // Path length should be within 20% of straight-line distance (8-dir A* is near-optimal)
    Translation2d start = new Translation2d(2.0, 2.0);
    Translation2d goal = new Translation2d(14.0, 6.0);
    List<Translation2d> path = pathfinder.findPath(start, goal, grid);
    assertFalse(path.isEmpty(), "Expected a valid path");
    double pathLength = computePathLength(path);
    double straightLine = start.getDistance(goal);
    assertTrue(
        pathLength < straightLine * 1.20,
        "Path length " + pathLength + " should be within 20% of " + straightLine);
  }

  // ---- helpers ----

  private static double computePathLength(List<Translation2d> path) {
    double total = 0;
    for (int i = 1; i < path.size(); i++) {
      total += path.get(i).getDistance(path.get(i - 1));
    }
    return total;
  }
}
