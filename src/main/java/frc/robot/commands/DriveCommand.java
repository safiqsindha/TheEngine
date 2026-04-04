package frc.robot.commands;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Constants;
import frc.robot.Robot;
import frc.robot.subsystems.SwerveSubsystem;
import java.util.function.DoubleSupplier;

/**
 * Default drive command for teleop. Maps joystick inputs to field-relative swerve drive.
 *
 * <p>Left stick = translation (X/Y). Right stick X = rotation.
 */
public class DriveCommand extends Command {

  private final SwerveSubsystem swerve;
  private final DoubleSupplier translationXSupplier;
  private final DoubleSupplier translationYSupplier;
  private final DoubleSupplier rotationSupplier;

  /**
   * Creates a new DriveCommand.
   *
   * @param swerve the swerve subsystem
   * @param translationX supplier for X translation (-1 to 1, forward positive)
   * @param translationY supplier for Y translation (-1 to 1, left positive)
   * @param rotation supplier for rotation (-1 to 1, CCW positive)
   */
  public DriveCommand(
      SwerveSubsystem swerve,
      DoubleSupplier translationX,
      DoubleSupplier translationY,
      DoubleSupplier rotation) {
    this.swerve = swerve;
    this.translationXSupplier = translationX;
    this.translationYSupplier = translationY;
    this.rotationSupplier = rotation;
    addRequirements(swerve);
  }

  @Override
  public void execute() {
    // Apply deadband to joystick inputs
    double xInput =
        MathUtil.applyDeadband(translationXSupplier.getAsDouble(), Constants.OI.kDriveDeadband);
    double yInput =
        MathUtil.applyDeadband(translationYSupplier.getAsDouble(), Constants.OI.kDriveDeadband);
    double rotInput =
        MathUtil.applyDeadband(rotationSupplier.getAsDouble(), Constants.OI.kDriveDeadband);

    // Convert joystick inputs to m/s and rad/s, scaled by brownout protection
    double scale = Robot.getBrownoutScale();
    Translation2d translation =
        new Translation2d(xInput, yInput).times(Constants.Swerve.kMaxSpeedMetersPerSec * scale);
    double rotation = rotInput * Constants.Swerve.kMaxAngularSpeedRadPerSec * scale;

    // Drive field-relative
    swerve.drive(translation, rotation, true);
  }

  @Override
  public boolean isFinished() {
    // Default command never finishes
    return false;
  }
}
