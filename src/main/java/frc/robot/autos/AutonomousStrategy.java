package frc.robot.autos;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import frc.robot.Constants;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Decision engine that evaluates candidate autonomous targets and ranks them by utility.
 *
 * <p>Scoring factors:
 *
 * <ul>
 *   <li><b>Action priority:</b> CLIMB overrides everything when time is low; SCORE beats COLLECT
 *       when HUB is active and robot holds FUEL.
 *   <li><b>Distance:</b> closer targets score higher (inverse-distance weighting).
 *   <li><b>Opponent penalty:</b> targets near detected opponents are penalized.
 * </ul>
 *
 * <p>Also provides the <b>Bot Aborter</b> — a static check that aborts a target if an opponent will
 * arrive {@link Constants.Pathfinding#kAbortTimeThresholdSeconds} before the robot.
 */
public final class AutonomousStrategy {

  // Fixed field locations (blue alliance; flip for red in the caller)
  private static final Pose2d HUB_POSE = new Pose2d(3.39, 4.11, new Rotation2d());
  private static final Pose2d CLIMB_POSE = new Pose2d(8.23, 4.11, new Rotation2d());

  /**
   * Evaluate all candidate targets given the current game state and return them ranked by utility
   * (highest first).
   *
   * @param state current game snapshot
   * @return scored targets sorted descending by utility; never null, may be empty
   */
  public List<ScoredTarget> evaluateTargets(GameState state) {
    List<ScoredTarget> targets = new ArrayList<>();
    Translation2d robotPos = state.getRobotPose().getTranslation();

    // ── CLIMB — dominates when time is low ──
    if (state.getTimeRemaining() <= Constants.Pathfinding.kClimbTimeThresholdSeconds) {
      double dist = robotPos.getDistance(CLIMB_POSE.getTranslation());
      // High base utility; still distance-weighted so nearer is better
      double utility = 100.0 - dist;
      targets.add(new ScoredTarget(ActionType.CLIMB, CLIMB_POSE, utility));
    }

    // ── SCORE — when HUB is active and robot holds FUEL ──
    if (state.isHubActive() && state.getFuelHeld() > 0) {
      double dist = robotPos.getDistance(HUB_POSE.getTranslation());
      // Base utility 50 + fuel bonus; penalize by distance
      double utility = 50.0 + state.getFuelHeld() * 5.0 - dist;
      targets.add(new ScoredTarget(ActionType.SCORE, HUB_POSE, utility));
    }

    // ── COLLECT — one target per detected FUEL position ──
    for (Translation2d fuelPos : state.getDetectedFuel()) {
      double dist = robotPos.getDistance(fuelPos);
      // Base utility 20; penalize by distance and opponent proximity
      double utility = 20.0 - dist;
      utility -= opponentPenalty(fuelPos, state.getDetectedOpponents());
      Pose2d collectPose = new Pose2d(fuelPos, new Rotation2d());
      targets.add(new ScoredTarget(ActionType.COLLECT, collectPose, utility));
    }

    // If nothing else, still offer COLLECT at default field positions
    if (targets.isEmpty()) {
      targets.add(
          new ScoredTarget(ActionType.COLLECT, new Pose2d(8.23, 4.11, new Rotation2d()), 0.0));
    }

    targets.sort(Comparator.comparingDouble(ScoredTarget::utility).reversed());
    return targets;
  }

  /**
   * Bot Aborter — returns true if the opponent will reach the target before the robot by at least
   * {@link Constants.Pathfinding#kAbortTimeThresholdSeconds}.
   *
   * @param robotDist robot's distance to target (meters)
   * @param robotSpeed robot's current speed (m/s)
   * @param opponentDist opponent's distance to target (meters)
   * @param opponentSpeed opponent's estimated speed (m/s)
   * @return true if the robot should abort this target
   */
  public static boolean shouldAbortTarget(
      double robotDist, double robotSpeed, double opponentDist, double opponentSpeed) {
    if (robotSpeed <= 0) return true; // can't reach if not moving
    if (opponentSpeed <= 0) return false; // opponent stationary — no threat

    double robotEta = robotDist / robotSpeed;
    double opponentEta = opponentDist / opponentSpeed;
    return (robotEta - opponentEta) >= Constants.Pathfinding.kAbortTimeThresholdSeconds;
  }

  // ---- private helpers ----

  /**
   * Compute opponent proximity penalty for a target position. Targets near opponents are penalized
   * proportionally to how close the nearest opponent is.
   */
  private static double opponentPenalty(Translation2d targetPos, List<Translation2d> opponents) {
    double penalty = 0.0;
    for (Translation2d opp : opponents) {
      double dist = targetPos.getDistance(opp);
      if (dist < Constants.Pathfinding.kOpponentInfluenceRadiusMeters) {
        // Penalty increases as opponent gets closer (inverse relationship)
        penalty +=
            (Constants.Pathfinding.kOpponentInfluenceRadiusMeters - dist)
                * Constants.Pathfinding.kRepulsiveGain;
      }
    }
    return penalty;
  }
}
