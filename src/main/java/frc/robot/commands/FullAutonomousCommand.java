package frc.robot.commands;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.Command;
import frc.lib.pathfinding.DynamicAvoidanceLayer;
import frc.lib.pathfinding.NavigationGrid;
import frc.robot.Constants;
import frc.robot.autos.AutonomousStrategy;
import frc.robot.autos.GameState;
import frc.robot.autos.ScoredTarget;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;
import org.littletonrobotics.junction.Logger;

/**
 * Top-level autonomous loop: evaluate → pathfind → execute → repeat.
 *
 * <p>Each cycle:
 *
 * <ol>
 *   <li>{@link AutonomousStrategy#evaluateTargets(GameState)} ranks candidates.
 *   <li>Best target becomes the current goal; a {@link PathfindToGoalCommand} drives there.
 *   <li>On arrival (or abort), the SSM is notified and the loop re-evaluates.
 * </ol>
 *
 * <p>Integrates three reactive layers:
 *
 * <ul>
 *   <li><b>DynamicAvoidanceLayer</b> — potential-field velocity correction when opponents are near.
 *   <li><b>Bot Aborter</b> — aborts current target if an opponent will arrive {@link
 *       Constants.Pathfinding#kAbortTimeThresholdSeconds} before the robot.
 *   <li><b>NavigationGrid dynamic obstacles</b> — opponent positions are injected as temporary
 *       obstacles each cycle so PPLib's AD* re-plans around them.
 * </ul>
 */
public class FullAutonomousCommand extends Command {

  private final SwerveSubsystem swerve;
  private final SuperstructureStateMachine ssm;
  private final AutonomousStrategy strategy;
  private final DynamicAvoidanceLayer avoidanceLayer;
  private final NavigationGrid navGrid;
  private final Supplier<List<Translation2d>> fuelSupplier;
  private final Supplier<List<Translation2d>> opponentSupplier;

  private Command activePathCommand;
  private ScoredTarget currentTarget;
  private final Timer cycleTimer = new Timer();

  /** Half-width of the dynamic obstacle box stamped per opponent (meters). */
  private static final double OPPONENT_OBSTACLE_HALF_SIZE = 0.50;

  /**
   * Full constructor with all reactive layers.
   *
   * @param swerve swerve subsystem
   * @param ssm superstructure state machine
   * @param strategy decision engine
   * @param avoidanceLayer potential-field opponent avoidance
   * @param navGrid navigation grid for dynamic obstacle injection (may be null to skip)
   * @param fuelSupplier supplier of detected FUEL positions (from FuelDetectionConsumer)
   * @param opponentSupplier supplier of detected opponent positions
   */
  public FullAutonomousCommand(
      SwerveSubsystem swerve,
      SuperstructureStateMachine ssm,
      AutonomousStrategy strategy,
      DynamicAvoidanceLayer avoidanceLayer,
      NavigationGrid navGrid,
      Supplier<List<Translation2d>> fuelSupplier,
      Supplier<List<Translation2d>> opponentSupplier) {
    this.swerve = swerve;
    this.ssm = ssm;
    this.strategy = strategy;
    this.avoidanceLayer = avoidanceLayer;
    this.navGrid = navGrid;
    this.fuelSupplier = fuelSupplier;
    this.opponentSupplier = opponentSupplier;
    addRequirements(swerve);
  }

  /**
   * Convenience constructor with detection feeds but no NavGrid / avoidance layer.
   *
   * @param swerve swerve subsystem
   * @param ssm superstructure state machine
   * @param strategy decision engine
   * @param fuelSupplier supplier of detected FUEL positions
   * @param opponentSupplier supplier of detected opponent positions
   */
  public FullAutonomousCommand(
      SwerveSubsystem swerve,
      SuperstructureStateMachine ssm,
      AutonomousStrategy strategy,
      Supplier<List<Translation2d>> fuelSupplier,
      Supplier<List<Translation2d>> opponentSupplier) {
    this(swerve, ssm, strategy, new DynamicAvoidanceLayer(), null, fuelSupplier, opponentSupplier);
  }

  /** Convenience constructor with no external detection feeds. */
  public FullAutonomousCommand(
      SwerveSubsystem swerve, SuperstructureStateMachine ssm, AutonomousStrategy strategy) {
    this(swerve, ssm, strategy, Collections::emptyList, Collections::emptyList);
  }

  @Override
  public void initialize() {
    Logger.recordOutput("FullAuto/Status", "STARTING");

    evaluateAndDrive();
  }

  @Override
  public void execute() {
    if (activePathCommand == null) {
      evaluateAndDrive();
      return;
    }

    activePathCommand.execute();

    // ── Inject opponent positions as dynamic obstacles on the navigation grid ──
    List<Translation2d> opponents = opponentSupplier.get();
    updateDynamicObstacles(opponents);

    // ── Avoidance layer: compute corrected velocity for logging / diagnostics ──
    if (currentTarget != null && !opponents.isEmpty()) {
      Translation2d corrected =
          avoidanceLayer.computeCorrectedVelocity(
              swerve.getPose(), currentTarget.targetPose().getTranslation(), opponents);
      Logger.recordOutput("FullAuto/AvoidanceVelocity", corrected.toString());
    }

    // ── Check if current path finished ──
    if (activePathCommand.isFinished()) {
      activePathCommand.end(false);
      Logger.recordOutput("FullAuto/Status", "ARRIVED");

      notifySSM(currentTarget);
      evaluateAndDrive();
      return;
    }

    // ── Re-evaluate periodically (every 0.5s) ──
    if (cycleTimer.hasElapsed(0.5)) {
      cycleTimer.reset();

      // ── Bot Aborter: abort if any opponent will beat us to the target ──
      if (currentTarget != null && checkBotAborter(opponents)) {
        Logger.recordOutput("FullAuto/Status", "ABORT");

        activePathCommand.end(true);
        evaluateAndDrive();
        return;
      }

      // ── Retarget if a significantly better option appeared ──
      List<ScoredTarget> ranked = strategy.evaluateTargets(buildGameState());
      if (!ranked.isEmpty()) {
        ScoredTarget best = ranked.get(0);
        if (currentTarget != null
            && best.utility() - currentTarget.utility() > 5.0
            && !poseClose(best.targetPose(), currentTarget.targetPose())) {
          Logger.recordOutput("FullAuto/Status", "RETARGETING");

          activePathCommand.end(true);
          currentTarget = best;
          startPathTo(best);
        }
      }
    }
  }

  @Override
  public boolean isFinished() {
    return false;
  }

  @Override
  public void end(boolean interrupted) {
    if (activePathCommand != null) {
      activePathCommand.end(true);
      activePathCommand = null;
    }
    if (navGrid != null) {
      navGrid.clearDynamicObstacles();
    }
    Logger.recordOutput("FullAuto/Status", interrupted ? "INTERRUPTED" : "DONE");
  }

  // ---- private helpers ----

  private void evaluateAndDrive() {
    GameState state = buildGameState();
    List<ScoredTarget> ranked = strategy.evaluateTargets(state);
    if (ranked.isEmpty()) {
      Logger.recordOutput("FullAuto/Status", "NO_TARGETS");

      activePathCommand = null;
      currentTarget = null;
      return;
    }
    currentTarget = ranked.get(0);
    Logger.recordOutput("FullAuto/CurrentAction", currentTarget.actionType().name());
    Logger.recordOutput("FullAuto/CurrentTarget", currentTarget.targetPose());
    Logger.recordOutput("FullAuto/CurrentUtility", currentTarget.utility());
    startPathTo(currentTarget);
  }

  private void startPathTo(ScoredTarget target) {
    activePathCommand = new PathfindToGoalCommand(swerve, target.targetPose());
    activePathCommand.initialize();
    cycleTimer.restart();
  }

  private GameState buildGameState() {
    // getMatchTime() returns -1 when no match data is available (e.g. practice/test mode).
    // Default to 150s so the strategy doesn't incorrectly trigger CLIMB on startup.
    double rawTime = DriverStation.getMatchTime();
    double timeRemaining = (rawTime >= 0) ? rawTime : 150.0;

    // Suppliers are trusted to return non-null lists, but guard defensively so a bad
    // supplier can't crash the entire autonomous loop.
    List<Translation2d> fuel = fuelSupplier.get();
    List<Translation2d> opponents = opponentSupplier.get();
    if (fuel == null) fuel = Collections.emptyList();
    if (opponents == null) opponents = Collections.emptyList();

    return new GameState()
        .withRobotPose(swerve.getPose())
        .withFuelHeld(ssm.hasGamePiece() ? 1 : 0)
        .withHubActive(true)
        .withTimeRemaining(timeRemaining)
        .withDetectedFuel(fuel)
        .withDetectedOpponents(opponents);
  }

  /**
   * Bot Aborter — check if any opponent will reach our current target before us by the abort
   * threshold. Assumes opponents travel at max robot speed (worst case).
   *
   * @return true if the current target should be abandoned
   */
  private boolean checkBotAborter(List<Translation2d> opponents) {
    if (currentTarget == null || opponents.isEmpty()) return false;

    Translation2d targetPos = currentTarget.targetPose().getTranslation();
    Translation2d robotPos = swerve.getPose().getTranslation();
    double robotDist = robotPos.getDistance(targetPos);

    ChassisSpeeds vel = swerve.getRobotVelocity();
    double robotSpeed =
        Math.sqrt(
            vel.vxMetersPerSecond * vel.vxMetersPerSecond
                + vel.vyMetersPerSecond * vel.vyMetersPerSecond);
    // Floor robot speed at 0.5 m/s to avoid division by zero / infinite ETA
    robotSpeed = Math.max(robotSpeed, 0.5);

    for (Translation2d opp : opponents) {
      double oppDist = opp.getDistance(targetPos);
      // Assume opponent is traveling at max speed toward the target (worst case)
      double oppSpeed = Constants.Pathfinding.kMaxRobotSpeedMps;

      if (AutonomousStrategy.shouldAbortTarget(robotDist, robotSpeed, oppDist, oppSpeed)) {
        Logger.recordOutput("FullAuto/AbortReason", "Opponent at " + opp + " will arrive first");
        return true;
      }
    }
    return false;
  }

  /**
   * Stamp each opponent position as a square dynamic obstacle on the navigation grid so PPLib's AD*
   * re-plans around them. Clears previous obstacles first.
   */
  private void updateDynamicObstacles(List<Translation2d> opponents) {
    if (navGrid == null) return;
    navGrid.clearDynamicObstacles();
    for (Translation2d opp : opponents) {
      navGrid.setDynamicObstacle(
          new Translation2d(
              opp.getX() - OPPONENT_OBSTACLE_HALF_SIZE, opp.getY() - OPPONENT_OBSTACLE_HALF_SIZE),
          new Translation2d(
              opp.getX() + OPPONENT_OBSTACLE_HALF_SIZE, opp.getY() + OPPONENT_OBSTACLE_HALF_SIZE));
    }
  }

  private void notifySSM(ScoredTarget target) {
    if (target == null) return;
    switch (target.actionType()) {
      case SCORE -> ssm.requestScore();
      case COLLECT -> ssm.requestIntake();
      case CLIMB -> ssm.requestClimb();
    }
  }

  private static boolean poseClose(Pose2d a, Pose2d b) {
    return a.getTranslation().getDistance(b.getTranslation()) < 0.5;
  }
}
