package frc.lib.pathfinding;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Tests for DynamicAvoidanceLayer. Verifies potential field force vector calculations for opponent
 * avoidance during autonomous.
 */
class DynamicAvoidanceLayerTest {

  private static final double DELTA = 0.01;

  @Test
  void testNoOpponents_outputEqualsAttractiveForce() {
    // With no opponents, corrected velocity should point directly at waypoint
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    List<Translation2d> opponents = List.of();
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    assertTrue(result.getX() > 0, "Should point toward waypoint (positive X)");
    assertEquals(0.0, result.getY(), DELTA, "No Y component when waypoint is directly ahead");
  }

  @Test
  void testOpponentAhead_deflectsAround() {
    // Opponent close ahead and slightly off-axis deflects the velocity vector
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(7.0, 4.0);
    // Opponent at (4.5, 4.3): ~1.53m from robot, within 2.0m influence, slightly above path
    List<Translation2d> opponents = List.of(new Translation2d(4.5, 4.3));
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    assertTrue(result.getX() > 0, "Should still generally point toward waypoint");
    assertNotEquals(0.0, result.getY(), "Should have Y deflection to avoid opponent");
  }

  @Test
  void testOpponentOutsideInfluenceRadius_noEffect() {
    // Opponent at 5m away (beyond 2.0m default influence) should not affect velocity
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    List<Translation2d> opponents = List.of(new Translation2d(3.0, 9.0)); // 5m away
    Translation2d withOpponent = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    Translation2d without = layer.computeCorrectedVelocity(robot, waypoint, List.of());
    assertEquals(without.getX(), withOpponent.getX(), DELTA);
    assertEquals(without.getY(), withOpponent.getY(), DELTA);
  }

  @Test
  void testOpponentAtInfluenceBoundary_minimalEffect() {
    // Opponent exactly at influence radius boundary (2.0m) should have zero repulsive force
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    Translation2d opponent = new Translation2d(3.0, 6.0); // exactly 2.0m away (straight up)
    List<Translation2d> opponents = List.of(opponent);
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    // At boundary, linear formula gives zero repulsion — deflection must be minimal
    assertTrue(Math.abs(result.getY()) < 0.5, "Minimal deflection at influence boundary");
  }

  @Test
  void testTwoOpponentsFlanking_noOscillation() {
    // Two opponents equidistant above and below path cancel Y forces; robot still moves forward
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(7.0, 4.0);
    // Each opponent at ~1.80m from robot, symmetric above and below
    List<Translation2d> opponents =
        List.of(
            new Translation2d(4.5, 5.0), // 1m above path
            new Translation2d(4.5, 3.0) // 1m below path
            );
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    assertTrue(result.getX() > 0, "Should still move forward");
    assertEquals(0.0, result.getY(), 0.1, "Symmetric opponents should cancel Y forces");
  }

  @Test
  void testOutputIsNormalized_doesNotExceedMaxSpeed() {
    // Output velocity magnitude should never exceed max robot speed (4.5 m/s)
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(15.0, 4.0); // far = strong attraction
    // Opponent at 0.5m directly ahead = maximum repulsion
    List<Translation2d> opponents = List.of(new Translation2d(3.5, 4.0));
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    double magnitude = result.getNorm();
    assertTrue(magnitude <= 4.5 + DELTA, "Velocity should not exceed max speed (4.5 m/s)");
  }

  @Test
  void testVeryCloseOpponent_strongRepulsion() {
    // Opponent 0.4m above the robot should produce strong Y deflection
    DynamicAvoidanceLayer layer = new DynamicAvoidanceLayer();
    Pose2d robot = new Pose2d(3.0, 4.0, new Rotation2d());
    Translation2d waypoint = new Translation2d(6.0, 4.0);
    // Opponent directly above: repulsive force is entirely in -Y direction
    List<Translation2d> opponents = List.of(new Translation2d(3.0, 4.4));
    Translation2d result = layer.computeCorrectedVelocity(robot, waypoint, opponents);
    double yDeflection = Math.abs(result.getY());
    assertTrue(yDeflection > 1.0, "Close opponent should cause strong Y deflection");
  }
}
