package frc.robot.commands;

import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.Command;
import frc.robot.autos.AutonomousStrategy;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;
import org.littletonrobotics.junction.Logger;

/**
 * Autonomous wrapper that tries strategies in order, falling back if one fails:
 *
 * <ol>
 *   <li><b>FULL_AUTO</b> — {@link FullAutonomousCommand} (YOLO + pathfinding + strategy), up to
 *       13s.
 *   <li><b>SAFE_MODE</b> — Simple timed drive forward.
 *   <li><b>STOPPED</b> — Do nothing safely.
 * </ol>
 *
 * <p>If the active command finishes unexpectedly early (e.g. NO_TARGETS or error), the next tier is
 * activated. Every transition is logged via AdvantageKit.
 */
public class AutonomousFallbackCommand extends Command {

  /** Fallback tiers, tried in order. */
  public enum FallbackTier {
    FULL_AUTO,
    SAFE_MODE,
    STOPPED
  }

  /** Maximum time (seconds) to wait for FULL_AUTO before it is considered done on its own. */
  private static final double FULL_AUTO_TIMEOUT_SECONDS = 13.0;

  /** Speed (m/s) for the safe-mode drive forward. */
  private static final double SAFE_DRIVE_SPEED_MPS = 1.0;

  private final SwerveSubsystem swerve;
  private final SuperstructureStateMachine ssm;
  private final AutonomousStrategy strategy;

  private FallbackTier currentTier;
  private Command activeCommand;
  private final Timer tierTimer = new Timer();

  /**
   * @param swerve swerve subsystem
   * @param ssm superstructure state machine
   * @param strategy autonomous decision engine
   */
  public AutonomousFallbackCommand(
      SwerveSubsystem swerve, SuperstructureStateMachine ssm, AutonomousStrategy strategy) {
    this.swerve = swerve;
    this.ssm = ssm;
    this.strategy = strategy;
    // Do NOT addRequirements — inner commands handle their own subsystem requirements.
  }

  @Override
  public void initialize() {
    transitionTo(FallbackTier.FULL_AUTO);
  }

  @Override
  public void execute() {
    if (activeCommand == null) {
      return;
    }

    activeCommand.execute();

    switch (currentTier) {
      case FULL_AUTO -> {
        // If the full-auto command finished on its own before 13s, it hit NO_TARGETS or an error.
        if (activeCommand.isFinished() && !tierTimer.hasElapsed(FULL_AUTO_TIMEOUT_SECONDS)) {
          Logger.recordOutput("Auto/FallbackReason", "FullAuto ended early");
          activeCommand.end(false);
          transitionTo(FallbackTier.SAFE_MODE);
        }
      }
      case SAFE_MODE -> {
        if (activeCommand.isFinished()) {
          activeCommand.end(false);
          transitionTo(FallbackTier.STOPPED);
        }
      }
      case STOPPED -> {
        // Nothing to monitor.
      }
    }
  }

  @Override
  public boolean isFinished() {
    // Run until the auto period ends.
    return false;
  }

  @Override
  public void end(boolean interrupted) {
    if (activeCommand != null) {
      activeCommand.end(true);
      activeCommand = null;
    }
    Logger.recordOutput("Auto/FallbackTier", "ENDED");
  }

  // ---- helpers ----

  private void transitionTo(FallbackTier tier) {
    currentTier = tier;
    Logger.recordOutput("Auto/FallbackTier", tier.name());
    tierTimer.restart();

    switch (tier) {
      case FULL_AUTO -> {
        activeCommand = new FullAutonomousCommand(swerve, ssm, strategy);
        activeCommand.initialize();
      }
      case SAFE_MODE -> {
        activeCommand = createSafeDriveCommand();
        activeCommand.initialize();
      }
      case STOPPED -> {
        swerve.drive(new Translation2d(), 0.0, false);
        activeCommand = null;
      }
    }
  }

  /**
   * Creates a simple timed drive-forward command as a safe fallback. Drives at a low constant speed
   * for 3 seconds then stops.
   */
  private Command createSafeDriveCommand() {
    return swerve
        .run(() -> swerve.drive(new Translation2d(SAFE_DRIVE_SPEED_MPS, 0.0), 0.0, true))
        .withTimeout(3.0)
        .withName("SafeDriveForward");
  }

  /** Returns the currently active fallback tier (for testing / diagnostics). */
  public FallbackTier getCurrentTier() {
    return currentTier;
  }
}
