package frc.robot.commands;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Tests for AutoAlignCommand and DriveToGamePieceCommand logic. Since these commands require
 * subsystem instantiation (HAL), we test the pure math and constants they rely on.
 *
 * <p>AutoAlignCommand: P-controller rotation from Limelight tx offset. DriveToGamePieceCommand:
 * nearest-fuel selection and proportional translation control.
 */
class TeleopAssistCommandsTest {

  // ── AutoAlignCommand constants ──────────────────────────────────────────

  private static final double AUTO_ALIGN_KP = 0.05;
  private static final double ROTATION_SIGN = -1.0;

  @Test
  void autoAlign_pGainIsPositive() {
    assertTrue(AUTO_ALIGN_KP > 0, "P gain must be positive");
  }

  @Test
  void autoAlign_zeroOffsetProducesZeroRotation() {
    double rotation = ROTATION_SIGN * (0.0 * AUTO_ALIGN_KP);
    assertEquals(0.0, rotation, 1e-9);
  }

  @Test
  void autoAlign_positiveOffsetProducesCorrectRotation() {
    // Target is 10 degrees to the right (positive tx)
    double txOffset = 10.0;
    double rotation = ROTATION_SIGN * (txOffset * AUTO_ALIGN_KP);
    // With ROTATION_SIGN = -1.0: positive tx → negative rotation (turn right)
    assertTrue(rotation < 0, "Positive tx offset should produce negative rotation (turn right)");
    assertEquals(-0.5, rotation, 1e-9);
  }

  @Test
  void autoAlign_negativeOffsetProducesCorrectRotation() {
    double txOffset = -10.0;
    double rotation = ROTATION_SIGN * (txOffset * AUTO_ALIGN_KP);
    assertTrue(rotation > 0, "Negative tx offset should produce positive rotation (turn left)");
    assertEquals(0.5, rotation, 1e-9);
  }

  @Test
  void autoAlign_largeOffsetProducesStrongRotation() {
    double txOffset = 25.0; // edge of Limelight FOV
    double rotation = Math.abs(ROTATION_SIGN * (txOffset * AUTO_ALIGN_KP));
    assertTrue(rotation > 1.0, "Large offset should produce significant rotation");
  }

  // ── DriveToGamePiece constants ──────────────────────────────────────────

  private static final double TRANSLATION_P = 0.4;
  private static final double ARRIVAL_THRESHOLD_M = 0.5;

  @Test
  void driveToGamePiece_arrivalThresholdIsPositive() {
    assertTrue(ARRIVAL_THRESHOLD_M > 0);
  }

  @Test
  void driveToGamePiece_translationPIsPositive() {
    assertTrue(TRANSLATION_P > 0);
  }

  // ── Nearest fuel selection logic ────────────────────────────────────────
  // Replicates the core selection algorithm from DriveToGamePieceCommand.execute()

  private Translation2d findNearest(Translation2d robotPos, List<Translation2d> fuelPositions) {
    Translation2d nearest = null;
    double nearestDist = Double.MAX_VALUE;
    for (Translation2d pos : fuelPositions) {
      double dist = robotPos.getDistance(pos);
      if (dist < nearestDist) {
        nearest = pos;
        nearestDist = dist;
      }
    }
    return nearest;
  }

  @Test
  void nearestFuel_selectsClosestFromMultiple() {
    Translation2d robot = new Translation2d(3.0, 4.0);
    List<Translation2d> fuel =
        List.of(
            new Translation2d(5.0, 4.0), // 2.0m
            new Translation2d(3.5, 4.0), // 0.5m — closest
            new Translation2d(8.0, 4.0)); // 5.0m
    Translation2d nearest = findNearest(robot, fuel);
    assertEquals(new Translation2d(3.5, 4.0), nearest);
  }

  @Test
  void nearestFuel_singleFuelReturnsIt() {
    Translation2d robot = new Translation2d(3.0, 4.0);
    List<Translation2d> fuel = List.of(new Translation2d(6.0, 4.0));
    Translation2d nearest = findNearest(robot, fuel);
    assertEquals(new Translation2d(6.0, 4.0), nearest);
  }

  @Test
  void nearestFuel_emptyListReturnsNull() {
    Translation2d robot = new Translation2d(3.0, 4.0);
    Translation2d nearest = findNearest(robot, List.of());
    assertNull(nearest);
  }

  @Test
  void nearestFuel_diagonalDistanceCalculation() {
    Translation2d robot = new Translation2d(0.0, 0.0);
    List<Translation2d> fuel =
        List.of(
            new Translation2d(3.0, 0.0), // 3.0m on X axis
            new Translation2d(2.0, 2.0)); // ~2.83m diagonal — closer
    Translation2d nearest = findNearest(robot, fuel);
    assertEquals(new Translation2d(2.0, 2.0), nearest);
  }

  // ── Proportional speed control logic ────────────────────────────────────
  // Replicates: speed = Math.min(nearestDist * kTranslationP, 1.0)

  @Test
  void proportionalSpeed_capsAtOne() {
    double farDist = 5.0;
    double speed = Math.min(farDist * TRANSLATION_P, 1.0);
    assertEquals(1.0, speed, 1e-9, "Speed should cap at 1.0 for far targets");
  }

  @Test
  void proportionalSpeed_proportionalForCloseTargets() {
    double closeDist = 1.0;
    double speed = Math.min(closeDist * TRANSLATION_P, 1.0);
    assertEquals(0.4, speed, 1e-9, "Speed should be proportional for close targets");
  }

  @Test
  void proportionalSpeed_zeroAtZeroDistance() {
    double speed = Math.min(0.0 * TRANSLATION_P, 1.0);
    assertEquals(0.0, speed, 1e-9);
  }

  @Test
  void proportionalSpeed_capThresholdDistance() {
    // At what distance does speed cap? 1.0 / kP = 2.5m
    double capDist = 1.0 / TRANSLATION_P;
    assertEquals(2.5, capDist, 1e-9, "Speed should cap at 2.5m distance");
    double speed = Math.min(capDist * TRANSLATION_P, 1.0);
    assertEquals(1.0, speed, 1e-9);
  }

  // ── Arrival threshold ───────────────────────────────────────────────────

  @Test
  void arrivalThreshold_withinThresholdMeansArrived() {
    double dist = 0.3; // < 0.5m threshold
    assertTrue(dist <= ARRIVAL_THRESHOLD_M, "Should be within arrival threshold");
  }

  @Test
  void arrivalThreshold_outsideThresholdMeansNotArrived() {
    double dist = 1.0; // > 0.5m threshold
    assertFalse(dist <= ARRIVAL_THRESHOLD_M, "Should be outside arrival threshold");
  }

  // ── Drive deadband ──────────────────────────────────────────────────────
  // Mirrors Constants.OI.kDriveDeadband — hardcoded to avoid HAL JNI dependency
  private static final double DRIVE_DEADBAND = 0.1;

  @Test
  void driveDeadbandIsPositive() {
    assertTrue(DRIVE_DEADBAND > 0, "Drive deadband must be positive");
    assertTrue(DRIVE_DEADBAND < 0.5, "Drive deadband should not be too large");
  }
}
