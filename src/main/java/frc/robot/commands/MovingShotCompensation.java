package frc.robot.commands;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;

/**
 * Static utility that computes heading offset to compensate for lateral robot movement while
 * shooting.
 *
 * <p>When the robot is moving sideways relative to the target, the ball inherits that lateral
 * velocity. This utility calculates the heading correction needed so the ball arrives at the target
 * despite the lateral drift.
 */
public final class MovingShotCompensation {

  /** Approximate ball exit velocity from flywheel (m/s). */
  private static final double BALL_EXIT_VELOCITY_MPS = 12.0;

  /** Maximum compensation angle (radians). Clamp to prevent wild corrections. */
  private static final double MAX_COMPENSATION_RAD = Math.toRadians(15.0);

  private MovingShotCompensation() {
    // Utility class — no instantiation.
  }

  /**
   * Compute heading correction for lateral robot movement during a shot.
   *
   * @param robotVelocity current chassis speeds (robot-relative, m/s)
   * @param robotToTarget vector from robot to scoring target (field-relative, meters)
   * @param robotHeading current heading (radians, CCW positive)
   * @return heading offset in radians to add to aim point
   */
  public static double computeCompensation(
      ChassisSpeeds robotVelocity, Translation2d robotToTarget, double robotHeading) {
    // Guard: if target distance is negligible, return 0 to avoid division issues.
    if (robotToTarget.getNorm() < 0.1) {
      return 0.0;
    }

    // Convert robot-relative velocity to field-relative.
    double cos = Math.cos(robotHeading);
    double sin = Math.sin(robotHeading);
    double fieldVx = robotVelocity.vxMetersPerSecond * cos - robotVelocity.vyMetersPerSecond * sin;
    double fieldVy = robotVelocity.vxMetersPerSecond * sin + robotVelocity.vyMetersPerSecond * cos;

    // Unit vector toward target.
    Translation2d targetUnit = robotToTarget.div(robotToTarget.getNorm());

    // Lateral velocity = cross product of velocity with target direction.
    // cross(v, t) = vx * ty - vy * tx
    double lateral = fieldVx * targetUnit.getY() - fieldVy * targetUnit.getX();

    // Compensation angle.
    double compensation = Math.atan(lateral / BALL_EXIT_VELOCITY_MPS);

    return MathUtil.clamp(compensation, -MAX_COMPENSATION_RAD, MAX_COMPENSATION_RAD);
  }
}
