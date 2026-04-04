package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Tests for {@link OdometryDivergenceDetector}. */
class OdometryDivergenceDetectorTest {

  private double fakeTime;
  private OdometryDivergenceDetector detector;

  @BeforeEach
  void setUp() {
    fakeTime = 0.0;
    detector = new OdometryDivergenceDetector(() -> fakeTime);
  }

  @Test
  @DisplayName("Identical poses produce zero divergence and no alerts")
  void testIdenticalPoses() {
    Pose2d pose = new Pose2d(1.0, 2.0, new Rotation2d(0));
    detector.update(pose, pose);

    assertEquals(0.0, detector.getDivergenceMeters(), 1e-9);
    assertFalse(detector.isDiverging());
    assertFalse(detector.isCritical());
  }

  @Test
  @DisplayName("Poses 1m apart trigger isDiverging but not isCritical")
  void testWarnThreshold() {
    Pose2d a = new Pose2d(0, 0, new Rotation2d(0));
    Pose2d b = new Pose2d(1, 0, new Rotation2d(0));
    detector.update(a, b);

    assertTrue(detector.isDiverging());
    assertFalse(detector.isCritical());
  }

  @Test
  @DisplayName("Poses 2m apart for 2s triggers isCritical")
  void testCriticalSustained() {
    Pose2d a = new Pose2d(0, 0, new Rotation2d(0));
    Pose2d b = new Pose2d(2, 0, new Rotation2d(0));

    fakeTime = 0.0;
    detector.update(a, b);
    assertFalse(detector.isCritical(), "Should not be critical immediately");

    fakeTime = 2.0;
    detector.update(a, b);
    assertTrue(detector.isCritical(), "Should be critical after 2s sustained divergence");
  }

  @Test
  @DisplayName("Poses 2m apart for 1s then converge resets critical timer")
  void testCriticalTimerResets() {
    Pose2d a = new Pose2d(0, 0, new Rotation2d(0));
    Pose2d far = new Pose2d(2, 0, new Rotation2d(0));
    Pose2d close = new Pose2d(0.5, 0, new Rotation2d(0));

    fakeTime = 0.0;
    detector.update(a, far);

    fakeTime = 1.0;
    detector.update(a, far);
    assertFalse(detector.isCritical(), "Not critical yet at 1s");

    // Converge below critical threshold
    fakeTime = 1.5;
    detector.update(a, close);
    assertFalse(detector.isCritical(), "Timer should reset after convergence");

    // Diverge again — timer restarts from this point
    fakeTime = 2.0;
    detector.update(a, far);
    assertFalse(detector.isCritical(), "Timer restarted, not sustained long enough");

    fakeTime = 4.0;
    detector.update(a, far);
    assertTrue(detector.isCritical(), "Should be critical after sustained divergence from restart");
  }

  @Test
  @DisplayName("reset() clears all state")
  void testReset() {
    Pose2d a = new Pose2d(0, 0, new Rotation2d(0));
    Pose2d b = new Pose2d(2, 0, new Rotation2d(0));

    fakeTime = 0.0;
    detector.update(a, b);
    fakeTime = 5.0;
    detector.update(a, b);
    assertTrue(detector.isCritical());

    detector.reset();
    assertEquals(0.0, detector.getDivergenceMeters(), 1e-9);
    assertFalse(detector.isDiverging());
    assertFalse(detector.isCritical());
  }

  @Test
  @DisplayName("getDivergenceMeters returns correct value")
  void testGetDivergenceMeters() {
    Pose2d a = new Pose2d(0, 0, new Rotation2d(0));
    Pose2d b = new Pose2d(3, 4, new Rotation2d(0));
    detector.update(a, b);

    assertEquals(5.0, detector.getDivergenceMeters(), 1e-9);
  }
}
