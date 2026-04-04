package frc.robot;

import edu.wpi.first.hal.AllianceStationID;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.wpilibj.simulation.DriverStationSim;
import edu.wpi.first.wpilibj.smartdashboard.SendableChooser;
import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import frc.robot.subsystems.SwerveSubsystem;
import org.littletonrobotics.junction.Logger;

/**
 * Driver practice simulation configuration. Publishes a SmartDashboard chooser for selecting
 * practice scenarios and starting positions. Run {@link #apply()} once in {@code simulationInit()}
 * to configure the DriverStation sim state and reset the robot to the selected start pose.
 *
 * <p>Use the controller's Start button (in test mode) or call {@link #resetToStart()} to teleport
 * the robot back to the scenario's starting position during practice.
 */
public class DriverPracticeMode {

  /** Field-relative starting poses for each practice scenario (blue alliance). */
  public enum Scenario {
    FULL_AUTO_BLUE(
        "Full Auto – Blue",
        AllianceStationID.Blue1,
        new Pose2d(1.5, 4.0, Rotation2d.fromDegrees(0)),
        true),

    FULL_AUTO_RED(
        "Full Auto – Red",
        AllianceStationID.Red1,
        new Pose2d(Constants.kFieldLengthMeters - 1.5, 4.0, Rotation2d.fromDegrees(180)),
        true),

    TELEOP_BLUE_CENTER(
        "Teleop – Blue Center",
        AllianceStationID.Blue2,
        new Pose2d(1.5, 4.1, Rotation2d.fromDegrees(0)),
        false),

    TELEOP_RED_CENTER(
        "Teleop – Red Center",
        AllianceStationID.Red2,
        new Pose2d(Constants.kFieldLengthMeters - 1.5, 4.1, Rotation2d.fromDegrees(180)),
        false),

    TELEOP_BLUE_NEAR_HUB(
        "Teleop – Blue Near Hub",
        AllianceStationID.Blue1,
        new Pose2d(4.5, 4.1, Rotation2d.fromDegrees(0)),
        false),

    STRESS_TEST(
        "Stress Test – Full Field",
        AllianceStationID.Blue3,
        new Pose2d(1.0, 1.0, Rotation2d.fromDegrees(45)),
        false);

    final String label;
    final AllianceStationID station;
    final Pose2d startPose;
    final boolean autoMode;

    Scenario(String label, AllianceStationID station, Pose2d startPose, boolean autoMode) {
      this.label = label;
      this.station = station;
      this.startPose = startPose;
      this.autoMode = autoMode;
    }
  }

  private final SwerveSubsystem swerve;
  private final SendableChooser<Scenario> scenarioChooser = new SendableChooser<>();

  public DriverPracticeMode(SwerveSubsystem swerve) {
    this.swerve = swerve;

    scenarioChooser.setDefaultOption(
        Scenario.TELEOP_BLUE_CENTER.label, Scenario.TELEOP_BLUE_CENTER);
    for (Scenario s : Scenario.values()) {
      if (s != Scenario.TELEOP_BLUE_CENTER) {
        scenarioChooser.addOption(s.label, s);
      }
    }

    SmartDashboard.putData("Practice Scenario", scenarioChooser);
    SmartDashboard.putString(
        "Practice/Instructions",
        "Select scenario, restart sim, then use Start button to reset to start");
  }

  /**
   * Apply the selected scenario to the DriverStation sim. Call once in {@code simulationInit()}.
   */
  public void apply() {
    Scenario selected = getSelected();
    DriverStationSim.setAllianceStationId(selected.station);
    DriverStationSim.setAutonomous(selected.autoMode);
    DriverStationSim.setEnabled(true);
    DriverStationSim.notifyNewData();
    resetToStart();
    Logger.recordOutput("Practice/Scenario", selected.label);
    Logger.recordOutput("Practice/StartPose", selected.startPose);
  }

  /**
   * Reset the robot pose to the scenario's starting position. Bind this to a controller button for
   * quick practice resets without restarting the sim.
   */
  public void resetToStart() {
    swerve.resetOdometry(getSelected().startPose);
    Logger.recordOutput("Practice/Reset", true);
  }

  /** Get the currently selected scenario. */
  public Scenario getSelected() {
    Scenario s = scenarioChooser.getSelected();
    return s != null ? s : Scenario.TELEOP_BLUE_CENTER;
  }

  /** Whether the currently selected scenario starts in autonomous mode. */
  public boolean isAutoScenario() {
    return getSelected().autoMode;
  }
}
