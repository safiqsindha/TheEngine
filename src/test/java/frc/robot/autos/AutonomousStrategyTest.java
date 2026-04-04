package frc.robot.autos;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Tests for AutonomousStrategy utility function. Verifies target ranking based on game state (HUB
 * active/inactive, time remaining, FUEL positions, opponents).
 */
class AutonomousStrategyTest {

  private final AutonomousStrategy strategy = new AutonomousStrategy();

  @Test
  void testHubActive_prefersScoring() {
    // When HUB is active and robot has FUEL, scoring should rank highest
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(3)
            .withHubActive(true)
            .withTimeRemaining(60.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.SCORE,
        targets.get(0).actionType(),
        "Should prefer scoring when HUB is active and holding FUEL");
  }

  @Test
  void testHubInactive_prefersCollecting() {
    // When HUB is inactive, robot should collect FUEL or play defense
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.COLLECT,
        targets.get(0).actionType(),
        "Should prefer collecting when HUB is inactive");
  }

  @Test
  void testLowTimeRemaining_prefersTowerClimb() {
    // With <15 seconds left, TOWER climbing should rank highest
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(true)
            .withTimeRemaining(12.0);
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertEquals(
        ActionType.CLIMB, targets.get(0).actionType(), "Should prefer climbing when time is low");
  }

  @Test
  void testCloserTargetRanksHigher_sameType() {
    // Between two FUEL collection targets, the closer one should rank higher
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0)
            .withDetectedFuel(
                List.of(
                    new Translation2d(5.0, 4.0), // 1m away
                    new Translation2d(10.0, 4.0) // 6m away
                    ));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    // First COLLECT target should be the closer one
    ScoredTarget first =
        targets.stream()
            .filter(t -> t.actionType() == ActionType.COLLECT)
            .findFirst()
            .orElseThrow();
    assertTrue(first.targetPose().getX() < 6.0, "Closer FUEL target should rank higher");
  }

  @Test
  void testContestedTarget_penalized() {
    // A FUEL target near an opponent should have lower utility
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0)
            .withDetectedFuel(
                List.of(
                    new Translation2d(6.0, 4.0), // equidistant from robot
                    new Translation2d(6.0, 6.0) // equidistant from robot
                    ))
            .withDetectedOpponents(
                List.of(
                    new Translation2d(6.5, 4.0) // opponent near first target
                    ));
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    // The uncontested target (6.0, 6.0) should rank higher among COLLECT targets
    List<ScoredTarget> collectTargets =
        targets.stream().filter(t -> t.actionType() == ActionType.COLLECT).toList();
    assertEquals(6.0, collectTargets.get(0).targetPose().getY(), 0.5);
  }

  @Test
  void testBotAborter_abortsWhenOpponentFaster() {
    // If opponent will reach target 0.75s before us, should abort
    double robotDistToTarget = 3.0;
    double robotSpeed = 2.0; // 1.5s to arrive
    double opponentDistToTarget = 1.0;
    double opponentSpeed = 2.0; // 0.5s to arrive — 1.0s faster
    boolean shouldAbort =
        AutonomousStrategy.shouldAbortTarget(
            robotDistToTarget, robotSpeed, opponentDistToTarget, opponentSpeed);
    assertTrue(shouldAbort, "Should abort when opponent arrives 1.0s earlier (> 0.75s threshold)");
  }

  @Test
  void testBotAborter_doesNotAbortWhenRobotFaster() {
    // If robot will arrive first, should not abort
    double robotDistToTarget = 1.0;
    double robotSpeed = 3.0; // 0.33s to arrive
    double opponentDistToTarget = 3.0;
    double opponentSpeed = 2.0; // 1.5s to arrive
    boolean shouldAbort =
        AutonomousStrategy.shouldAbortTarget(
            robotDistToTarget, robotSpeed, opponentDistToTarget, opponentSpeed);
    assertFalse(shouldAbort, "Should not abort when robot arrives first");
  }

  @Test
  void testBotAborter_opponentMovingAway_noAbort() {
    // If opponent is moving away from target, no abort
    double robotDistToTarget = 3.0;
    double robotSpeed = 2.0;
    double opponentDistToTarget = 5.0; // farther than us
    double opponentSpeed = 1.0; // slower
    boolean shouldAbort =
        AutonomousStrategy.shouldAbortTarget(
            robotDistToTarget, robotSpeed, opponentDistToTarget, opponentSpeed);
    assertFalse(shouldAbort);
  }
}
