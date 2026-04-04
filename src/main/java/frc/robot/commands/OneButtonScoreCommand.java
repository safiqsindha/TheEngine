package frc.robot.commands;

import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.Helper;
import frc.robot.subsystems.Flywheel;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;
import org.littletonrobotics.junction.Logger;

/**
 * One-button composite scoring command. Handles the full scoring pipeline: align to AprilTag, wait
 * for vision lock, spin up flywheel, feed game piece, and cooldown. Takes over swerve drive for
 * heading correction throughout the sequence.
 *
 * <p>Overall timeout: 6 seconds regardless of phase.
 */
public class OneButtonScoreCommand extends Command {

  /** Scoring sequence phases. */
  enum Phase {
    ALIGNING,
    WAITING_VISION,
    SPINNING_UP,
    FEEDING,
    COOLDOWN,
    DONE
  }

  private static final double kAlignPGain = 0.05;
  private static final double kHeadingErrorThresholdDeg = 3.0;
  private static final double kVisionTimeoutSeconds = 3.0;
  private static final double kFlywheelTargetRpm = 2800.0;
  private static final double kFeedDurationSeconds = 0.5;
  private static final double kCooldownDurationSeconds = 0.2;
  private static final double kTotalTimeoutSeconds = 6.0;
  private static final double kFlywheelReadyThreshold = 0.10;

  private final SwerveSubsystem swerve;
  private final VisionSubsystem vision;
  private final SuperstructureStateMachine ssm;
  private final Flywheel flywheel;

  private Phase phase;
  private double commandStartTime;
  private double phaseStartTime;

  /**
   * Creates a one-button score command.
   *
   * @param swerve swerve drive subsystem
   * @param vision vision subsystem for AprilTag tracking
   * @param ssm superstructure state machine for scoring requests
   * @param flywheel flywheel subsystem for spinning and feeding
   */
  public OneButtonScoreCommand(
      SwerveSubsystem swerve,
      VisionSubsystem vision,
      SuperstructureStateMachine ssm,
      Flywheel flywheel) {
    this.swerve = swerve;
    this.vision = vision;
    this.ssm = ssm;
    this.flywheel = flywheel;
    addRequirements(swerve);
  }

  @Override
  public void initialize() {
    phase = Phase.ALIGNING;
    commandStartTime = Timer.getFPGATimestamp();
    phaseStartTime = commandStartTime;
    Helper.resetFilters();
    vision.setAprilTagPipeline();
    Logger.recordOutput("OneButtonScore/Phase", phase.name());
  }

  @Override
  public void execute() {
    Helper.updateFilters();

    switch (phase) {
      case ALIGNING:
        executeAligning();
        break;
      case WAITING_VISION:
        executeWaitingVision();
        break;
      case SPINNING_UP:
        executeSpinningUp();
        break;
      case FEEDING:
        executeFeeding();
        break;
      case COOLDOWN:
        executeCooldown();
        break;
      case DONE:
        break;
    }
  }

  private void executeAligning() {
    double txOffset = Helper.getAprilTagAim();
    double rotation = -1.0 * (txOffset * kAlignPGain);
    swerve.drive(new Translation2d(0, 0), rotation, true);

    if (Math.abs(txOffset) < kHeadingErrorThresholdDeg) {
      transitionTo(Phase.WAITING_VISION);
    }
  }

  private void executeWaitingVision() {
    // Maintain heading correction while waiting
    double txOffset = Helper.getAprilTagAim();
    double rotation = -1.0 * (txOffset * kAlignPGain);
    swerve.drive(new Translation2d(0, 0), rotation, true);

    if (vision.isTargetValidFor(1.0)) {
      transitionTo(Phase.SPINNING_UP);
    } else if (Timer.getFPGATimestamp() - phaseStartTime > kVisionTimeoutSeconds) {
      // Vision lock timeout - abort
      transitionTo(Phase.DONE);
    }
  }

  private void executeSpinningUp() {
    // Maintain heading correction
    double txOffset = Helper.getAprilTagAim();
    double rotation = -1.0 * (txOffset * kAlignPGain);
    swerve.drive(new Translation2d(0, 0), rotation, true);

    flywheel.setTargetRpm(kFlywheelTargetRpm);

    double currentRpm = flywheel.getCurrentRpm();
    if (kFlywheelTargetRpm > 0
        && Math.abs(currentRpm - kFlywheelTargetRpm) / kFlywheelTargetRpm
            < kFlywheelReadyThreshold) {
      transitionTo(Phase.FEEDING);
    }
  }

  private void executeFeeding() {
    ssm.requestScore();

    if (Timer.getFPGATimestamp() - phaseStartTime > kFeedDurationSeconds) {
      transitionTo(Phase.COOLDOWN);
    }
  }

  private void executeCooldown() {
    flywheel.setTargetRpm(0);
    ssm.requestIdle();

    if (Timer.getFPGATimestamp() - phaseStartTime > kCooldownDurationSeconds) {
      transitionTo(Phase.DONE);
    }
  }

  private void transitionTo(Phase nextPhase) {
    phase = nextPhase;
    phaseStartTime = Timer.getFPGATimestamp();
    Logger.recordOutput("OneButtonScore/Phase", phase.name());
  }

  @Override
  public boolean isFinished() {
    if (phase == Phase.DONE) {
      return true;
    }
    // Overall 6-second timeout
    if (Timer.getFPGATimestamp() - commandStartTime > kTotalTimeoutSeconds) {
      Logger.recordOutput("OneButtonScore/Phase", "TIMEOUT");
      return true;
    }
    return false;
  }

  @Override
  public void end(boolean interrupted) {
    flywheel.setTargetRpm(0);
    ssm.requestIdle();
    swerve.drive(new Translation2d(0, 0), 0, true);
    Logger.recordOutput("OneButtonScore/Phase", interrupted ? "INTERRUPTED" : "COMPLETE");
  }
}
