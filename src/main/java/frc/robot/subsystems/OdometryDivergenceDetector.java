package frc.robot.subsystems;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.wpilibj.RobotController;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Monitors the gap between vision-reported pose and wheel odometry pose.
 *
 * <p>Fires a warning when the two estimates diverge beyond a threshold, and escalates to a critical
 * alert when the divergence exceeds a higher threshold for a sustained duration. This helps detect
 * encoder slip, vision outliers, or mechanical failures during a match.
 */
public class OdometryDivergenceDetector {

  private static final double WARN_THRESHOLD_M = 0.75;
  private static final double CRITICAL_THRESHOLD_M = 1.5;
  private static final double SUSTAINED_DURATION_S = 1.5;

  private final DoubleSupplier clock;
  private double criticalStartTime = -1;
  private double lastDivergence = 0;

  /**
   * Creates a detector with a custom clock source.
   *
   * @param clock supplier returning the current time in seconds
   */
  public OdometryDivergenceDetector(DoubleSupplier clock) {
    this.clock = clock;
  }

  /** Creates a detector using FPGA time as the clock source. */
  public OdometryDivergenceDetector() {
    this(() -> RobotController.getFPGATime() * 1e-6);
  }

  /**
   * Update the detector with the latest wheel odometry and vision poses.
   *
   * @param wheelOdometry the pose reported by wheel odometry
   * @param visionPose the pose reported by vision
   */
  public void update(Pose2d wheelOdometry, Pose2d visionPose) {
    lastDivergence = wheelOdometry.getTranslation().getDistance(visionPose.getTranslation());

    double now = clock.getAsDouble();

    if (lastDivergence > CRITICAL_THRESHOLD_M) {
      if (criticalStartTime < 0) {
        criticalStartTime = now;
      }
    } else {
      criticalStartTime = -1;
    }

    Logger.recordOutput("Odometry/DivergenceM", lastDivergence);
    Logger.recordOutput("Odometry/Critical", isCritical());
  }

  /**
   * Returns true if the divergence exceeds the warning threshold.
   *
   * @return true if diverging
   */
  public boolean isDiverging() {
    return lastDivergence > WARN_THRESHOLD_M;
  }

  /**
   * Returns true if the divergence has exceeded the critical threshold for the sustained duration.
   *
   * @return true if critically diverged
   */
  public boolean isCritical() {
    if (criticalStartTime < 0) {
      return false;
    }
    return (clock.getAsDouble() - criticalStartTime) > SUSTAINED_DURATION_S;
  }

  /**
   * Returns the most recently computed divergence in meters.
   *
   * @return divergence in meters
   */
  public double getDivergenceMeters() {
    return lastDivergence;
  }

  /** Resets all internal state (divergence, timers). */
  public void reset() {
    criticalStartTime = -1;
    lastDivergence = 0;
  }
}
