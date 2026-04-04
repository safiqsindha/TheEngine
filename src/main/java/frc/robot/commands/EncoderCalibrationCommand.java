package frc.robot.commands;

import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.subsystems.SwerveSubsystem;
import org.littletonrobotics.junction.Logger;
import swervelib.SwerveModule;

/**
 * Reads the raw absolute encoder position for each swerve module and logs it in a format that can
 * be copy-pasted directly into {@code hardware_config.ini}.
 *
 * <p><b>How to use on hardware:</b>
 *
 * <ol>
 *   <li>Point all four swerve modules straight forward (bevel gear facing the correct direction).
 *   <li>Deploy the code, enable the robot in <b>Test</b> mode.
 *   <li>Bind this command to a button in {@code RobotContainer} test bindings, or run it via
 *       SmartDashboard.
 *   <li>Open AdvantageScope or the SmartDashboard — copy the four offset values from {@code
 *       Calibration/hardware_config_ini_snippet} into the {@code [encoder_offsets]} section of
 *       {@code hardware_config.ini}.
 *   <li>Run {@code python tools/generate_configs.py} to regenerate module JSON files.
 *   <li>Redeploy.
 * </ol>
 *
 * <p>This command finishes immediately after logging — it does not hold any subsystem and can run
 * in any robot mode.
 */
public class EncoderCalibrationCommand extends Command {

  private final SwerveSubsystem swerve;

  public EncoderCalibrationCommand(SwerveSubsystem swerve) {
    this.swerve = swerve;
    // No requirements — read-only, never conflicts with drive commands.
  }

  @Override
  public void initialize() {
    SwerveModule[] modules = swerve.getModules();

    StringBuilder snippet = new StringBuilder("[encoder_offsets]\n");

    for (SwerveModule module : modules) {
      // getRawAbsolutePosition() returns the encoder reading minus whatever offset is
      // currently programmed. We want the *raw* reading so the user can record it as
      // the new zero offset. absolutePositionCache holds the last value from the encoder.
      double rawDegrees = module.absolutePositionCache.getValue();
      String name = module.configuration.name; // "frontleft", "frontright", etc.

      // Normalise to [0, 360)
      double normalised = ((rawDegrees % 360.0) + 360.0) % 360.0;

      Logger.recordOutput("Calibration/" + name + "_raw_deg", rawDegrees);
      Logger.recordOutput("Calibration/" + name + "_offset_deg", normalised);
      SmartDashboard.putNumber("Calibration/" + name + " offset (deg)", normalised);

      snippet
          .append(name)
          .append("_offset_deg = ")
          .append(String.format("%.3f", normalised))
          .append("\n");
    }

    String snippetStr = snippet.toString();
    Logger.recordOutput("Calibration/hardware_config_ini_snippet", snippetStr);
    SmartDashboard.putString("Calibration/hardware_config_ini_snippet", snippetStr);

    // Print to Driver Station console so the student can see it immediately
    System.out.println("\n========== ENCODER OFFSETS ==========");
    System.out.println(snippetStr);
    System.out.println("Copy the above into hardware_config.ini [encoder_offsets]");
    System.out.println("Then run: python tools/generate_configs.py");
    System.out.println("=====================================\n");
  }

  @Override
  public boolean isFinished() {
    return true;
  }
}
