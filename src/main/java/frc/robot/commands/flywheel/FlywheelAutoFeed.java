package frc.robot.commands.flywheel;

import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Helper;
import frc.robot.subsystems.Conveyor;
import frc.robot.subsystems.Flywheel;

/**
 * Spins up the flywheel to the distance-predicted RPM and auto-feeds once within 10% of target.
 * Uses Limelight AprilTag distance for dynamic RPM calculation.
 */
public class FlywheelAutoFeed extends Command {

  private final Flywheel flywheel;
  private final Conveyor conveyor;

  private static final double kFeederPercent = 1.0;
  private static final double kConveyorPercent = 1.0;

  private boolean rpmReady = false;

  public FlywheelAutoFeed(Flywheel flywheel, Conveyor conveyor) {
    this.flywheel = flywheel;
    this.conveyor = conveyor;
    addRequirements(flywheel, conveyor);
  }

  @Override
  public void initialize() {
    rpmReady = false;
    flywheel.setLower(-0.1);
    conveyor.setConveyor(0);
    Helper.resetFilters();
  }

  @Override
  public void execute() {
    Helper.updateFilters();
    double distance = Helper.getAprilTagDist();
    double predictedRpm = Helper.rpmFromMeters(distance);

    Helper.printRpmDistance(predictedRpm, distance);
    flywheel.setTargetRpm(predictedRpm);

    if (rpmReady) {
      flywheel.setLower(kFeederPercent);
      conveyor.setConveyor(kConveyorPercent);
    } else {
      rpmReady =
          Math.abs((flywheel.getCurrentRpm() - predictedRpm) / predictedRpm)
              < frc.robot.Constants.Flywheel.kReadyThreshold;
    }
  }

  @Override
  public void end(boolean interrupted) {
    flywheel.setTargetRpm(0);
    flywheel.setLower(0);
    conveyor.setConveyor(0);
  }

  @Override
  public boolean isFinished() {
    return false;
  }
}
