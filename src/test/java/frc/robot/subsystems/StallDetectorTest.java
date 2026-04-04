package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/** Unit tests for {@link StallDetector}. Uses mutable suppliers for deterministic testing. */
class StallDetectorTest {

  private double currentAmps = 0.0;
  private double timeSeconds = 0.0;

  private StallDetector createDetector(double thresholdAmps, double durationSeconds) {
    return new StallDetector(
        "TestMotor", () -> currentAmps, thresholdAmps, durationSeconds, () -> timeSeconds);
  }

  @Test
  void normalCurrentBelowThreshold_notStalled() {
    StallDetector detector = createDetector(40.0, 0.5);
    currentAmps = 20.0;
    timeSeconds = 0.0;

    detector.update();

    assertFalse(detector.isStalled());
    assertEquals(0.0, detector.getStallDurationSeconds());
  }

  @Test
  void highCurrentForLessThanDuration_notStalled() {
    StallDetector detector = createDetector(40.0, 0.5);

    // Current goes above threshold
    currentAmps = 50.0;
    timeSeconds = 1.0;
    detector.update();

    // Advance time but not enough
    timeSeconds = 1.3;
    detector.update();

    assertFalse(detector.isStalled());
    assertTrue(detector.getStallDurationSeconds() > 0);
    assertTrue(detector.getStallDurationSeconds() < 0.5);
  }

  @Test
  void highCurrentForLongerThanDuration_stalled() {
    StallDetector detector = createDetector(40.0, 0.5);

    // Current goes above threshold
    currentAmps = 50.0;
    timeSeconds = 1.0;
    detector.update();

    // Advance time past duration threshold
    timeSeconds = 1.6;
    detector.update();

    assertTrue(detector.isStalled());
    assertTrue(detector.getStallDurationSeconds() > 0.5);
  }

  @Test
  void currentDropsBelowThreshold_notStalledAnymore() {
    StallDetector detector = createDetector(40.0, 0.5);

    // Trigger a stall
    currentAmps = 50.0;
    timeSeconds = 1.0;
    detector.update();
    timeSeconds = 1.6;
    detector.update();
    assertTrue(detector.isStalled());

    // Current drops below threshold
    currentAmps = 20.0;
    timeSeconds = 2.0;
    detector.update();

    assertFalse(detector.isStalled());
    assertEquals(0.0, detector.getStallDurationSeconds());
  }

  @Test
  void resetClearsStallState() {
    StallDetector detector = createDetector(40.0, 0.5);

    // Trigger a stall
    currentAmps = 50.0;
    timeSeconds = 1.0;
    detector.update();
    timeSeconds = 1.6;
    detector.update();
    assertTrue(detector.isStalled());

    // Reset
    detector.reset();

    assertFalse(detector.isStalled());
    assertEquals(0.0, detector.getStallDurationSeconds());
  }

  @Test
  void multipleStallClearCycles() {
    StallDetector detector = createDetector(40.0, 0.5);

    // First stall cycle
    currentAmps = 50.0;
    timeSeconds = 0.0;
    detector.update();
    timeSeconds = 0.6;
    detector.update();
    assertTrue(detector.isStalled());

    // Clear
    currentAmps = 10.0;
    timeSeconds = 1.0;
    detector.update();
    assertFalse(detector.isStalled());

    // Second stall cycle
    currentAmps = 60.0;
    timeSeconds = 2.0;
    detector.update();
    assertFalse(detector.isStalled()); // Not long enough yet

    timeSeconds = 2.6;
    detector.update();
    assertTrue(detector.isStalled());

    // Clear again
    currentAmps = 5.0;
    timeSeconds = 3.0;
    detector.update();
    assertFalse(detector.isStalled());

    // Third stall cycle
    currentAmps = 45.0;
    timeSeconds = 4.0;
    detector.update();
    timeSeconds = 4.7;
    detector.update();
    assertTrue(detector.isStalled());
  }
}
