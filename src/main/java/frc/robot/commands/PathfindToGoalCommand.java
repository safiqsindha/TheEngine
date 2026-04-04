package frc.robot.commands;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.subsystems.SwerveSubsystem;
import org.littletonrobotics.junction.Logger;

/**
 * Wraps PathPlannerLib's AD* pathfinding with AdvantageKit logging and clean lifecycle management.
 *
 * <p>Used by FullAutonomousCommand to drive the robot to scored waypoints. The inner pathfinding
 * command is created by {@link SwerveSubsystem#pathfindToPose(Pose2d)} (which delegates to PPLib's
 * {@code AutoBuilder.pathfindToPose()}).
 *
 * <p>Logs target pose, distance remaining, and completion status under {@code Pathfind/} in
 * AdvantageKit.
 */
public class PathfindToGoalCommand extends Command {

  private final SwerveSubsystem swerve;
  private final Pose2d targetPose;
  private Command innerCommand;

  /**
   * Create a pathfinding command to the given target pose.
   *
   * @param swerve the swerve subsystem (also satisfies the PPLib requirement)
   * @param targetPose the desired end pose (field-relative)
   */
  public PathfindToGoalCommand(SwerveSubsystem swerve, Pose2d targetPose) {
    this.swerve = swerve;
    this.targetPose = targetPose;
    addRequirements(swerve);
  }

  @Override
  public void initialize() {
    Logger.recordOutput("Pathfind/TargetPose", targetPose);
    Logger.recordOutput("Pathfind/Status", "PATHFINDING");
    innerCommand = swerve.pathfindToPose(targetPose);
    innerCommand.initialize();
  }

  @Override
  public void execute() {
    innerCommand.execute();
    double distanceRemaining =
        swerve.getPose().getTranslation().getDistance(targetPose.getTranslation());
    Logger.recordOutput("Pathfind/DistanceRemaining", distanceRemaining);
  }

  @Override
  public boolean isFinished() {
    return innerCommand.isFinished();
  }

  @Override
  public void end(boolean interrupted) {
    innerCommand.end(interrupted);
    Logger.recordOutput("Pathfind/Status", interrupted ? "INTERRUPTED" : "ARRIVED");
    Logger.recordOutput("Pathfind/FinalPose", swerve.getPose());
  }

  /** Get the target pose this command is driving toward. */
  public Pose2d getTargetPose() {
    return targetPose;
  }
}
