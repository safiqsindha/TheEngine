package frc.lib.pathfinding;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Translation2d;
import frc.robot.Constants;
import java.util.List;

/**
 * Artificial potential-field layer for dynamic opponent avoidance.
 *
 * <p>Computes a corrected velocity vector each loop cycle by summing:
 *
 * <ul>
 *   <li><b>Attractive force</b> — points from the robot toward the next waypoint, magnitude =
 *       {@link Constants.Pathfinding#kAttractiveGain} × {@link
 *       Constants.Pathfinding#kMaxRobotSpeedMps}.
 *   <li><b>Repulsive force</b> — for each opponent within {@link
 *       Constants.Pathfinding#kOpponentInfluenceRadiusMeters}, a force pointing away from the
 *       opponent, linearly scaled from zero at the boundary to max at dist→0.
 * </ul>
 *
 * <p>The resulting vector is capped at {@link Constants.Pathfinding#kMaxRobotSpeedMps} so that the
 * output can be passed directly to {@link frc.robot.subsystems.SwerveSubsystem#driveRobotRelative}
 * (after a Pose2d→ChassisSpeeds conversion in the caller).
 *
 * <p>This layer does not replace PPLib path-following; it is called inside {@code
 * FullAutonomousCommand} to nudge the target velocity when an opponent enters the influence radius.
 */
public final class DynamicAvoidanceLayer {

  /**
   * Compute a corrected field-relative velocity vector.
   *
   * @param robotPose current robot pose (field-relative)
   * @param waypoint next path waypoint to drive toward (field-relative, meters)
   * @param opponents list of detected opponent positions (field-relative, meters)
   * @return corrected velocity vector (m/s, field-relative), magnitude ≤ {@link
   *     Constants.Pathfinding#kMaxRobotSpeedMps}
   */
  public Translation2d computeCorrectedVelocity(
      Pose2d robotPose, Translation2d waypoint, List<Translation2d> opponents) {

    Translation2d robotPos = robotPose.getTranslation();
    double maxSpeed = Constants.Pathfinding.kMaxRobotSpeedMps;

    // ── Attractive force ──────────────────────────────────────────────────────
    Translation2d toWaypoint = waypoint.minus(robotPos);
    double waypointDist = toWaypoint.getNorm();

    double attrX = 0;
    double attrY = 0;
    if (waypointDist > 1e-6) {
      double scale = maxSpeed * Constants.Pathfinding.kAttractiveGain / waypointDist;
      attrX = toWaypoint.getX() * scale;
      attrY = toWaypoint.getY() * scale;
    }

    // ── Repulsive forces ──────────────────────────────────────────────────────
    double repX = 0;
    double repY = 0;
    for (Translation2d opp : opponents) {
      Translation2d fromOpp = robotPos.minus(opp);
      double dist = fromOpp.getNorm();
      if (dist > 1e-6 && dist < Constants.Pathfinding.kOpponentInfluenceRadiusMeters) {
        // Linear falloff: full strength at dist→0, zero at the influence boundary
        double magnitude =
            Constants.Pathfinding.kRepulsiveGain
                * (Constants.Pathfinding.kOpponentInfluenceRadiusMeters - dist)
                / Constants.Pathfinding.kOpponentInfluenceRadiusMeters
                * maxSpeed;
        repX += (fromOpp.getX() / dist) * magnitude;
        repY += (fromOpp.getY() / dist) * magnitude;
      }
    }

    // ── Sum and cap ───────────────────────────────────────────────────────────
    double totalX = attrX + repX;
    double totalY = attrY + repY;
    double totalMag = Math.sqrt(totalX * totalX + totalY * totalY);

    if (totalMag > maxSpeed) {
      double scale = maxSpeed / totalMag;
      totalX *= scale;
      totalY *= scale;
    }

    return new Translation2d(totalX, totalY);
  }
}
