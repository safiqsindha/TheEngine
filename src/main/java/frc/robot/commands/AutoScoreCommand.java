package frc.robot.commands;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import frc.robot.Constants;
import frc.robot.commands.flywheel.FlywheelAim;
import frc.robot.commands.flywheel.FlywheelAutoFeed;
import frc.robot.subsystems.Conveyor;
import frc.robot.subsystems.Flywheel;
import frc.robot.subsystems.LEDs;
import frc.robot.subsystems.LEDs.AnimationType;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;
import org.littletonrobotics.junction.Logger;

/**
 * Fully automated scoring sequence using vision alignment.
 *
 * <p>Sequence (all within a {@link Constants.Superstructure#kAutoScoreTimeoutSeconds}-second
 * window):
 *
 * <ol>
 *   <li><b>Aim</b> — {@link FlywheelAim} rotates the robot toward the AprilTag target and the
 *       flywheel spins up concurrently.
 *   <li><b>Vision confirm</b> — Wait until the Limelight AprilTag has been continuously valid for
 *       {@link Constants.Superstructure#kVisionConfirmSeconds}. This guards against false targets.
 *   <li><b>Feed</b> — {@link FlywheelAutoFeed} feeds the game piece once the flywheel is at speed.
 *   <li><b>Retract</b> — Notify the SSM that scoring is complete; return to IDLE.
 * </ol>
 *
 * <p>If the sequence times out before completing, the LEDs flash an error pattern and the SSM is
 * forced back to IDLE so the driver can retry manually.
 *
 * <p>This command does NOT require {@link SuperstructureStateMachine} as a WPILib subsystem (the
 * SSM is a pure state tracker), but it does call {@link SuperstructureStateMachine#requestScore()}
 * and {@link SuperstructureStateMachine#requestIdle()} to keep the state machine in sync.
 */
public class AutoScoreCommand extends Command {

  /**
   * Build the AutoScoreCommand as a composed sequential command.
   *
   * @param swerve swerve subsystem
   * @param flywheel flywheel subsystem
   * @param conveyor conveyor subsystem
   * @param vision vision subsystem (provides AprilTag lock confirmation)
   * @param ssm superstructure state machine (state notifications only)
   * @param leds LED subsystem (error feedback on timeout)
   * @return composed command with timeout
   */
  public static Command build(
      SwerveSubsystem swerve,
      Flywheel flywheel,
      Conveyor conveyor,
      VisionSubsystem vision,
      SuperstructureStateMachine ssm,
      LEDs leds) {

    Command aimAndSpin =
        Commands.parallel(
            new FlywheelAim(swerve),
            // Wait inside the parallel for vision lock; FlywheelAim runs until interrupted
            Commands.waitUntil(
                () -> vision.isTargetValidFor(Constants.Superstructure.kVisionConfirmSeconds)));

    Command feedShot = new FlywheelAutoFeed(flywheel, conveyor).withTimeout(2.0);

    Command retract =
        Commands.runOnce(
            () -> {
              ssm.requestIdle();
              Logger.recordOutput("AutoScore/Result", "SUCCESS");
            });

    Command onError =
        Commands.runOnce(
                () -> {
                  ssm.requestIdle();
                  Logger.recordOutput("AutoScore/Result", "TIMEOUT");
                })
            .andThen(
                Commands.run(
                        () ->
                            leds.setAnimation(
                                AnimationType.ERROR_FLASH, Constants.LEDs.kPriorityAlert),
                        leds)
                    .withTimeout(1.5));

    Command sequence =
        Commands.sequence(
            Commands.runOnce(
                () -> {
                  ssm.requestScore();
                  Logger.recordOutput("AutoScore/State", "AIMING");
                }),
            aimAndSpin,
            Commands.runOnce(() -> Logger.recordOutput("AutoScore/State", "FEEDING")),
            feedShot,
            retract);

    // Race the full sequence against the timeout; on timeout run the error handler
    return Commands.race(
        sequence,
        Commands.sequence(
            Commands.waitSeconds(Constants.Superstructure.kAutoScoreTimeoutSeconds), onError));
  }

  // Private constructor — use build() factory method
  private AutoScoreCommand() {}
}
