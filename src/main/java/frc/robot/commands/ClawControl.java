package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.subsystems.SideClaw;

/**
 * Instant command that sets the side claw to a target position. Finishes immediately after setting
 * the position setpoint — the SPARK MAX onboard PID holds position.
 */
public class ClawControl extends Command {

  private final SideClaw sideClaw;
  private final double position;

  public ClawControl(SideClaw sideClaw, double position) {
    this.sideClaw = sideClaw;
    this.position = position;
    addRequirements(sideClaw);
  }

  @Override
  public void initialize() {
    sideClaw.setTargetPosition(position);
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
