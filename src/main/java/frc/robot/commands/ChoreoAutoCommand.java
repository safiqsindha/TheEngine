package frc.robot.commands;

import choreo.auto.AutoFactory;
import choreo.auto.AutoRoutine;
import choreo.auto.AutoTrajectory;
import choreo.trajectory.SwerveSample;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.ConditionalCommand;
import frc.robot.commands.flywheel.FlywheelAutoFeed;
import frc.robot.commands.flywheel.FlywheelStatic;
import frc.robot.subsystems.Conveyor;
import frc.robot.subsystems.Flywheel;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;

/**
 * Factory for Choreo trajectory-following autonomous routines.
 *
 * <p>Architecture notes:
 *
 * <ul>
 *   <li>Choreo is the sole trajectory pipeline — do NOT use PathPlannerLib.
 *   <li>Trajectories are created in the Choreo desktop app and exported to {@code
 *       src/main/deploy/choreo/} as {@code .traj} files.
 *   <li>All trajectories are authored on the blue-alliance side. {@code useAllianceFlipping = true}
 *       automatically mirrors them for red alliance.
 *   <li>The {@link AutoFactory} controller consumes a {@link SwerveSample} (not raw {@link
 *       edu.wpi.first.math.kinematics.ChassisSpeeds}) — call {@code sample.getChassisSpeeds()} to
 *       unwrap.
 * </ul>
 *
 * <p>To add a new path: create it in the Choreo desktop app, save to {@code
 * src/main/deploy/choreo/myPath.traj}, then add a routine method below and register it in {@code
 * RobotContainer.configureAutonomous()}.
 *
 * <p>Event markers added in the Choreo GUI (e.g. {@code "spinup"}, {@code "shoot"}) are bound to
 * commands via {@link AutoTrajectory#atTime(String)}.
 */
public final class ChoreoAutoCommand {

  // ─── Trajectory file names (must match .traj filenames without extension) ───
  /** Drive straight off the starting line (~2 m forward). */
  public static final String TRAJ_LEAVE_START = "leaveStart";

  /** Drive from reef scoring position to nearest coral station. */
  public static final String TRAJ_REEF_TO_STATION = "reefToStation";

  /** Drive from coral station back to reef scoring position. */
  public static final String TRAJ_STATION_TO_REEF = "stationToReef";

  private ChoreoAutoCommand() {}

  // ═══════════════════════════════════════════════════════════════════════════
  // FACTORY
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Create a configured {@link AutoFactory} bound to the given swerve subsystem.
   *
   * <p><b>Important:</b> The controller lambda explicitly unwraps {@link SwerveSample} to {@link
   * edu.wpi.first.math.kinematics.ChassisSpeeds}. Passing {@code swerve::driveRobotRelative}
   * directly would be a type mismatch — {@code AutoFactory} calls the consumer with a {@link
   * SwerveSample}, not a {@link edu.wpi.first.math.kinematics.ChassisSpeeds}.
   *
   * @param swerve the swerve subsystem
   * @return a configured, alliance-aware {@link AutoFactory}
   */
  public static AutoFactory factory(SwerveSubsystem swerve) {
    return new AutoFactory(
        swerve::getPose,
        swerve::resetOdometry,
        (SwerveSample sample) -> swerve.driveRobotRelative(sample.getChassisSpeeds()),
        true, // flip coordinates for red alliance
        swerve);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONVENIENCE — single-trajectory runner
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Create a command that follows a single named Choreo trajectory. Resets odometry to the
   * trajectory start pose before driving.
   *
   * @param trajectoryName the {@code .traj} filename without extension
   * @param swerve the swerve subsystem
   * @return a {@link Command} that follows the trajectory and finishes when complete
   */
  public static Command trajectory(String trajectoryName, SwerveSubsystem swerve) {
    AutoFactory f = factory(swerve);
    AutoRoutine routine = f.newRoutine(trajectoryName);
    AutoTrajectory traj = routine.trajectory(trajectoryName);
    routine.active().onTrue(traj.resetOdometry().andThen(traj.cmd()));
    return routine.cmd();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ROUTINES
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * <b>Leave Only</b> — drive straight off the starting line to earn the leave point. No scoring.
   *
   * <p>Requires: {@value #TRAJ_LEAVE_START}.traj
   */
  public static AutoRoutine leaveRoutine(AutoFactory factory) {
    AutoRoutine routine = factory.newRoutine("Leave Only");
    AutoTrajectory leave = routine.trajectory(TRAJ_LEAVE_START);
    routine.active().onTrue(leave.resetOdometry().andThen(leave.cmd()));
    return routine;
  }

  /**
   * <b>Score and Leave</b> — shoot the preloaded coral with the flywheel, then drive off the
   * starting line.
   *
   * <p>Requires: {@value #TRAJ_LEAVE_START}.traj
   */
  public static AutoRoutine scoreAndLeaveRoutine(
      AutoFactory factory, Flywheel flywheel, Conveyor conveyor) {
    AutoRoutine routine = factory.newRoutine("Score and Leave");
    AutoTrajectory leave = routine.trajectory(TRAJ_LEAVE_START);

    routine
        .active()
        .onTrue(
            Commands.sequence(
                // Shoot preloaded coral (up to 3 s), then drive off line
                new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                leave.resetOdometry().andThen(leave.cmd())));

    return routine;
  }

  /**
   * <b>2 Coral</b> — shoot preloaded coral, drive to the nearest coral station to collect a second
   * coral, return to the reef, and shoot again.
   *
   * <p>After the station pickup, a {@link ConditionalCommand} checks {@code ssm.hasGamePiece()}
   * before attempting the second shot. If the pickup failed, the robot skips scoring and returns to
   * idle — preventing a wasted spin-up cycle.
   *
   * <p>Requires: {@value #TRAJ_REEF_TO_STATION}.traj, {@value #TRAJ_STATION_TO_REEF}.traj
   *
   * <p>Event markers expected in trajectories:
   *
   * <ul>
   *   <li>{@code "intake"} in {@value #TRAJ_REEF_TO_STATION} — extend intake as robot approaches
   *       station
   *   <li>{@code "spinup"} in {@value #TRAJ_STATION_TO_REEF} — spin flywheel before reaching reef
   * </ul>
   */
  public static AutoRoutine twoCoralRoutine(
      AutoFactory factory, Flywheel flywheel, Conveyor conveyor, SuperstructureStateMachine ssm) {
    AutoRoutine routine = factory.newRoutine("2 Coral");
    AutoTrajectory toStation = routine.trajectory(TRAJ_REEF_TO_STATION);
    AutoTrajectory stationToReef = routine.trajectory(TRAJ_STATION_TO_REEF);

    // Step 1: shoot preloaded coral, then drive to station
    routine
        .active()
        .onTrue(
            Commands.sequence(
                new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                toStation.resetOdometry().andThen(toStation.cmd())));

    // Step 2: when arriving at station, drive back toward reef
    toStation.done().onTrue(stationToReef.cmd());

    // Step 3: spin up flywheel 1.5 s before reaching reef — only if game piece was acquired
    stationToReef
        .atTimeBeforeEnd(1.5)
        .onTrue(
            new ConditionalCommand(
                new FlywheelStatic(flywheel, conveyor, 3000).withTimeout(2.5),
                Commands.none(),
                ssm::hasGamePiece));

    // Step 4: when back at reef, shoot only if we successfully picked up a game piece
    stationToReef
        .done()
        .onTrue(
            new ConditionalCommand(
                new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                Commands.runOnce(
                    () ->
                        org.littletonrobotics.junction.Logger.recordOutput(
                            "Auto/SkippedShot", "2Coral-NoGamePiece")),
                ssm::hasGamePiece));

    return routine;
  }

  /**
   * <b>3 Coral</b> — two full station cycles: shoot preloaded, collect two more corals from the
   * station, and score all three.
   *
   * <p>Both scoring attempts after station pickups are gated by {@link ConditionalCommand} checking
   * {@code ssm.hasGamePiece()}. A missed pickup causes the robot to skip the shot and move on to
   * the next cycle rather than wasting time spinning up the flywheel.
   *
   * <p>Requires: {@value #TRAJ_REEF_TO_STATION}.traj, {@value #TRAJ_STATION_TO_REEF}.traj (both run
   * twice).
   *
   * <p>This routine reuses the same trajectory segments for both collection cycles. If the two
   * cycles require different paths, split them into separate {@code .traj} files.
   */
  public static AutoRoutine threeCoralRoutine(
      AutoFactory factory, Flywheel flywheel, Conveyor conveyor, SuperstructureStateMachine ssm) {
    AutoRoutine routine = factory.newRoutine("3 Coral");

    // First cycle uses split index 0 (or whole file if no splits defined)
    AutoTrajectory toStation1 = routine.trajectory(TRAJ_REEF_TO_STATION, 0);
    AutoTrajectory stationToReef1 = routine.trajectory(TRAJ_STATION_TO_REEF, 0);

    // Second cycle uses split index 1 (or falls back to whole file if no split)
    AutoTrajectory toStation2 = routine.trajectory(TRAJ_REEF_TO_STATION, 1);
    AutoTrajectory stationToReef2 = routine.trajectory(TRAJ_STATION_TO_REEF, 1);

    // ── Cycle 1 ──────────────────────────────────────────────────────────────
    routine
        .active()
        .onTrue(
            Commands.sequence(
                new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                toStation1.resetOdometry().andThen(toStation1.cmd())));

    toStation1.done().onTrue(stationToReef1.cmd());

    // Spin up only if game piece acquired at station 1
    stationToReef1
        .atTimeBeforeEnd(1.5)
        .onTrue(
            new ConditionalCommand(
                new FlywheelStatic(flywheel, conveyor, 3000).withTimeout(2.5),
                Commands.none(),
                ssm::hasGamePiece));

    // After cycle 1 return: shoot if acquired, then always proceed to cycle 2
    stationToReef1
        .done()
        .onTrue(
            Commands.sequence(
                new ConditionalCommand(
                    new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                    Commands.runOnce(
                        () ->
                            org.littletonrobotics.junction.Logger.recordOutput(
                                "Auto/SkippedShot", "3Coral-Cycle1-NoGamePiece")),
                    ssm::hasGamePiece),
                // Always attempt cycle 2 regardless of cycle 1 outcome
                toStation2.cmd()));

    // ── Cycle 2 ──────────────────────────────────────────────────────────────
    toStation2.done().onTrue(stationToReef2.cmd());

    // Spin up only if game piece acquired at station 2
    stationToReef2
        .atTimeBeforeEnd(1.5)
        .onTrue(
            new ConditionalCommand(
                new FlywheelStatic(flywheel, conveyor, 3000).withTimeout(2.5),
                Commands.none(),
                ssm::hasGamePiece));

    // Shoot cycle 2 if acquired
    stationToReef2
        .done()
        .onTrue(
            new ConditionalCommand(
                new FlywheelAutoFeed(flywheel, conveyor).withTimeout(3.0),
                Commands.runOnce(
                    () ->
                        org.littletonrobotics.junction.Logger.recordOutput(
                            "Auto/SkippedShot", "3Coral-Cycle2-NoGamePiece")),
                ssm::hasGamePiece));

    return routine;
  }
}
