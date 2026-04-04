package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import frc.robot.subsystems.SuperstructureStateMachine.State;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link SuperstructureStateMachine}. Exercises the static pure state-transition function
 * {@code computeNextState(State, double, double, boolean, boolean, boolean)} directly, bypassing
 * HAL and hardware dependencies.
 */
class SuperstructureStateMachineTest {

  /** Game piece current threshold (amps) — must match Constants.Superstructure value. */
  private static final double THRESHOLD = 15.0;

  // Shorthand for the static transition function
  private static State next(
      State state, double current, boolean intake, boolean score, boolean climb) {
    return SuperstructureStateMachine.computeNextState(
        state, current, THRESHOLD, intake, score, climb);
  }

  // ── IDLE state transitions ──────────────────────────────────────────────

  @Test
  void idle_staysIdleWithNoRequests() {
    assertEquals(State.IDLE, next(State.IDLE, 0.0, false, false, false));
  }

  @Test
  void idle_transitionsToIntakingOnRequest() {
    assertEquals(State.INTAKING, next(State.IDLE, 0.0, true, false, false));
  }

  @Test
  void idle_transitionsToClimbingOnRequest() {
    assertEquals(State.CLIMBING, next(State.IDLE, 0.0, false, false, true));
  }

  @Test
  void idle_climbTakesPriorityOverIntake() {
    assertEquals(State.CLIMBING, next(State.IDLE, 0.0, true, false, true));
  }

  // ── INTAKING state transitions ──────────────────────────────────────────

  @Test
  void intaking_staysIntakingBelowCurrentThreshold() {
    assertEquals(State.INTAKING, next(State.INTAKING, THRESHOLD - 1.0, true, false, false));
  }

  @Test
  void intaking_transitionsToStagingOnCurrentSpike() {
    assertEquals(State.STAGING, next(State.INTAKING, THRESHOLD + 5.0, true, false, false));
  }

  @Test
  void intaking_returnsToIdleWhenIntakeCancelled() {
    assertEquals(State.IDLE, next(State.INTAKING, 0.0, false, false, false));
  }

  @Test
  void intaking_exactThresholdDoesNotTrigger() {
    // Must exceed threshold, not equal
    assertEquals(State.INTAKING, next(State.INTAKING, THRESHOLD, true, false, false));
  }

  @Test
  void intaking_cancelsEvenWithHighCurrent() {
    // If intake is cancelled, goes to IDLE regardless of current
    assertEquals(State.IDLE, next(State.INTAKING, THRESHOLD + 20.0, false, false, false));
  }

  // ── STAGING state transitions ──────────────────────────────────────────

  @Test
  void staging_staysStagingWithIntakeActive() {
    assertEquals(State.STAGING, next(State.STAGING, 0.0, true, false, false));
  }

  @Test
  void staging_transitionsToScoringOnScoreRequest() {
    assertEquals(State.SCORING, next(State.STAGING, 0.0, true, true, false));
  }

  @Test
  void staging_returnsToIdleWhenIntakeCancelled() {
    assertEquals(State.IDLE, next(State.STAGING, 0.0, false, false, false));
  }

  @Test
  void staging_scoreWithoutIntakeStillScores() {
    // scoreRequested takes priority check before intakeRequested check
    assertEquals(State.SCORING, next(State.STAGING, 0.0, false, true, false));
  }

  // ── SCORING state transitions ──────────────────────────────────────────

  @Test
  void scoring_staysScoringRegardlessOfFlags() {
    assertEquals(State.SCORING, next(State.SCORING, 0.0, false, false, false));
    assertEquals(State.SCORING, next(State.SCORING, 0.0, true, true, true));
  }

  // ── CLIMBING state transitions ──────────────────────────────────────────

  @Test
  void climbing_staysClimbingWhileRequested() {
    assertEquals(State.CLIMBING, next(State.CLIMBING, 0.0, false, false, true));
  }

  @Test
  void climbing_returnsToIdleWhenCancelled() {
    assertEquals(State.IDLE, next(State.CLIMBING, 0.0, false, false, false));
  }

  // ── Full lifecycle: IDLE → INTAKING → STAGING → SCORING ───────────────

  @Test
  void fullScoringLifecycle() {
    // IDLE → INTAKING (intake requested)
    assertEquals(State.INTAKING, next(State.IDLE, 0.0, true, false, false));

    // INTAKING → STAGING (current spike)
    assertEquals(State.STAGING, next(State.INTAKING, THRESHOLD + 10.0, true, false, false));

    // STAGING → SCORING (score requested)
    assertEquals(State.SCORING, next(State.STAGING, 0.0, true, true, false));

    // SCORING stays (until requestIdle called externally)
    assertEquals(State.SCORING, next(State.SCORING, 0.0, false, false, false));
  }

  // ── Full lifecycle: IDLE → CLIMBING → IDLE ─────────────────────────────

  @Test
  void climbingLifecycle() {
    assertEquals(State.CLIMBING, next(State.IDLE, 0.0, false, false, true));
    assertEquals(State.CLIMBING, next(State.CLIMBING, 0.0, false, false, true));
    assertEquals(State.IDLE, next(State.CLIMBING, 0.0, false, false, false));
  }

  // ── Edge cases ─────────────────────────────────────────────────────────

  @Test
  void negativeCurrent_doesNotTriggerStaging() {
    assertEquals(State.INTAKING, next(State.INTAKING, -5.0, true, false, false));
  }

  @Test
  void zeroCurrent_doesNotTriggerStaging() {
    assertEquals(State.INTAKING, next(State.INTAKING, 0.0, true, false, false));
  }

  @Test
  void allFlagsTrue_idleGoesToClimbing() {
    // Climb has highest priority in IDLE state
    assertEquals(State.CLIMBING, next(State.IDLE, 0.0, true, true, true));
  }
}
