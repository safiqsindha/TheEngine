package frc.robot.subsystems;

import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import org.littletonrobotics.junction.Logger;

/**
 * Pure state tracker for the robot superstructure. Coordinates the intake → conveyor → flywheel →
 * scoring pipeline without directly commanding motors. Commands read the current state and decide
 * what to do; this class handles state transitions and logging.
 *
 * <p>States:
 *
 * <ul>
 *   <li>{@link State#IDLE} — No game piece, mechanisms at rest.
 *   <li>{@link State#INTAKING} — Intake deployed, wheels spinning; waiting for game piece.
 *   <li>{@link State#STAGING} — Game piece acquired; staging in conveyor for scoring.
 *   <li>{@link State#SCORING} — Flywheel spinning up, feeding, or ejecting.
 *   <li>{@link State#CLIMBING} — Climber extending/retracting; all other mechanisms idle.
 * </ul>
 *
 * <p>Game piece detection uses a current-spike heuristic: when the intake wheel current exceeds
 * {@link Constants.Superstructure#kGamePieceCurrentThresholdAmps}, a game piece is assumed to have
 * been captured and the state advances from INTAKING → STAGING.
 */
public class SuperstructureStateMachine extends SubsystemBase {

  /** Superstructure operating states. */
  public enum State {
    IDLE,
    INTAKING,
    STAGING,
    SCORING,
    CLIMBING
  }

  private final Intake intake;

  private State currentState = State.IDLE;

  // Whether scoring was requested externally (e.g. AutoScoreCommand or driver button)
  private boolean scoreRequested = false;
  // Whether climbing was requested externally
  private boolean climbRequested = false;
  // Whether intake was requested externally
  private boolean intakeRequested = false;

  /**
   * Creates the superstructure state machine.
   *
   * @param intake intake subsystem, used to read wheel current for game piece detection
   */
  public SuperstructureStateMachine(Intake intake) {
    this.intake = intake;
  }

  @Override
  public void periodic() {
    State nextState = computeNextState();
    if (nextState != currentState) {
      Logger.recordOutput("Superstructure/StateTransition", currentState + " → " + nextState);
      currentState = nextState;
    }
    Logger.recordOutput("Superstructure/State", currentState.name());
    Logger.recordOutput("Superstructure/ScoreRequested", scoreRequested);
    Logger.recordOutput("Superstructure/ClimbRequested", climbRequested);
    Logger.recordOutput("Superstructure/IntakeRequested", intakeRequested);
    Logger.recordOutput("Superstructure/IntakeWheelCurrentAmps", intake.getWheelCurrent());
  }

  private State computeNextState() {
    return computeNextState(
        currentState,
        intake.getWheelCurrent(),
        Constants.Superstructure.kGamePieceCurrentThresholdAmps,
        intakeRequested,
        scoreRequested,
        climbRequested);
  }

  /**
   * Pure state transition logic. Package-private and static for unit testing without HAL.
   *
   * @param state current state
   * @param wheelCurrentAmps intake wheel current in amps
   * @param currentThresholdAmps game piece detection threshold in amps
   * @param intakeReq whether intake is requested
   * @param scoreReq whether score is requested
   * @param climbReq whether climb is requested
   * @return the next state
   */
  static State computeNextState(
      State state,
      double wheelCurrentAmps,
      double currentThresholdAmps,
      boolean intakeReq,
      boolean scoreReq,
      boolean climbReq) {
    switch (state) {
      case IDLE:
        if (climbReq) return State.CLIMBING;
        if (intakeReq) return State.INTAKING;
        return State.IDLE;

      case INTAKING:
        if (!intakeReq) return State.IDLE;
        // Game piece detected by current spike → advance to staging
        if (wheelCurrentAmps > currentThresholdAmps) {
          return State.STAGING;
        }
        return State.INTAKING;

      case STAGING:
        if (scoreReq) return State.SCORING;
        // If intake command was cancelled before scoring, return to idle
        if (!intakeReq) return State.IDLE;
        return State.STAGING;

      case SCORING:
        // SCORING exits back to IDLE when the scoring command explicitly calls requestIdle().
        // Commands are responsible for calling requestIdle() after the shot completes.
        return State.SCORING;

      case CLIMBING:
        if (!climbReq) return State.IDLE;
        return State.CLIMBING;

      default:
        return State.IDLE;
    }
  }

  // ─── External request API ─────────────────────────────────────────────────

  /**
   * Request the superstructure to begin intaking. Call continuously while the intake command is
   * running; the state machine will auto-advance to STAGING when a game piece is detected.
   */
  public void requestIntake() {
    intakeRequested = true;
    scoreRequested = false;
    climbRequested = false;
  }

  /**
   * Request the superstructure to score. Transitions from STAGING → SCORING. Has no effect if no
   * game piece has been staged.
   */
  public void requestScore() {
    scoreRequested = true;
  }

  /** Request the superstructure to climb. Transitions any state → CLIMBING. */
  public void requestClimb() {
    climbRequested = true;
    intakeRequested = false;
    scoreRequested = false;
  }

  /**
   * Return all requests to idle. Use this after a scoring sequence completes or when cancelling
   * intake/climb.
   */
  public void requestIdle() {
    intakeRequested = false;
    scoreRequested = false;
    climbRequested = false;
    currentState = State.IDLE;
  }

  // ─── State queries ────────────────────────────────────────────────────────

  /** The current superstructure state. */
  public State getState() {
    return currentState;
  }

  /** Whether the superstructure has a staged game piece ready to score. */
  public boolean hasGamePiece() {
    return currentState == State.STAGING || currentState == State.SCORING;
  }

  /** Whether the superstructure is currently in the scoring sequence. */
  public boolean isScoring() {
    return currentState == State.SCORING;
  }

  /** Whether the superstructure is intaking or staging (intake mechanism active). */
  public boolean isIntaking() {
    return currentState == State.INTAKING || currentState == State.STAGING;
  }
}
