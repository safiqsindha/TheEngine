package frc.robot.commands;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Constants;
import frc.robot.Helper;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Teleop auto-align command. The driver retains full translation control (left stick) while the
 * robot automatically rotates to face the nearest AprilTag scoring target.
 *
 * <p>Intended for use with {@code whileTrue} on the right bumper — release returns to manual
 * control via the default {@link DriveCommand}.
 */
public class AutoAlignCommand extends Command {

  private static final double kP = 0.05;
  private static final double kRotationSign = -1.0;

  private final SwerveSubsystem swerve;
  private final VisionSubsystem vision;
  private final DoubleSupplier translationXSupplier;
  private final DoubleSupplier translationYSupplier;

  /**
   * @param swerve swerve subsystem
   * @param vision vision subsystem (used to confirm target lock)
   * @param translationX forward/back joystick supplier (-1 to 1)
   * @param translationY left/right joystick supplier (-1 to 1)
   */
  public AutoAlignCommand(
      SwerveSubsystem swerve,
      VisionSubsystem vision,
      DoubleSupplier translationX,
      DoubleSupplier translationY) {
    this.swerve = swerve;
    this.vision = vision;
    this.translationXSupplier = translationX;
    this.translationYSupplier = translationY;
    addRequirements(swerve);
  }

  @Override
  public void initialize() {
    Helper.resetFilters();
    vision.setAprilTagPipeline();
    Logger.recordOutput("AutoAlign/Status", "ALIGNING");
  }

  @Override
  public void execute() {
    Helper.updateFilters();

    // Driver translation from left stick
    double xInput =
        MathUtil.applyDeadband(translationXSupplier.getAsDouble(), Constants.OI.kDriveDeadband);
    double yInput =
        MathUtil.applyDeadband(translationYSupplier.getAsDouble(), Constants.OI.kDriveDeadband);
    Translation2d translation =
        new Translation2d(xInput, yInput).times(Constants.Swerve.kMaxSpeedMetersPerSec);

    // Auto rotation toward AprilTag target
    double txOffset = Helper.getAprilTagAim();
    double rotation = kRotationSign * (txOffset * kP);

    Logger.recordOutput("AutoAlign/TxOffset", txOffset);
    Logger.recordOutput("AutoAlign/HasTarget", vision.hasTarget());

    swerve.drive(translation, rotation, true);
  }

  @Override
  public void end(boolean interrupted) {
    Logger.recordOutput("AutoAlign/Status", "MANUAL");
  }

  @Override
  public boolean isFinished() {
    return false;
  }
}
