package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.subsystems.Climber;

/**
 * Instant command that sets the climber to a target position. Finishes immediately after setting
 * the position setpoint — the SPARK MAX onboard PID holds position.
 */
public class ClimberControl extends Command {

  private final Climber climber;
  private final double position;

  public ClimberControl(Climber climber, double position) {
    this.climber = climber;
    this.position = position;
    addRequirements(climber);
  }

  @Override
  public void initialize() {
    climber.setTargetPosition(position);
  }

  @Override
  public void execute() {}

  @Override
  public void end(boolean interrupted) {}

  @Override
  public boolean isFinished() {
    return true;
  }
}
