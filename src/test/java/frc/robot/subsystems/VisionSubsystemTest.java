package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/**
 * Unit tests for VisionSubsystem's pure-logic botpose validation. Tests the static isValidBotpose()
 * method without requiring NetworkTables, HAL, or hardware.
 */
class VisionSubsystemTest {

  // Default thresholds matching VisionSubsystem constants
  private static final int MIN_TAG_COUNT = 1;
  private static final double MAX_LATENCY_MS = 50.0;
  private static final double MAX_TAG_DIST_M = 4.0;

  /** Build a minimal valid botpose array (11 elements) with the given field values. */
  private static double[] validBotpose(
      double x, double y, double yaw, double latencyMs, int tagCount, double avgTagDistM) {
    double[] arr = new double[11];
    arr[0] = x;
    arr[1] = y;
    arr[5] = yaw;
    arr[6] = latencyMs;
    arr[7] = tagCount;
    arr[9] = avgTagDistM;
    return arr;
  }

  @Test
  void testValidMeasurement_passes() {
    double[] botpose = validBotpose(4.0, 4.0, 0.0, 20.0, 2, 2.0);
    assertTrue(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testNullArray_fails() {
    assertFalse(
        VisionSubsystem.isValidBotpose(null, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testEmptyArray_fails() {
    assertFalse(
        VisionSubsystem.isValidBotpose(
            new double[0], MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testShortArray_fails() {
    assertFalse(
        VisionSubsystem.isValidBotpose(
            new double[10], MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testZeroTagCount_fails() {
    double[] botpose = validBotpose(4.0, 4.0, 0.0, 20.0, 0, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testLatencyExceedsMax_fails() {
    double[] botpose = validBotpose(4.0, 4.0, 0.0, 51.0, 1, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testAvgTagDistExceedsMax_fails() {
    double[] botpose = validBotpose(4.0, 4.0, 0.0, 20.0, 1, 4.1);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testNegativeX_fails() {
    double[] botpose = validBotpose(-0.1, 4.0, 0.0, 20.0, 1, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testXExceedsFieldLength_fails() {
    double[] botpose = validBotpose(16.55, 4.0, 0.0, 20.0, 1, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testNegativeY_fails() {
    double[] botpose = validBotpose(4.0, -0.1, 0.0, 20.0, 1, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testYExceedsFieldWidth_fails() {
    double[] botpose = validBotpose(4.0, 8.22, 0.0, 20.0, 1, 2.0);
    assertFalse(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testPoseAtFieldCorner_passes() {
    // Exactly at (0, 0) — field origin — should be valid
    double[] botpose = validBotpose(0.0, 0.0, 0.0, 10.0, 1, 1.0);
    assertTrue(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testPoseAtFarFieldCorner_passes() {
    double[] botpose = validBotpose(16.54, 8.21, 180.0, 10.0, 1, 1.0);
    assertTrue(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }

  @Test
  void testLatencyAtExactMax_passes() {
    double[] botpose = validBotpose(4.0, 4.0, 0.0, 50.0, 1, 2.0);
    assertTrue(
        VisionSubsystem.isValidBotpose(botpose, MIN_TAG_COUNT, MAX_LATENCY_MS, MAX_TAG_DIST_M));
  }
}
