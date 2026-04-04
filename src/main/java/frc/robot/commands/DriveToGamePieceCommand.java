package frc.robot.commands;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Constants;
import frc.robot.subsystems.FuelDetectionConsumer;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;
import java.util.List;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Teleop command: drives toward the nearest confirmed FUEL detection while the driver retains
 * rotation control (right stick). Release the left bumper to return to manual control.
 *
 * <p>Translation is auto-computed toward the nearest {@link FuelDetectionConsumer} position. If no
 * fuel is detected, the robot holds still in translation (driver can still rotate).
 */
public class DriveToGamePieceCommand extends Command {

  private final SwerveSubsystem swerve;
  private final VisionSubsystem vision;
  private final DoubleSupplier rotationSupplier;

  /** Proportional gain: meters of error → fraction of max speed. */
  private static final double kTranslationP = 0.4;

  /** Stop driving toward target when within this distance (meters). */
  private static final double kArrivalThresholdM = 0.5;

  public DriveToGamePieceCommand(
      SwerveSubsystem swerve, VisionSubsystem vision, DoubleSupplier rotation) {
    this.swerve = swerve;
    this.vision = vision;
    this.rotationSupplier = rotation;
    addRequirements(swerve);
  }

  @Override
  public void initialize() {
    vision.setNeuralPipeline();
    Logger.recordOutput("DriveToGamePiece/Status", "SEEKING");
  }

  @Override
  public void execute() {
    List<Translation2d> fuelPositions = vision.getFuelPositions();
    Translation2d robotPos = swerve.getPose().getTranslation();

    // Find nearest confirmed fuel detection
    Translation2d nearest = null;
    double nearestDist = Double.MAX_VALUE;
    for (Translation2d pos : fuelPositions) {
      double dist = robotPos.getDistance(pos);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = pos;
      }
    }

    Translation2d translation;
    if (nearest != null && nearestDist > kArrivalThresholdM) {
      // Drive toward nearest fuel — proportional controller, capped at 1.0 (max speed)
      Translation2d toTarget = nearest.minus(robotPos);
      double speed = Math.min(nearestDist * kTranslationP, 1.0);
      double norm = toTarget.getNorm();
      // Guard against division by zero if robot is exactly on the fuel position
      if (norm < 1e-6) {
        translation = new Translation2d();
      } else {
        translation =
            new Translation2d(toTarget.getX() / norm, toTarget.getY() / norm)
                .times(speed * Constants.Swerve.kMaxSpeedMetersPerSec);
      }
      Logger.recordOutput("DriveToGamePiece/Status", "DRIVING");
      Logger.recordOutput("DriveToGamePiece/TargetPos", nearest.toString());
      Logger.recordOutput("DriveToGamePiece/DistanceM", nearestDist);
    } else {
      translation = new Translation2d();
      Logger.recordOutput("DriveToGamePiece/Status", nearest != null ? "ARRIVED" : "NO_DETECTION");
    }

    // Driver keeps rotation
    double rotInput =
        MathUtil.applyDeadband(rotationSupplier.getAsDouble(), Constants.OI.kDriveDeadband);
    double rotation = rotInput * Constants.Swerve.kMaxAngularSpeedRadPerSec;

    swerve.drive(translation, rotation, true);
  }

  @Override
  public void end(boolean interrupted) {
    Logger.recordOutput("DriveToGamePiece/Status", "MANUAL");
  }

  @Override
  public boolean isFinished() {
    return false;
  }
}
