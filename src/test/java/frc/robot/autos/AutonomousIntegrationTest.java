package frc.robot.autos;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Integration tests for the full decision pipeline: GameState -> AutonomousStrategy ->
 * ScoredTarget. Verifies end-to-end target ranking under various game scenarios.
 */
class AutonomousIntegrationTest {

  private final AutonomousStrategy strategy = new AutonomousStrategy();

  // Hardcoded from Constants.Pathfinding (do NOT import Constants)
  private static final double CLIMB_TIME_THRESHOLD_SECONDS = 15.0;

  @Test
  void emptyField_noFuel_hubActive_returnsTargets() {
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(2.0, 2.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(true)
            .withTimeRemaining(60.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertFalse(targets.isEmpty(), "Should return at least one target even with empty field");
    // With no fuel held and hub active, SCORE should not appear (requires fuelHeld > 0).
    // Should fall back to default COLLECT.
    assertNotNull(targets.get(0).actionType());
  }

  @Test
  void holdingFuel_hubActive_closeToHub_scoreIsHighest() {
    // HUB is at (3.39, 4.11); place robot close to it
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(3.5, 4.0, new Rotation2d()))
            .withFuelHeld(1)
            .withHubActive(true)
            .withTimeRemaining(60.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.SCORE, targets.get(0).actionType(), "SCORE should be highest when close to hub");
  }

  @Test
  void fifteenSecondsRemaining_robotNearTower_climbDominates() {
    // CLIMB pose is at (8.23, 4.11); place robot near it
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(8.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(true)
            .withTimeRemaining(CLIMB_TIME_THRESHOLD_SECONDS);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.CLIMB,
        targets.get(0).actionType(),
        "CLIMB should dominate with 15s remaining near tower");
  }

  @Test
  void fifteenSecondsRemaining_robotFarFromTower_climbStillChosen() {
    // Robot far from tower but time is low — climb still has utility 100 - dist
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(1.0, 1.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(CLIMB_TIME_THRESHOLD_SECONDS);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.CLIMB,
        targets.get(0).actionType(),
        "CLIMB should still be chosen even when far from tower");
  }

  @Test
  void twoFuelDetected_notHolding_collectChosen_nearestPreferred() {
    Translation2d closeFuel = new Translation2d(5.0, 3.0);
    Translation2d farFuel = new Translation2d(8.0, 4.0);
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 3.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0)
            .withDetectedFuel(List.of(closeFuel, farFuel));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.COLLECT, targets.get(0).actionType(), "COLLECT should be chosen with no fuel");
    // The first COLLECT target should be nearer
    List<ScoredTarget> collectTargets =
        targets.stream().filter(t -> t.actionType() == ActionType.COLLECT).toList();
    assertTrue(
        collectTargets.get(0).targetPose().getX() < collectTargets.get(1).targetPose().getX(),
        "Nearest fuel should be ranked higher");
  }

  @Test
  void hubNotActive_holdingFuel_scoreNotTop() {
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(3.5, 4.0, new Rotation2d()))
            .withFuelHeld(3)
            .withHubActive(false)
            .withTimeRemaining(60.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    // SCORE requires hubActive — should not appear at all
    boolean hasScore = targets.stream().anyMatch(t -> t.actionType() == ActionType.SCORE);
    assertFalse(hasScore, "SCORE should not appear when hub is inactive");
  }

  @Test
  void zeroSecondsRemaining_climbAtMaxUrgency() {
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(8.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(0.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.CLIMB,
        targets.get(0).actionType(),
        "CLIMB should be top at 0 seconds remaining");
    // Utility should be very high (100 - small distance)
    assertTrue(targets.get(0).utility() > 90.0, "CLIMB utility should be near 100 when close");
  }

  @Test
  void multipleTargets_holdingFuel_hubActive_plentyOfTime_scoreIsTop() {
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(1)
            .withHubActive(true)
            .withTimeRemaining(45.0)
            .withDetectedFuel(
                List.of(
                    new Translation2d(6.0, 3.0),
                    new Translation2d(7.0, 5.0),
                    new Translation2d(9.0, 2.0)));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.SCORE,
        targets.get(0).actionType(),
        "SCORE should be top with fuel held, hub active, 45s left");
  }

  @Test
  void evaluateTargets_returnsSortedByUtilityDescending() {
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(1)
            .withHubActive(true)
            .withTimeRemaining(10.0) // triggers CLIMB too
            .withDetectedFuel(List.of(new Translation2d(6.0, 3.0), new Translation2d(9.0, 2.0)));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertTrue(targets.size() >= 2, "Should have multiple targets");
    for (int i = 0; i < targets.size() - 1; i++) {
      assertTrue(
          targets.get(i).utility() >= targets.get(i + 1).utility(),
          "Targets should be sorted by utility descending at index " + i);
    }
  }

  @Test
  void allTargetsFarAway_utilitiesLowerButStillReturnsTargets() {
    // Robot at origin, fuel >10m away
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(0.0, 0.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0)
            .withDetectedFuel(List.of(new Translation2d(12.0, 8.0), new Translation2d(14.0, 6.0)));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertFalse(targets.isEmpty(), "Should still return targets even when all are far away");
    // Utilities should be lower (20 - dist where dist > 10)
    for (ScoredTarget t : targets) {
      if (t.actionType() == ActionType.COLLECT) {
        assertTrue(t.utility() < 10.0, "Far targets should have low utility");
      }
    }
  }
}
