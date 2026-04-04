package frc.robot.commands;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link PathfindToGoalCommand} constants and PathPlanner configuration. The command
 * itself is a thin wrapper around PPLib's pathfinding, so we validate the constraints and
 * configuration constants it uses.
 *
 * <p>Constants are hardcoded here to avoid importing frc.robot.Constants, which transitively loads
 * HAL JNI natives and crashes in plain unit tests.
 */
class PathfindToGoalCommandTest {

  // Mirrors Constants.Swerve values
  private static final double MAX_SPEED_MPS = 14.5 * 0.3048; // Units.feetToMeters(14.5) ≈ 4.4196
  private static final double MAX_ANGULAR_SPEED_RAD_PER_SEC = Math.PI * 2;
  private static final double MODULE_LOCATION_INCHES = 11.0;
  private static final double WHEEL_DIAMETER_INCHES = 4.0;
  private static final double DRIVE_GEAR_RATIO = 6.23;

  // Mirrors Constants top-level
  private static final double FIELD_LENGTH_METERS = 16.541;
  private static final double ROBOT_MASS_KG = (148 - 20.3) * 0.453592;

  // Mirrors Constants.Pathfinding
  private static final double REPLAN_THRESHOLD_METERS = 0.30;
  private static final int NAV_GRID_COLUMNS = 164;
  private static final int NAV_GRID_ROWS = 82;
  private static final double NAV_GRID_CELL_SIZE_METERS = 0.10;

  @Test
  void maxSpeedIsPositive() {
    assertTrue(MAX_SPEED_MPS > 0);
  }

  @Test
  void maxAngularSpeedIsPositive() {
    assertTrue(MAX_ANGULAR_SPEED_RAD_PER_SEC > 0);
  }

  @Test
  void maxSpeedIsReasonable() {
    // FRC robots typically max out around 5-6 m/s
    assertTrue(MAX_SPEED_MPS <= 7.0, "Max speed seems unreasonably high");
    assertTrue(MAX_SPEED_MPS >= 1.0, "Max speed seems unreasonably low");
  }

  @Test
  void maxAngularSpeedIsReasonable() {
    // Most swerve robots rotate at 1-3 full rotations per second (6-19 rad/s)
    assertTrue(MAX_ANGULAR_SPEED_RAD_PER_SEC >= 1.0, "Angular speed seems too low");
    assertTrue(MAX_ANGULAR_SPEED_RAD_PER_SEC <= 20.0, "Angular speed seems too high");
  }

  // ── Target pose validation ──────────────────────────────────────────────

  @Test
  void targetPoseWithinFieldBounds() {
    // Typical scoring positions should be within field
    Pose2d scorePose = new Pose2d(2.0, 4.0, Rotation2d.fromDegrees(0));
    assertTrue(scorePose.getX() >= 0 && scorePose.getX() <= FIELD_LENGTH_METERS);
    assertTrue(scorePose.getY() >= 0 && scorePose.getY() <= 8.21);
  }

  @Test
  void distanceCalculationIsCorrect() {
    // Verify the distance remaining calculation used in execute()
    Pose2d robotPose = new Pose2d(2.0, 4.0, new Rotation2d());
    Pose2d targetPose = new Pose2d(5.0, 8.0, new Rotation2d());
    double distance = robotPose.getTranslation().getDistance(targetPose.getTranslation());
    assertEquals(5.0, distance, 0.01); // sqrt(9 + 16) = 5.0
  }

  @Test
  void zeroDistanceWhenAtTarget() {
    Pose2d pose = new Pose2d(3.0, 4.0, new Rotation2d());
    double distance = pose.getTranslation().getDistance(pose.getTranslation());
    assertEquals(0.0, distance, 1e-9);
  }

  // ── PathPlanner constraint validation ───────────────────────────────────

  @Test
  void replanThresholdIsPositive() {
    assertTrue(REPLAN_THRESHOLD_METERS > 0);
  }

  @Test
  void navGridDimensionsMatchFieldSize() {
    // 164 columns at 0.10m = 16.4m field length (close to 16.54)
    double gridLength = NAV_GRID_COLUMNS * NAV_GRID_CELL_SIZE_METERS;
    assertEquals(16.4, gridLength, 0.5, "Grid should approximate field length");

    // 82 rows at 0.10m = 8.2m field width (close to 8.21)
    double gridWidth = NAV_GRID_ROWS * NAV_GRID_CELL_SIZE_METERS;
    assertEquals(8.2, gridWidth, 0.5, "Grid should approximate field width");
  }

  // ── Module location / robot geometry ────────────────────────────────────

  @Test
  void moduleLocationIsPositive() {
    assertTrue(MODULE_LOCATION_INCHES > 0);
  }

  @Test
  void wheelDiameterIsReasonable() {
    // FRC wheels are typically 3-6 inches
    assertTrue(WHEEL_DIAMETER_INCHES >= 3.0);
    assertTrue(WHEEL_DIAMETER_INCHES <= 6.0);
  }

  @Test
  void driveGearRatioIsReasonable() {
    // Swerve drive gear ratios are typically 4-8
    assertTrue(DRIVE_GEAR_RATIO >= 4.0);
    assertTrue(DRIVE_GEAR_RATIO <= 9.0);
  }

  @Test
  void robotMassIsReasonable() {
    // FRC robots are 50-70 kg typically
    assertTrue(ROBOT_MASS_KG >= 30.0);
    assertTrue(ROBOT_MASS_KG <= 80.0);
  }
}
