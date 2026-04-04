package frc.robot;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/**
 * Unit tests for Helper.rpmFromMeters() — pure piecewise-linear interpolation with clamping. No HAL
 * or hardware dependency.
 */
class HelperTest {

  // Calibration points from Helper.rpmFromMeters()
  private static final double X1 = 1.125, Y1 = 2500.0;
  private static final double X2 = 1.714, Y2 = 3000.0;
  private static final double X3 = 2.5, Y3 = 3500.0;

  @Test
  void testRpmFromMeters_atX1_returnsY1() {
    assertEquals(Y1, Helper.rpmFromMeters(X1), 1.0);
  }

  @Test
  void testRpmFromMeters_atX2_returnsY2() {
    assertEquals(Y2, Helper.rpmFromMeters(X2), 1.0);
  }

  @Test
  void testRpmFromMeters_atX3_returnsY3() {
    assertEquals(Y3, Helper.rpmFromMeters(X3), 1.0);
  }

  @Test
  void testRpmFromMeters_midpointX1X2_interpolatesLinearly() {
    double mid = (X1 + X2) / 2.0;
    double expected = (Y1 + Y2) / 2.0;
    assertEquals(expected, Helper.rpmFromMeters(mid), 1.0);
  }

  @Test
  void testRpmFromMeters_midpointX2X3_interpolatesLinearly() {
    double mid = (X2 + X3) / 2.0;
    double expected = (Y2 + Y3) / 2.0;
    assertEquals(expected, Helper.rpmFromMeters(mid), 1.0);
  }

  @Test
  void testRpmFromMeters_belowMinDistance_clampedToMinRpm() {
    double rpm = Helper.rpmFromMeters(0.0);
    assertEquals(Constants.Flywheel.kMinRpm, rpm, 1.0);
  }

  @Test
  void testRpmFromMeters_farAboveX3_clampedToMaxRpm() {
    double rpm = Helper.rpmFromMeters(100.0);
    assertEquals(Constants.Flywheel.kMaxRpm, rpm, 1.0);
  }

  @Test
  void testRpmFromMeters_outputNeverExceedsMaxRpm() {
    // Step in integer centimeters to avoid float loop counter SpotBugs warning
    for (int cm = 0; cm <= 1000; cm += 10) {
      double d = cm / 100.0;
      double rpm = Helper.rpmFromMeters(d);
      assertTrue(rpm <= Constants.Flywheel.kMaxRpm, "RPM exceeded max at distance " + d);
    }
  }

  @Test
  void testRpmFromMeters_outputNeverBelowMinRpm() {
    for (int cm = 0; cm <= 1000; cm += 10) {
      double d = cm / 100.0;
      double rpm = Helper.rpmFromMeters(d);
      assertTrue(rpm >= Constants.Flywheel.kMinRpm, "RPM below min at distance " + d);
    }
  }
}
