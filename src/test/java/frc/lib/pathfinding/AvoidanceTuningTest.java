package frc.lib.pathfinding;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.Test;

/**
 * Block 3.11: Avoidance tuning verification. Runs simulated autonomous cycles with opponent
 * injection and verifies the potential-field avoidance layer keeps the robot clear of opponents.
 *
 * <p>The test simulates a robot driving toward a waypoint while opponents are placed in the path.
 * Each simulation "tick" (20ms) computes the avoidance velocity and integrates the robot position.
 * A collision is any tick where robot-to-opponent distance drops below the collision threshold
 * (0.50m = approximate robot half-width).
 */
class AvoidanceTuningTest {

  private static final double DT = 0.02; // 20ms sim tick
  private static final double COLLISION_RADIUS_M = 0.50; // robot half-width
  private static final double SIM_DURATION_S = 10.0; // max sim time per cycle
  private static final int TICKS = (int) (SIM_DURATION_S / DT);

  private final DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();

  /**
   * Simulate one autonomous cycle: robot drives from start toward waypoint, opponents are placed
   * along the path. Returns the minimum distance to any opponent during the run.
   */
  private double simulateCycle(
      Translation2d start, Translation2d waypoint, List<Translation2d> opponents) {
    double x = start.getX();
    double y = start.getY();
    double minDist = Double.MAX_VALUE;

    for (int t = 0; t < TICKS; t++) {
      Pose2d robotPose = new Pose2d(x, y, new Rotation2d());
      Translation2d vel = layer.computeCorrectedVelocity(robotPose, waypoint, opponents);

      // Check collision distance
      for (Translation2d opp : opponents) {
        double dist = new Translation2d(x, y).getDistance(opp);
        minDist = Math.min(minDist, dist);
      }

      // Integrate position
      x += vel.getX() * DT;
      y += vel.getY() * DT;

      // Stop if we reached the waypoint
      if (new Translation2d(x, y).getDistance(waypoint) < 0.3) {
        break;
      }
    }
    return minDist;
  }

  @Test
  void singleOpponentBlockingPath_noCollision() {
    // Opponent directly between robot and waypoint
    Translation2d start = new Translation2d(2.0, 4.0);
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    List<Translation2d> opponents = List.of(new Translation2d(4.0, 4.0));

    double minDist = simulateCycle(start, waypoint, opponents);
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format(
            "Robot collided! Min distance %.3fm < collision radius %.2fm",
            minDist, COLLISION_RADIUS_M));
  }

  @Test
  void twoOpponentsGauntlet_noCollision() {
    // Two opponents creating a narrow gap
    Translation2d start = new Translation2d(2.0, 4.0);
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    List<Translation2d> opponents =
        List.of(new Translation2d(4.0, 4.8), new Translation2d(4.0, 3.2));

    double minDist = simulateCycle(start, waypoint, opponents);
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format("Robot collided in gauntlet! Min distance %.3fm", minDist));
  }

  @Test
  void opponentSlightlyOffPath_deflects() {
    // Opponent 0.5m off the direct path — robot should deflect around
    Translation2d start = new Translation2d(2.0, 4.0);
    Translation2d waypoint = new Translation2d(7.0, 4.0);
    List<Translation2d> opponents = List.of(new Translation2d(4.5, 4.5));

    double minDist = simulateCycle(start, waypoint, opponents);
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format("Robot collided with offset opponent! Min distance %.3fm", minDist));
  }

  @Test
  void threeOpponentScatter_noCollision() {
    // Three opponents scattered along the path
    Translation2d start = new Translation2d(1.0, 4.0);
    Translation2d waypoint = new Translation2d(8.0, 4.0);
    List<Translation2d> opponents =
        List.of(
            new Translation2d(3.0, 4.2), new Translation2d(5.0, 3.8), new Translation2d(6.5, 4.5));

    double minDist = simulateCycle(start, waypoint, opponents);
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format("Robot collided in scatter! Min distance %.3fm", minDist));
  }

  @RepeatedTest(10)
  void randomizedOpponents_noCollision() {
    // Random opponent placement along the path — repeated 10 times for statistical coverage
    Random rng = new Random();
    Translation2d start = new Translation2d(2.0, 4.0);
    Translation2d waypoint = new Translation2d(8.0, 4.0);

    // Place 1-3 opponents in the path corridor
    int numOpponents = rng.nextInt(3) + 1;
    List<Translation2d> opponents = new ArrayList<>();
    for (int i = 0; i < numOpponents; i++) {
      double ox = 3.0 + rng.nextDouble() * 4.0; // X between 3 and 7
      double oy = 3.0 + rng.nextDouble() * 2.0; // Y between 3 and 5 (path corridor)
      opponents.add(new Translation2d(ox, oy));
    }

    double minDist = simulateCycle(start, waypoint, opponents);
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format(
            "Robot collided with random opponents! Min distance %.3fm, opponents: %s",
            minDist, opponents));
  }

  @Test
  void opponentAtWaypoint_abortOrAvoid() {
    // Opponent sitting directly at the waypoint — robot should at minimum not collide
    Translation2d start = new Translation2d(2.0, 4.0);
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    List<Translation2d> opponents = List.of(new Translation2d(6.0, 4.0));

    double minDist = simulateCycle(start, waypoint, opponents);
    // With opponent AT the waypoint, the attractive and repulsive forces create an equilibrium.
    // The robot should not drive directly into the opponent.
    assertTrue(
        minDist >= COLLISION_RADIUS_M,
        String.format("Robot drove into opponent at waypoint! Min distance %.3fm", minDist));
  }
}
