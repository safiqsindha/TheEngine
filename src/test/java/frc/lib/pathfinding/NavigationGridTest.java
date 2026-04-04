package frc.lib.pathfinding;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Tests for NavigationGrid. Verifies grid loading, cell queries, and coordinate conversion. Uses
 * the pre-built navgrid.json at src/main/deploy/navgrid.json.
 */
class NavigationGridTest {

  private NavigationGrid grid;

  @BeforeEach
  void setUp() {
    grid = new NavigationGrid("src/main/deploy/navgrid.json");
  }

  @Test
  void testGridDimensions_matchExpected() {
    // navgrid.json is 164 columns × 82 rows at 0.10m resolution
    assertEquals(164, grid.getColumns());
    assertEquals(82, grid.getRows());
  }

  @Test
  void testFieldCenter_isPassable() {
    // Center of field (8.23m, 4.11m) should be open space
    assertTrue(grid.isPassable(grid.toGridCoords(new Translation2d(8.23, 4.11))));
  }

  @Test
  void testHubLocation_isObstacle() {
    // Blue HUB at approximately (3.39m, 4.11m) should be blocked
    int[] cell = grid.toGridCoords(new Translation2d(3.39, 4.11));
    assertFalse(grid.isPassable(cell[0], cell[1]));
  }

  @Test
  void testFieldBorder_isObstacle() {
    // Cell at (0,0) should be blocked (guardrail)
    assertFalse(grid.isPassable(0, 0));
  }

  @Test
  void testCoordinateConversion_roundTrip() {
    // Convert field→grid→field should be within one cell size of original
    Translation2d original = new Translation2d(5.0, 3.0);
    int[] gridCoords = grid.toGridCoords(original);
    Translation2d backToField = grid.toFieldCoords(gridCoords[0], gridCoords[1]);
    assertEquals(original.getX(), backToField.getX(), 0.10); // within 1 cell
    assertEquals(original.getY(), backToField.getY(), 0.10);
  }

  @Test
  void testOutOfBounds_handledGracefully() {
    // Querying outside the field should not throw, should return obstacle
    assertFalse(grid.isPassable(-1, -1));
    assertFalse(grid.isPassable(999, 999));
  }

  @Test
  void testSetDynamicObstacle_blocksRegion() {
    // Mark a rectangular zone as blocked, verify it's impassable
    Translation2d min = new Translation2d(5.0, 3.0);
    Translation2d max = new Translation2d(6.0, 4.0);
    grid.setDynamicObstacle(min, max);
    assertFalse(grid.isPassable(grid.toGridCoords(new Translation2d(5.5, 3.5))));
  }

  @Test
  void testClearDynamicObstacles_restoresOriginal() {
    // After clearing dynamic obstacles, previously blocked cells should be passable again
    Translation2d pos = new Translation2d(5.5, 3.5);
    assertTrue(grid.isPassable(grid.toGridCoords(pos))); // originally passable
    grid.setDynamicObstacle(new Translation2d(5.0, 3.0), new Translation2d(6.0, 4.0));
    assertFalse(grid.isPassable(grid.toGridCoords(pos))); // now blocked
    grid.clearDynamicObstacles();
    assertTrue(grid.isPassable(grid.toGridCoords(pos))); // restored
  }
}
