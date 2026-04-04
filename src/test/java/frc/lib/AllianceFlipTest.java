package frc.lib;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Tests for AllianceFlip utility. Verifies pose mirroring math between blue and red alliance sides.
 *
 * <p>Uses the package-private {@code flip(T, boolean isRed)} overloads to test the mirroring math
 * directly, without requiring HAL initialization or a DriverStation connection. The public {@code
 * flip(T)} overloads delegate to these, so the math is fully covered.
 *
 * <p>Field length matches {@code AllianceFlip.kFieldLengthMeters}: 16.54 m.
 */
class AllianceFlipTest {

  private static final double FIELD_LENGTH = AllianceFlip.getFieldLengthMeters(); // 16.54
  private static final double DELTA = 0.001;

  @Test
  @DisplayName("Gate 1: Flip translation blue→red mirrors X, preserves Y")
  void testFlipTranslation_blueToRed_xMirrored() {
    Translation2d blue = new Translation2d(2.0, 3.0);
    Translation2d red = AllianceFlip.flip(blue, true);

    assertEquals(
        FIELD_LENGTH - 2.0, red.getX(), DELTA, "Flipped X should be FIELD_LENGTH - original X");
    assertEquals(3.0, red.getY(), DELTA, "Y should be unchanged after flip");
  }

  @Test
  @DisplayName("Gate 1: Flip pose blue→red mirrors X and heading")
  void testFlipPose_blueToRed_headingMirrored() {
    Pose2d blue = new Pose2d(2.0, 3.0, Rotation2d.fromDegrees(45));
    Pose2d red = AllianceFlip.flip(blue, true);

    assertEquals(FIELD_LENGTH - 2.0, red.getX(), DELTA, "Flipped X should be FIELD_LENGTH - 2.0");
    assertEquals(3.0, red.getY(), DELTA, "Y should be unchanged");
    // Heading mirrors across Y axis: π - θ → 180 - 45 = 135 degrees
    assertEquals(
        135.0,
        red.getRotation().getDegrees(),
        DELTA,
        "Heading should mirror to 180 - 45 = 135 deg");
  }

  @Test
  @DisplayName("Gate 1: Pose at field center X stays at center after flip")
  void testFlipPose_atFieldCenter_staysCenter() {
    Pose2d center = new Pose2d(FIELD_LENGTH / 2.0, 4.0, Rotation2d.fromDegrees(90));
    Pose2d flipped = AllianceFlip.flip(center, true);

    assertEquals(
        FIELD_LENGTH / 2.0,
        flipped.getX(),
        DELTA,
        "A pose at field center X should remain at center X after flip");
  }

  @Test
  @DisplayName("Gate 1: Flipping twice returns to original pose")
  void testDoubleFlip_returnsOriginal() {
    Pose2d original = new Pose2d(3.5, 2.1, Rotation2d.fromDegrees(120));
    Pose2d doubleFlipped = AllianceFlip.flip(AllianceFlip.flip(original, true), true);

    assertEquals(
        original.getX(), doubleFlipped.getX(), DELTA, "Double-flip X should equal original");
    assertEquals(
        original.getY(), doubleFlipped.getY(), DELTA, "Double-flip Y should equal original");
    assertEquals(
        original.getRotation().getDegrees(),
        doubleFlipped.getRotation().getDegrees(),
        DELTA,
        "Double-flip heading should equal original");
  }

  @Test
  @DisplayName("Gate 1: Blue alliance flip is identity (no mirroring)")
  void testFlipOnBlue_isIdentity() {
    Pose2d original = new Pose2d(3.0, 4.0, Rotation2d.fromDegrees(60));
    Pose2d flipped = AllianceFlip.flip(original, false);

    assertEquals(original.getX(), flipped.getX(), DELTA, "Blue flip X should be unchanged");
    assertEquals(original.getY(), flipped.getY(), DELTA, "Blue flip Y should be unchanged");
    assertEquals(
        original.getRotation().getDegrees(),
        flipped.getRotation().getDegrees(),
        DELTA,
        "Blue flip heading should be unchanged");
  }
}
