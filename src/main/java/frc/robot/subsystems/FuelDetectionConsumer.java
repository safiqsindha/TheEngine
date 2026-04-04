package frc.robot.subsystems;

import edu.wpi.first.math.geometry.Translation2d;
import frc.robot.Constants;
import java.util.ArrayList;
import java.util.List;

/**
 * Parses the Limelight {@code llpython} NetworkTables array for FUEL detections produced by the
 * Wave Robotics YOLOv11n ONNX model (single class: fuel balls only).
 *
 * <p>Applies an 80 % confidence filter and enforces 3-frame persistence before reporting a
 * detection as confirmed.
 *
 * <p><b>Array format</b> (published by {@code tools/snapscript_fuel_detector.py}):
 *
 * <pre>
 *   index 0         : numFuel (int, cast from double)
 *   index 1 + i*3   : fx_i   (field-relative X, meters)
 *   index 2 + i*3   : fy_i   (field-relative Y, meters)
 *   index 3 + i*3   : conf_i (confidence, 0.0–1.0)
 *   ...
 *   (array is zero-padded to a fixed length of 1 + MAX_FUEL * 3 = 25 elements)
 * </pre>
 *
 * <p>The model is fuel-only — it has no opponent class. Opponent positions are therefore always
 * empty; the robot relies on AprilTag-based pose estimation to track opposing robots.
 *
 * <p>A detection is only included in {@link #getDetectedFuelPositions()} once it has appeared in at
 * least {@link Constants.Pathfinding#kFuelPersistenceFrames} consecutive frames with confidence ≥
 * {@link Constants.Pathfinding#kFuelConfidenceThreshold}.
 */
public class FuelDetectionConsumer {

  /** Tolerance (meters) for associating a new detection with an existing candidate. */
  private static final double MATCH_TOLERANCE_M = 0.5;

  /** Tracks a candidate detection across frames before it is confirmed. */
  private static final class Candidate {
    Translation2d position;
    int consecutiveFrames;

    Candidate(Translation2d position) {
      this.position = position;
      this.consecutiveFrames = 1;
    }
  }

  private final List<Candidate> candidates = new ArrayList<>();

  /**
   * Ingest a raw {@code llpython} array from NetworkTables for one robot loop cycle.
   *
   * @param raw the double array published by the Limelight SnapScript; may be null or empty
   */
  public void updateFromRawArray(double[] raw) {
    List<Translation2d> newDetections = parseAndFilter(raw);

    boolean[] matched = new boolean[newDetections.size()];
    List<Candidate> surviving = new ArrayList<>();

    // Match new detections to existing candidates (nearest-first within tolerance)
    for (Candidate candidate : candidates) {
      int bestIdx = -1;
      double bestDist = MATCH_TOLERANCE_M;
      for (int i = 0; i < newDetections.size(); i++) {
        if (matched[i]) continue;
        double dist = candidate.position.getDistance(newDetections.get(i));
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0) {
        // Candidate persists — update position to latest reading, increment counter
        candidate.position = newDetections.get(bestIdx);
        candidate.consecutiveFrames++;
        matched[bestIdx] = true;
        surviving.add(candidate);
      }
      // else: candidate was not seen this frame — drop it (counter resets implicitly)
    }

    // Any unmatched new detection starts a fresh candidate with count = 1
    for (int i = 0; i < newDetections.size(); i++) {
      if (!matched[i]) {
        surviving.add(new Candidate(newDetections.get(i)));
      }
    }

    candidates.clear();
    candidates.addAll(surviving);
  }

  /**
   * Returns the list of confirmed FUEL positions (field-space meters). A detection is confirmed
   * once it has appeared in {@link Constants.Pathfinding#kFuelPersistenceFrames} consecutive
   * frames.
   *
   * @return unmodifiable list of confirmed positions, capped at {@link
   *     Constants.Pathfinding#kMaxFuelDetections}
   */
  public List<Translation2d> getDetectedFuelPositions() {
    List<Translation2d> confirmed = new ArrayList<>();
    for (Candidate c : candidates) {
      if (c.consecutiveFrames >= Constants.Pathfinding.kFuelPersistenceFrames) {
        confirmed.add(c.position);
        if (confirmed.size() >= Constants.Pathfinding.kMaxFuelDetections) break;
      }
    }
    return List.copyOf(confirmed);
  }

  /**
   * Returns confirmed opponent positions. The Wave Robotics YOLOv11n model is fuel-only and does
   * not detect opponent robots. This method always returns an empty list.
   *
   * <p>To add opponent tracking, use AprilTag-based pose data from the Limelight AprilTag pipeline
   * (Pipeline 0) and compare to known alliance station positions.
   *
   * @return always an empty list
   */
  public List<Translation2d> getDetectedOpponentPositions() {
    return List.of();
  }

  // ── private helpers ─────────────────────────────────────────────────────────

  /**
   * Parse and confidence-filter the raw {@code llpython} array.
   *
   * @return list of positions whose confidence ≥ {@link
   *     Constants.Pathfinding#kFuelConfidenceThreshold}
   */
  private static List<Translation2d> parseAndFilter(double[] raw) {
    if (raw == null || raw.length < 1) return List.of();

    int numFuel = Math.max(0, (int) raw[0]);
    if (numFuel == 0 || raw.length < 1 + numFuel * 3) return List.of();

    List<Translation2d> result = new ArrayList<>();
    for (int i = 0; i < numFuel; i++) {
      int base = 1 + i * 3;
      double x = raw[base];
      double y = raw[base + 1];
      double conf = raw[base + 2];
      if (conf >= Constants.Pathfinding.kFuelConfidenceThreshold) {
        result.add(new Translation2d(x, y));
      }
    }
    return result;
  }
}
