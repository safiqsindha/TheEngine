package frc.robot.commands.flywheel;

import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Constants;
import frc.robot.Helper;
import frc.robot.subsystems.Conveyor;
import frc.robot.subsystems.Flywheel;

/**
 * Spins up the flywheel to a fixed RPM setpoint and auto-feeds once within 10% of target. Used for
 * POV-button preset shots at known distances.
 */
public class FlywheelStatic extends Command {

  private final Flywheel flywheel;
  private final Conveyor conveyor;
  private final double targetRpm;

  private static final double kFeederPercent = 1.0;
  private static final double kConveyorPercent = 1.0;

  private boolean rpmReady = false;

  public FlywheelStatic(Flywheel flywheel, Conveyor conveyor, double staticSetpointRpm) {
    this.flywheel = flywheel;
    this.conveyor = conveyor;
    this.targetRpm = staticSetpointRpm;
    addRequirements(flywheel, conveyor);
  }

  @Override
  public void initialize() {
    flywheel.setTargetRpm(targetRpm);
    flywheel.setLower(-0.1);
    Helper.resetFilters();
    rpmReady = false;
  }

  @Override
  public void execute() {
    Helper.updateFilters();
    double distance = Helper.getAprilTagDist();
    Helper.printRpmDistance(targetRpm, distance);

    if (rpmReady) {
      flywheel.setLower(kFeederPercent);
      conveyor.setConveyor(kConveyorPercent);
    } else {
      rpmReady =
          Math.abs((flywheel.getCurrentRpm() - targetRpm) / targetRpm)
              < Constants.Flywheel.kReadyThreshold;
    }
  }

  @Override
  public void end(boolean interrupted) {
    flywheel.setTargetRpm(0);
    flywheel.setLower(0);
  }

  @Override
  public boolean isFinished() {
    return false;
  }
}
