package frc.robot;

import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotController;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import org.littletonrobotics.junction.LoggedRobot;
import org.littletonrobotics.junction.Logger;
import org.littletonrobotics.junction.networktables.NT4Publisher;
import org.littletonrobotics.junction.wpilog.WPILOGWriter;

/**
 * The VM is configured to automatically run this class, and to call the functions corresponding to
 * each mode, as described in the TimedRobot documentation.
 *
 * <p>Uses AdvantageKit's LoggedRobot for deterministic logging and replay.
 */
public class Robot extends LoggedRobot {

  /** Voltage below which brownout protection reduces motor output. */
  private static final double kBrownoutThresholdVolts = 8.0;

  /** Voltage below which we log a critical warning. */
  private static final double kCriticalVoltageVolts = 6.5;

  private RobotContainer robotContainer;

  // ── Match phase tracking ──
  private enum MatchPhase {
    DISABLED,
    AUTO,
    TELEOP,
    TEST
  }

  private MatchPhase currentPhase = MatchPhase.DISABLED;
  private double phaseStartTimestamp = 0.0;

  @Override
  public void robotInit() {
    // Set up AdvantageKit logging
    Logger.recordMetadata("ProjectName", "Constructicon Core");
    Logger.recordMetadata("TeamNumber", "2950");
    Logger.recordMetadata("BuildDate", BuildConstants.BUILD_DATE);
    Logger.recordMetadata("GitSHA", BuildConstants.GIT_SHA);

    if (isReal()) {
      // Running on real robot: log to USB stick and publish to NetworkTables
      Logger.addDataReceiver(new WPILOGWriter());
      Logger.addDataReceiver(new NT4Publisher());
    } else {
      // Running in simulation: publish to NetworkTables only
      Logger.addDataReceiver(new NT4Publisher());
    }

    // Start AdvantageKit logger
    Logger.start();

    // Instantiate our RobotContainer. This will perform all button bindings,
    // set default commands, and configure the autonomous chooser.
    robotContainer = new RobotContainer();
  }

  @Override
  public void robotPeriodic() {
    // Run the command scheduler. This polls buttons, adds newly-scheduled
    // commands, runs currently-scheduled commands, removes finished commands,
    // and calls the periodic() methods of subsystems.
    CommandScheduler.getInstance().run();

    // ── Telemetry: battery, match timer, brownout status ──
    double batteryVolts = RobotController.getBatteryVoltage();
    Logger.recordOutput("Robot/BatteryVoltage", batteryVolts);
    Logger.recordOutput("Robot/MatchTimeRemaining", DriverStation.getMatchTime());
    Logger.recordOutput("Robot/BrownoutActive", batteryVolts < kBrownoutThresholdVolts);
    Logger.recordOutput(
        "Robot/CANBusUtilization", RobotController.getCANStatus().percentBusUtilization);

    if (batteryVolts < kCriticalVoltageVolts) {
      Logger.recordOutput("Robot/CriticalVoltageWarning", true);
    }

    // Brownout scale factor: linearly ramp down motor output from 100% at threshold to 50% at 6.0V
    double brownoutScale =
        batteryVolts >= kBrownoutThresholdVolts
            ? 1.0
            : Math.max(0.5, (batteryVolts - 6.0) / (kBrownoutThresholdVolts - 6.0));
    Logger.recordOutput("Robot/BrownoutScale", brownoutScale);
  }

  /**
   * Compute a motor output scale factor based on current battery voltage. Returns 1.0 when voltage
   * is healthy, ramps down linearly to 0.5 as voltage approaches 6.0V.
   */
  public static double getBrownoutScale() {
    double volts = RobotController.getBatteryVoltage();
    if (volts >= kBrownoutThresholdVolts) return 1.0;
    return Math.max(0.5, (volts - 6.0) / (kBrownoutThresholdVolts - 6.0));
  }

  private void logPhaseTransition(MatchPhase newPhase) {
    double now = edu.wpi.first.wpilibj.Timer.getFPGATimestamp();
    double elapsed = now - phaseStartTimestamp;
    Logger.recordOutput("Robot/Phase", currentPhase.name());
    Logger.recordOutput("Robot/PhaseElapsedSec", elapsed);
    Logger.recordOutput("Robot/PhaseTransitionTo", newPhase.name());
    System.out.printf("[Robot] %s → %s (phase lasted %.2fs)%n", currentPhase, newPhase, elapsed);
    currentPhase = newPhase;
    phaseStartTimestamp = now;
  }

  @Override
  public void disabledInit() {
    logPhaseTransition(MatchPhase.DISABLED);
  }

  @Override
  public void disabledPeriodic() {}

  @Override
  public void autonomousInit() {
    logPhaseTransition(MatchPhase.AUTO);
    if (isReal()) {
      Helper.llSetup();
    }
    // Neural detector in autonomous for game piece detection
    robotContainer.vision.setNeuralPipeline();
    robotContainer.intake.resetEncoder();
    var autoCommand = robotContainer.getAutonomousCommand();
    if (autoCommand != null) {
      CommandScheduler.getInstance().schedule(autoCommand);
    }
  }

  @Override
  public void autonomousPeriodic() {}

  @Override
  public void teleopInit() {
    logPhaseTransition(MatchPhase.TELEOP);
    // Cancel autonomous command when teleop starts
    var autoCommand = robotContainer.getAutonomousCommand();
    if (autoCommand != null) {
      autoCommand.cancel();
    }
    // Switch to AprilTag pipeline for teleop pose estimation and scoring alignment
    robotContainer.vision.setAprilTagPipeline();
  }

  @Override
  public void teleopPeriodic() {}

  @Override
  public void testInit() {
    logPhaseTransition(MatchPhase.TEST);
    CommandScheduler.getInstance().cancelAll();
  }

  @Override
  public void testPeriodic() {}

  @Override
  public void simulationInit() {
    // maple-sim arena is managed by YAGSL internally — no setup needed here.
    // YAGSL's SwerveDrive constructor registers its SwerveDriveSimulation with
    // SimulatedArena and drives SimulatedArena.simulationPeriodic() from its
    // 4ms odometry Notifier thread. simulationPeriodic() must NOT be called
    // again here, as that would double-step the physics engine.

    // Apply selected driver practice scenario (sets alliance, mode, and start pose).
    // Defaults to TELEOP_BLUE_CENTER; change via the SmartDashboard "Practice Scenario" chooser.
    robotContainer.getPracticeMode().apply();
  }
}
