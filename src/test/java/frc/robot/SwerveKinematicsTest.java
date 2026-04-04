package frc.robot;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.math.kinematics.SwerveDriveKinematics;
import edu.wpi.first.math.kinematics.SwerveModuleState;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Kinematic validation tests for Phase Gates 1.3 and 1.4.
 *
 * <p>These tests validate pure math using WPILib's SwerveDriveKinematics, independent of YAGSL.
 * They verify that the module locations and expected kinematics are correct before running on
 * hardware or in full simulation.
 */
class SwerveKinematicsTest {

  // Module locations matching hardware-verified YAGSL JSON config (converted to meters)
  private static final double kHalfTrack = 0.2794; // 11 inches in meters
  private static final Translation2d kFrontLeft = new Translation2d(kHalfTrack, kHalfTrack);
  private static final Translation2d kFrontRight = new Translation2d(kHalfTrack, -kHalfTrack);
  private static final Translation2d kBackLeft = new Translation2d(-kHalfTrack, kHalfTrack);
  private static final Translation2d kBackRight = new Translation2d(-kHalfTrack, -kHalfTrack);

  private static SwerveDriveKinematics kinematics;

  @BeforeAll
  static void setup() {
    kinematics = new SwerveDriveKinematics(kFrontLeft, kFrontRight, kBackLeft, kBackRight);
  }

  @Test
  @DisplayName("Gate 1.3: Pure forward at 2 m/s — all modules point forward")
  void pureForwardTranslation() {
    ChassisSpeeds speeds = new ChassisSpeeds(2.0, 0.0, 0.0);
    SwerveModuleState[] states = kinematics.toSwerveModuleStates(speeds);

    for (int i = 0; i < 4; i++) {
      // All modules should be at ~2 m/s
      assertEquals(
          2.0, states[i].speedMetersPerSecond, 0.01, "Module " + i + " speed should be ~2.0 m/s");
      // All modules should point forward (0 degrees)
      assertEquals(
          0.0, states[i].angle.getDegrees(), 0.5, "Module " + i + " should point forward (0 deg)");
    }
  }

  @Test
  @DisplayName("Gate 1.3: Pure strafe left at 2 m/s — all modules point left")
  void pureStrafeTranslation() {
    ChassisSpeeds speeds = new ChassisSpeeds(0.0, 2.0, 0.0);
    SwerveModuleState[] states = kinematics.toSwerveModuleStates(speeds);

    for (int i = 0; i < 4; i++) {
      assertEquals(
          2.0, states[i].speedMetersPerSecond, 0.01, "Module " + i + " speed should be ~2.0 m/s");
      assertEquals(
          90.0, states[i].angle.getDegrees(), 0.5, "Module " + i + " should point left (90 deg)");
    }
  }

  @Test
  @DisplayName("Gate 1.4: Pure rotation at 1 rad/s — modules tangent to circle")
  void pureRotation() {
    ChassisSpeeds speeds = new ChassisSpeeds(0.0, 0.0, 1.0);
    SwerveModuleState[] states = kinematics.toSwerveModuleStates(speeds);

    // For a square chassis, each module is at distance sqrt(2) * halfTrack from center
    double moduleRadius = Math.sqrt(2) * kHalfTrack;
    double expectedSpeed = moduleRadius * 1.0; // v = r * omega

    for (int i = 0; i < 4; i++) {
      assertEquals(
          expectedSpeed,
          states[i].speedMetersPerSecond,
          0.01,
          "Module " + i + " speed should be ~" + expectedSpeed + " m/s");
    }

    // Front-left should point at ~135 degrees (tangent to CCW rotation)
    assertEquals(135.0, states[0].angle.getDegrees(), 1.0, "FL should be ~135 deg");
    // Front-right should point at ~45 degrees
    assertEquals(45.0, states[1].angle.getDegrees(), 1.0, "FR should be ~45 deg");
    // Back-left should point at ~-135 degrees (or 225)
    double blAngle = states[2].angle.getDegrees();
    assertTrue(
        Math.abs(blAngle - (-135.0)) < 1.0 || Math.abs(blAngle - 225.0) < 1.0,
        "BL should be ~-135 or ~225 deg, got " + blAngle);
    // Back-right should point at ~-45 degrees (or 315)
    double brAngle = states[3].angle.getDegrees();
    assertTrue(
        Math.abs(brAngle - (-45.0)) < 1.0 || Math.abs(brAngle - 315.0) < 1.0,
        "BR should be ~-45 or ~315 deg, got " + brAngle);
  }

  @Test
  @DisplayName("Gate 1.4: Combined strafe-and-rotate — no desync")
  void combinedStrafeAndRotate() {
    ChassisSpeeds speeds = new ChassisSpeeds(1.5, 1.0, 0.5);
    SwerveModuleState[] states = kinematics.toSwerveModuleStates(speeds);

    // Verify all module speeds are positive and reasonable
    for (int i = 0; i < 4; i++) {
      assertTrue(states[i].speedMetersPerSecond > 0, "Module " + i + " speed should be positive");
      assertTrue(
          states[i].speedMetersPerSecond < Constants.Swerve.kMaxSpeedMetersPerSec * 1.5,
          "Module " + i + " speed should be within reasonable bounds");
    }

    // Verify inverse kinematics recovers original chassis speeds
    ChassisSpeeds recovered = kinematics.toChassisSpeeds(states);
    assertEquals(
        speeds.vxMetersPerSecond,
        recovered.vxMetersPerSecond,
        0.05,
        "Recovered Vx should match input");
    assertEquals(
        speeds.vyMetersPerSecond,
        recovered.vyMetersPerSecond,
        0.05,
        "Recovered Vy should match input");
    assertEquals(
        speeds.omegaRadiansPerSecond,
        recovered.omegaRadiansPerSecond,
        0.05,
        "Recovered omega should match input");
  }

  @Test
  @DisplayName("Module locations form a square chassis")
  void moduleLocationsAreSquare() {
    // All modules should be equidistant from center
    double flDist = kFrontLeft.getNorm();
    double frDist = kFrontRight.getNorm();
    double blDist = kBackLeft.getNorm();
    double brDist = kBackRight.getNorm();

    assertEquals(flDist, frDist, 0.001, "FL and FR should be same distance from center");
    assertEquals(flDist, blDist, 0.001, "FL and BL should be same distance from center");
    assertEquals(flDist, brDist, 0.001, "FL and BR should be same distance from center");
  }
}
