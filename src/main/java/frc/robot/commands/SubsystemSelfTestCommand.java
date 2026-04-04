package frc.robot.commands;

import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;
import org.littletonrobotics.junction.Logger;
import swervelib.SwerveModule;

/**
 * Pit diagnostic command that sequentially tests each subsystem and reports PASS/FAIL. Designed to
 * run on the actual robot in Test mode. Read-only -- does not actuate any mechanisms.
 *
 * <p>Tests:
 *
 * <ul>
 *   <li><b>SWERVE_POSITION</b> -- reads all 4 absolute encoder positions; PASS if all return
 *       non-NaN values.
 *   <li><b>GYRO_CHECK</b> -- reads gyro heading; PASS if it returns a non-NaN value.
 *   <li><b>VISION_CHECK</b> -- checks whether the vision subsystem is publishing; PASS if {@link
 *       VisionSubsystem#hasTarget()} returns without error (subsystem is alive).
 * </ul>
 */
public class SubsystemSelfTestCommand extends Command {

  /** Sequential test phases executed by this command. */
  enum TestPhase {
    SWERVE_POSITION,
    GYRO_CHECK,
    VISION_CHECK,
    COMPLETE
  }

  private final SwerveSubsystem swerve;
  private final VisionSubsystem vision;

  private TestPhase currentPhase;
  private int passCount;
  private int failCount;

  /**
   * Creates a new SubsystemSelfTestCommand.
   *
   * @param swerve the swerve drive subsystem
   * @param vision the vision subsystem
   */
  public SubsystemSelfTestCommand(SwerveSubsystem swerve, VisionSubsystem vision) {
    this.swerve = swerve;
    this.vision = vision;
    // No addRequirements — this is read-only, never conflicts with other commands.
  }

  @Override
  public void initialize() {
    currentPhase = TestPhase.SWERVE_POSITION;
    passCount = 0;
    failCount = 0;
    System.out.println("\n========== SUBSYSTEM SELF-TEST ==========");
  }

  @Override
  public void execute() {
    switch (currentPhase) {
      case SWERVE_POSITION:
        runSwervePositionTest();
        currentPhase = TestPhase.GYRO_CHECK;
        break;
      case GYRO_CHECK:
        runGyroCheckTest();
        currentPhase = TestPhase.VISION_CHECK;
        break;
      case VISION_CHECK:
        runVisionCheckTest();
        currentPhase = TestPhase.COMPLETE;
        break;
      case COMPLETE:
        // Nothing to do; isFinished() will return true.
        break;
    }
  }

  @Override
  public boolean isFinished() {
    return currentPhase == TestPhase.COMPLETE;
  }

  @Override
  public void end(boolean interrupted) {
    String summary =
        String.format(
            "Self-Test %s: %d PASS, %d FAIL",
            interrupted ? "INTERRUPTED" : "COMPLETE", passCount, failCount);
    System.out.println(summary);
    System.out.println("==========================================\n");
    Logger.recordOutput("SelfTest/Summary", summary);
    SmartDashboard.putString("SelfTest/Summary", summary);
  }

  private void runSwervePositionTest() {
    String phaseName = "SwervePosition";
    boolean pass = true;
    SwerveModule[] modules = swerve.getModules();

    if (modules == null || modules.length < 4) {
      pass = false;
    } else {
      for (SwerveModule module : modules) {
        double position = module.absolutePositionCache.getValue();
        if (Double.isNaN(position)) {
          pass = false;
          break;
        }
      }
    }

    recordResult(phaseName, pass);
  }

  private void runGyroCheckTest() {
    String phaseName = "GyroCheck";
    boolean pass;

    double headingDegrees = swerve.getHeading().getDegrees();
    pass = !Double.isNaN(headingDegrees);

    recordResult(phaseName, pass);
  }

  private void runVisionCheckTest() {
    String phaseName = "VisionCheck";
    boolean pass;

    try {
      // Call hasTarget() to verify the subsystem is alive and publishing.
      // We don't require a target to be visible -- just that the subsystem responds.
      boolean hasTarget = vision.hasTarget();
      // We don't require a target to be visible — just that the call didn't throw.
      // Log the actual target status for informational value.
      Logger.recordOutput("SelfTest/VisionHasTarget", hasTarget);
      pass = true;
    } catch (Exception e) {
      pass = false;
    }

    recordResult(phaseName, pass);
  }

  private void recordResult(String phaseName, boolean pass) {
    String result = pass ? "PASS" : "FAIL";
    if (pass) {
      passCount++;
    } else {
      failCount++;
    }

    Logger.recordOutput("SelfTest/" + phaseName, result);
    SmartDashboard.putString("SelfTest/" + phaseName, result);
    System.out.println("  " + phaseName + ": " + result);
  }
}
