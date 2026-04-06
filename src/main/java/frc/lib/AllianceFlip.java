package frc.lib;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.DriverStation.Alliance;

/**
 * Utility for flipping coordinates between red and blue alliance origins. The FRC field is 16.54m
 * long (X axis) and 8.21m wide (Y axis). Blue alliance origin is at the left corner of the blue
 * driver station wall.
 */
public final class AllianceFlip {

  private static final double kFieldLengthMeters = 16.541;

  private AllianceFlip() {}

  /** Returns true if the robot is on the red alliance. */
  public static boolean isRedAlliance() {
    var alliance = DriverStation.getAlliance();
    return alliance.isPresent() && alliance.get() == Alliance.Red;
  }

  /** Flip a Translation2d to the opposite alliance. */
  public static Translation2d flip(Translation2d translation) {
    return flip(translation, isRedAlliance());
  }

  /** Flip a Rotation2d to the opposite alliance (mirror across Y axis). */
  public static Rotation2d flip(Rotation2d rotation) {
    return flip(rotation, isRedAlliance());
  }

  /** Flip a Pose2d to the opposite alliance. */
  public static Pose2d flip(Pose2d pose) {
    return flip(pose, isRedAlliance());
  }

  // ─── Package-private overloads (used by unit tests to avoid HAL dependency) ─

  static Translation2d flip(Translation2d translation, boolean isRed) {
    if (isRed) {
      return new Translation2d(kFieldLengthMeters - translation.getX(), translation.getY());
    }
    return translation;
  }

  static Rotation2d flip(Rotation2d rotation, boolean isRed) {
    if (isRed) {
      return new Rotation2d(Math.PI - rotation.getRadians());
    }
    return rotation;
  }

  static Pose2d flip(Pose2d pose, boolean isRed) {
    if (isRed) {
      return new Pose2d(flip(pose.getTranslation(), true), flip(pose.getRotation(), true));
    }
    return pose;
  }

  /** The field length constant, exposed for test assertions. */
  static double getFieldLengthMeters() {
    return kFieldLengthMeters;
  }
}
