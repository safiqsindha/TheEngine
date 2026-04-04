package frc.robot.commands.flywheel;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Helper;
import frc.robot.subsystems.Flywheel;
import java.util.function.DoubleSupplier;

/**
 * Default flywheel command driven by the left trigger axis. First threshold starts the flywheel;
 * second threshold triggers the lower feed wheels.
 */
public class FlywheelDynamic extends Command {

  private final Flywheel flywheel;
  private final DoubleSupplier triggerAxis;

  private static final double kFirstThreshold = 0.1;
  private static final double kSecondThreshold = 0.9;
  private static final double kFeederPercent = 1.0;

  public FlywheelDynamic(Flywheel flywheel, CommandXboxController controller) {
    this.flywheel = flywheel;
    this.triggerAxis = controller::getLeftTriggerAxis;
    addRequirements(flywheel);
  }

  @Override
  public void initialize() {
    // In simulation, skip both calls: Helper class-loading (new Limelight) blocks
    // ~2 seconds on first access, which would expire a Choreo trajectory.
    if (!edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      Helper.resetFilters();
      flywheel.setLower(-0.1);
    }
  }

  @Override
  public void execute() {
    double trigger = Math.abs(triggerAxis.getAsDouble());

    if (trigger > kFirstThreshold) {
      flywheel.leftVortex.set(1);
    } else {
      flywheel.leftVortex.set(0);
    }

    flywheel.setLower(kFeederPercent * (trigger > kSecondThreshold ? 1 : 0));
  }

  @Override
  public void end(boolean interrupted) {}

  @Override
  public boolean isFinished() {
    return false;
  }
}
