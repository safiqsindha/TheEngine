package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.subsystems.Conveyor;

/**
 * Default conveyor command. Holds the conveyor stopped. Dedicated commands (FlywheelAutoFeed,
 * IntakeControl) override this when scoring or intaking.
 */
public class ConveyorControl extends Command {

  private final Conveyor conveyor;

  public ConveyorControl(Conveyor conveyor, CommandXboxController controller) {
    this.conveyor = conveyor;
    addRequirements(conveyor);
  }

  @Override
  public void initialize() {}

  @Override
  public void execute() {
    // Default: hold conveyor stopped. Dedicated commands (FlywheelAutoFeed, etc.)
    // override this when scoring or intaking.
    conveyor.setConveyor(0);
  }

  @Override
  public void end(boolean interrupted) {}

  @Override
  public boolean isFinished() {
    return false;
  }
}
