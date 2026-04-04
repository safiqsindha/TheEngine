package frc.robot.commands;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Tests for {@link MovingShotCompensation}. */
class MovingShotCompensationTest {

  private static final double TOLERANCE = 1e-3;

  @Test
  @DisplayName("Stationary robot produces zero compensation")
  void testStationary() {
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(0, 0, 0), new Translation2d(5, 0), 0.0);

    assertEquals(0.0, result, TOLERANCE);
  }

  @Test
  @DisplayName("Robot moving directly toward target produces near-zero compensation")
  void testMovingTowardTarget() {
    // Robot heading 0, moving forward (vx=2 robot-relative), target straight ahead
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(2.0, 0, 0), new Translation2d(5, 0), 0.0);

    assertEquals(0.0, result, TOLERANCE);
  }

  @Test
  @DisplayName("Robot moving perpendicular at 2 m/s produces atan(2/12) compensation")
  void testPerpendicularMotion() {
    // Robot heading 0, moving left (vy = +2 robot-relative), target straight ahead (+X)
    // Field velocity: vx=0, vy=2. Target unit = (1,0).
    // Lateral = vx*ty - vy*tx = 0*0 - 2*1 = -2 => compensation = atan(-2/12) ≈ -0.165
    // Use positive vy in robot frame which maps to positive field vy at heading 0
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(0, 2.0, 0), new Translation2d(5, 0), 0.0);

    // vy robot-relative maps to field vy. cross = fieldVx*ty - fieldVy*tx = 0 - 2*1 = -2
    double expected = Math.atan(-2.0 / 12.0);
    assertEquals(expected, result, TOLERANCE);
    // Absolute value check
    assertEquals(Math.atan(2.0 / 12.0), Math.abs(result), TOLERANCE);
  }

  @Test
  @DisplayName("Robot moving perpendicular at 20 m/s is clamped to 15 degrees")
  void testClamped() {
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(0, 20.0, 0), new Translation2d(5, 0), 0.0);

    double maxRad = Math.toRadians(15.0);
    assertEquals(-maxRad, result, TOLERANCE);
  }

  @Test
  @DisplayName("Negative lateral velocity produces negative compensation")
  void testNegativeLateral() {
    // Robot heading 0, moving right (vy = -2 robot-relative), target straight ahead (+X)
    // Field: vx=0, vy=-2. Lateral = 0*0 - (-2)*1 = 2 => compensation positive
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(0, -2.0, 0), new Translation2d(5, 0), 0.0);

    double expected = Math.atan(2.0 / 12.0);
    assertEquals(expected, result, TOLERANCE);

    // Opposite direction
    double resultOther =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(0, 2.0, 0), new Translation2d(5, 0), 0.0);

    assertTrue(resultOther < 0, "Opposite lateral should give opposite sign");
  }

  @Test
  @DisplayName("Zero-length target vector returns 0 without crashing")
  void testZeroTarget() {
    double result =
        MovingShotCompensation.computeCompensation(
            new ChassisSpeeds(5, 5, 1), new Translation2d(0, 0), 0.0);

    assertEquals(0.0, result, TOLERANCE);
  }
}
