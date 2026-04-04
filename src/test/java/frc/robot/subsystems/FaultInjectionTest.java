package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import frc.robot.autos.AutonomousStrategy;
import frc.robot.autos.GameState;
import frc.robot.autos.ScoredTarget;
import frc.robot.subsystems.SuperstructureStateMachine.State;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Fault injection tests for graceful degradation. Feeds garbage, boundary, and adversarial input to
 * subsystems and verifies no exceptions are thrown and safe defaults are returned.
 */
class FaultInjectionTest {

  // Hardcoded from Constants.Superstructure (do NOT import Constants)
  private static final double THRESHOLD = 15.0;

  private static State next(
      State state, double current, boolean intake, boolean score, boolean climb) {
    return SuperstructureStateMachine.computeNextState(
        state, current, THRESHOLD, intake, score, climb);
  }

  // ── FuelDetectionConsumer fault injection ──────────────────────────────────

  @Test
  void fuelConsumer_nullArray_noCrash_emptyPositions() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    assertDoesNotThrow(() -> consumer.updateFromRawArray(null));
    assertTrue(
        consumer.getDetectedFuelPositions().isEmpty(),
        "Null array should produce empty detections");
  }

  @Test
  void fuelConsumer_emptyArray_noCrash() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    assertDoesNotThrow(() -> consumer.updateFromRawArray(new double[0]));
    assertTrue(
        consumer.getDetectedFuelPositions().isEmpty(),
        "Empty array should produce empty detections");
  }

  @Test
  void fuelConsumer_hugeNumFuel_shortArray_noCrash() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    // Claims 999999 fuel but array is only 1 element
    double[] raw = {999999.0};
    assertDoesNotThrow(() -> consumer.updateFromRawArray(raw));
    assertTrue(
        consumer.getDetectedFuelPositions().isEmpty(),
        "Truncated array should produce empty detections");
  }

  @Test
  void fuelConsumer_nanConfidence_filteredOut() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    // NaN confidence should not satisfy >= 0.80 threshold
    double[] raw = {1.0, 5.0, 3.0, Double.NaN};
    for (int i = 0; i < 3; i++) {
      assertDoesNotThrow(() -> consumer.updateFromRawArray(raw));
    }
    assertTrue(
        consumer.getDetectedFuelPositions().isEmpty(), "NaN confidence should be filtered out");
  }

  @Test
  void fuelConsumer_negativeCoords_stillParses() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    // Negative coordinates are a valid edge case (could be off-field)
    double[] raw = {1.0, -2.0, -3.0, 0.95};
    for (int i = 0; i < 3; i++) {
      consumer.updateFromRawArray(raw);
    }
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(1, detections.size(), "Negative coords should still be parsed");
    assertEquals(-2.0, detections.get(0).getX(), 0.01);
    assertEquals(-3.0, detections.get(0).getY(), 0.01);
  }

  @Test
  void fuelConsumer_missingConfidence_noCrash() {
    FuelDetectionConsumer consumer = new FuelDetectionConsumer();
    // Claims 1 fuel but only has x,y (missing confidence) — array too short
    double[] raw = {1.0, 5.0, 3.0};
    assertDoesNotThrow(() -> consumer.updateFromRawArray(raw));
    assertTrue(
        consumer.getDetectedFuelPositions().isEmpty(),
        "Incomplete triplet should produce empty detections");
  }

  // ── SuperstructureStateMachine fault injection ─────────────────────────────

  @Test
  void stateMachine_rapidCycling_1000Times_alwaysValidState() {
    State state = State.IDLE;
    for (int i = 0; i < 1000; i++) {
      boolean intake = (i % 3 == 0);
      boolean score = (i % 5 == 0);
      boolean climb = (i % 7 == 0);
      double current = (i % 11 == 0) ? THRESHOLD + 10.0 : 0.0;
      state =
          SuperstructureStateMachine.computeNextState(
              state, current, THRESHOLD, intake, score, climb);
      assertNotNull(state, "State should never be null at iteration " + i);
      // Verify it is one of the known enum values
      assertTrue(
          state == State.IDLE
              || state == State.INTAKING
              || state == State.STAGING
              || state == State.SCORING
              || state == State.CLIMBING,
          "State should be a known enum value at iteration " + i);
    }
  }

  @Test
  void stateMachine_doubleRequestScore_noIllegalState() {
    // IDLE -> INTAKING -> STAGING -> SCORING (first score) -> SCORING (second score, no crash)
    State state = next(State.IDLE, 0.0, true, false, false);
    assertEquals(State.INTAKING, state);

    state = next(state, THRESHOLD + 10.0, true, false, false);
    assertEquals(State.STAGING, state);

    state = next(state, 0.0, true, true, false);
    assertEquals(State.SCORING, state);

    // Second score request while already scoring — should stay in SCORING
    state = next(state, 0.0, true, true, false);
    assertEquals(State.SCORING, state, "Double score request should not cause illegal state");
  }

  // ── GameState fault injection ──────────────────────────────────────────────

  @Test
  void gameState_extremeValues_buildsWithoutCrash() {
    assertDoesNotThrow(
        () -> {
          GameState state =
              new GameState()
                  .withRobotPose(new Pose2d(-999.0, -999.0, new Rotation2d()))
                  .withFuelHeld(999)
                  .withHubActive(true)
                  .withTimeRemaining(-999.0)
                  .withDetectedFuel(List.of())
                  .withDetectedOpponents(List.of());
          assertNotNull(state);
          assertEquals(999, state.getFuelHeld());
          assertEquals(-999.0, state.getTimeRemaining(), 0.01);
        });
  }

  // ── AutonomousStrategy fault injection ─────────────────────────────────────

  @Test
  void strategy_emptyDetections_returnsTargetsNotNull() {
    AutonomousStrategy strategy = new AutonomousStrategy();
    GameState state =
        new GameState()
            .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
            .withFuelHeld(0)
            .withHubActive(false)
            .withTimeRemaining(60.0)
            .withDetectedFuel(List.of());
    List<ScoredTarget> targets = strategy.evaluateTargets(state);
    assertNotNull(targets, "evaluateTargets should never return null");
    assertFalse(targets.isEmpty(), "Should return fallback target even with no detections");
  }
}
