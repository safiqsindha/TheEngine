package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Constants;
import frc.robot.subsystems.Intake;
import java.util.function.DoubleSupplier;

/**
 * Default intake command driven by the right trigger axis. First half of trigger scales arm angle
 * from min to max and spins the intake wheel proportionally.
 */
public class IntakeControl extends Command {

  private final Intake intake;
  private final DoubleSupplier triggerAxis;

  public IntakeControl(Intake intake, CommandXboxController controller) {
    this.intake = intake;
    this.triggerAxis = controller::getRightTriggerAxis;
    addRequirements(intake);
  }

  @Override
  public void initialize() {}

  @Override
  public void execute() {
    double trigger = Math.abs(triggerAxis.getAsDouble());

    // First half of trigger (0–0.5) maps arm from min to max angle
    double armScaled =
        Constants.Intake.kArmMinRotations
            + (Constants.Intake.kArmMaxRotations - Constants.Intake.kArmMinRotations)
                * (Math.min(0.5, trigger) / 0.5);

    // First half of trigger also maps wheel to full speed
    double wheelScaled = Math.min(0.5, trigger) / 0.5;

    intake.setWheel(wheelScaled);
    intake.updateTargetAngle(armScaled);
  }

  @Override
  public void end(boolean interrupted) {}

  @Override
  public boolean isFinished() {
    return false;
  }
}
