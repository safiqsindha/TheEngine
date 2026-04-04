package frc.lib.pathfinding;

import edu.wpi.first.math.geometry.Translation2d;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Set;

/**
 * Wraps the pre-built navgrid.json occupancy grid, providing cell queries, coordinate conversion,
 * and dynamic obstacle management.
 *
 * <p>navgrid.json format: {"grid": [[0,1,...], ...], "cell_size_m": 0.1, "columns": N, "rows": M}
 * grid[row][col] — 0 = passable, 1 = obstacle.
 */
public final class NavigationGrid {

  private final int[][] staticGrid; // staticGrid[row][col]
  private final int columns;
  private final int rows;
  private final double cellSize;

  /** Dynamic obstacles added at runtime (e.g. opponent robots). Cleared each cycle. */
  private final Set<Long> dynamicObstacles = new HashSet<>();

  /**
   * Package-private constructor for unit tests — accepts a pre-built grid array.
   *
   * @param grid staticGrid[row][col], 0=passable 1=obstacle
   * @param cellSize cell size in meters
   */
  NavigationGrid(int[][] grid, double cellSize) {
    this.rows = grid.length;
    this.columns = rows > 0 ? grid[0].length : 0;
    this.cellSize = cellSize;
    this.staticGrid = grid;
  }

  /**
   * Load a navgrid.json from the given file path.
   *
   * @param jsonPath absolute or relative path to the navgrid.json file
   * @throws RuntimeException if the file cannot be read or parsed
   */
  public NavigationGrid(String jsonPath) {
    try {
      String raw = new String(Files.readAllBytes(Paths.get(jsonPath)), StandardCharsets.UTF_8);
      this.columns = parseInt(raw, "\"columns\"");
      this.rows = parseInt(raw, "\"rows\"");
      this.cellSize = parseDouble(raw, "\"cell_size_m\"");
      this.staticGrid = parseGrid(raw, this.rows, this.columns);
    } catch (IOException e) {
      throw new RuntimeException("NavigationGrid: cannot read " + jsonPath, e);
    }
  }

  // ---- public API ----

  /** Number of grid columns (X axis). */
  public int getColumns() {
    return columns;
  }

  /** Number of grid rows (Y axis). */
  public int getRows() {
    return rows;
  }

  /**
   * Returns true if the cell is within bounds, not a static obstacle, and not a dynamic obstacle.
   */
  public boolean isPassable(int col, int row) {
    if (col < 0 || col >= columns || row < 0 || row >= rows) {
      return false; // treat out-of-bounds as obstacle
    }
    if (staticGrid[row][col] != 0) {
      return false;
    }
    return !dynamicObstacles.contains(packCoord(col, row));
  }

  /** Convenience overload accepting the array returned by {@link #toGridCoords}. */
  public boolean isPassable(int[] colRow) {
    return isPassable(colRow[0], colRow[1]);
  }

  /**
   * Convert a field position (meters) to [col, row] grid coordinates. Clamps to valid range.
   *
   * @param fieldPos field position in meters
   * @return [col, row]
   */
  public int[] toGridCoords(Translation2d fieldPos) {
    int col = (int) (fieldPos.getX() / cellSize);
    int row = (int) (fieldPos.getY() / cellSize);
    col = Math.max(0, Math.min(columns - 1, col));
    row = Math.max(0, Math.min(rows - 1, row));
    return new int[] {col, row};
  }

  /**
   * Convert [col, row] grid coordinates to the center of that cell in field space (meters).
   *
   * @return field position at cell center
   */
  public Translation2d toFieldCoords(int col, int row) {
    double x = col * cellSize + cellSize / 2.0;
    double y = row * cellSize + cellSize / 2.0;
    return new Translation2d(x, y);
  }

  /**
   * Mark all cells overlapping the axis-aligned bounding box [min, max] as dynamic obstacles.
   * Dynamic obstacles are layered on top of the static grid.
   *
   * @param min lower-left corner in field space (meters)
   * @param max upper-right corner in field space (meters)
   */
  public void setDynamicObstacle(Translation2d min, Translation2d max) {
    int colMin = Math.max(0, (int) (min.getX() / cellSize));
    int colMax = Math.min(columns - 1, (int) (max.getX() / cellSize));
    int rowMin = Math.max(0, (int) (min.getY() / cellSize));
    int rowMax = Math.min(rows - 1, (int) (max.getY() / cellSize));
    for (int c = colMin; c <= colMax; c++) {
      for (int r = rowMin; r <= rowMax; r++) {
        dynamicObstacles.add(packCoord(c, r));
      }
    }
  }

  /** Remove all dynamic obstacles, restoring the original static grid state. */
  public void clearDynamicObstacles() {
    dynamicObstacles.clear();
  }

  // ---- private helpers ----

  private static long packCoord(int col, int row) {
    return ((long) col << 32) | (row & 0xFFFFFFFFL);
  }

  /** Minimal JSON integer parser — finds the first occurrence of {@code key} and returns value. */
  private static int parseInt(String json, String key) {
    int idx = json.indexOf(key);
    if (idx < 0) throw new RuntimeException("Key not found: " + key);
    int colon = json.indexOf(':', idx);
    int start = colon + 1;
    while (start < json.length() && Character.isWhitespace(json.charAt(start))) start++;
    int end = start;
    while (end < json.length() && (Character.isDigit(json.charAt(end)) || json.charAt(end) == '-'))
      end++;
    return Integer.parseInt(json.substring(start, end));
  }

  /** Minimal JSON double parser — finds the first occurrence of {@code key} and returns value. */
  private static double parseDouble(String json, String key) {
    int idx = json.indexOf(key);
    if (idx < 0) throw new RuntimeException("Key not found: " + key);
    int colon = json.indexOf(':', idx);
    int start = colon + 1;
    while (start < json.length() && Character.isWhitespace(json.charAt(start))) start++;
    int end = start;
    while (end < json.length()
        && (Character.isDigit(json.charAt(end))
            || json.charAt(end) == '.'
            || json.charAt(end) == '-')) end++;
    return Double.parseDouble(json.substring(start, end));
  }

  /**
   * Parse the "grid" 2-D array from the JSON string. Assumes grid[row][col] layout (outer array =
   * rows, inner array = columns).
   */
  private static int[][] parseGrid(String json, int rows, int cols) {
    int gridIdx = json.indexOf("\"grid\"");
    if (gridIdx < 0) throw new RuntimeException("'grid' key not found in navgrid.json");
    int outerOpen = json.indexOf('[', gridIdx);

    int[][] grid = new int[rows][cols];
    int pos = outerOpen + 1;

    for (int r = 0; r < rows; r++) {
      int innerOpen = json.indexOf('[', pos);
      pos = innerOpen + 1;
      for (int c = 0; c < cols; c++) {
        // skip whitespace and commas
        while (pos < json.length()
            && (json.charAt(pos) == ',' || Character.isWhitespace(json.charAt(pos)))) pos++;
        grid[r][c] = json.charAt(pos) - '0'; // values are single-digit 0 or 1
        pos++;
      }
      int innerClose = json.indexOf(']', pos);
      pos = innerClose + 1;
    }
    return grid;
  }
}
