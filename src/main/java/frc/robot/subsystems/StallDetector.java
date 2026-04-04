package frc.robot.subsystems;

import edu.wpi.first.wpilibj.Timer;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Reusable utility class that monitors motor current and detects stall conditions. Not a subsystem
 * -- intended to be owned and updated by the subsystem that controls the motor.
 *
 * <p>A stall is detected when the motor current exceeds the configured threshold for longer than
 * the configured duration. When a stall is detected, it is logged via AdvantageKit.
 */
public class StallDetector {

  private final String name;
  private final DoubleSupplier currentSupplier;
  private final double thresholdAmps;
  private final double durationThresholdSeconds;
  private final DoubleSupplier clock;

  // Track stall state
  private boolean aboveThreshold = false;
  private double stallStartTime = 0;

  /**
   * Creates a StallDetector with a custom clock source.
   *
   * @param name descriptive name for logging (e.g., "IntakeWheel")
   * @param currentAmps supplier that returns the motor current in amps
   * @param thresholdAmps current threshold above which a stall is suspected
   * @param durationSeconds how long the current must stay above threshold to confirm a stall
   * @param clock supplier that returns the current time in seconds
   */
  public StallDetector(
      String name,
      DoubleSupplier currentAmps,
      double thresholdAmps,
      double durationSeconds,
      DoubleSupplier clock) {
    this.name = name;
    this.currentSupplier = currentAmps;
    this.thresholdAmps = thresholdAmps;
    this.durationThresholdSeconds = durationSeconds;
    this.clock = clock;
  }

  /**
   * Creates a StallDetector using FPGA time.
   *
   * @param name descriptive name for logging (e.g., "IntakeWheel")
   * @param currentAmps supplier that returns the motor current in amps
   * @param thresholdAmps current threshold above which a stall is suspected
   * @param durationSeconds how long the current must stay above threshold to confirm a stall
   */
  public StallDetector(
      String name, DoubleSupplier currentAmps, double thresholdAmps, double durationSeconds) {
    this(name, currentAmps, thresholdAmps, durationSeconds, Timer::getFPGATimestamp);
  }

  /**
   * Read the current and update stall tracking state. Must be called periodically (e.g., from the
   * owning subsystem's {@code periodic()} method).
   */
  public void update() {
    double current = currentSupplier.getAsDouble();

    if (current > thresholdAmps) {
      if (!aboveThreshold) {
        // Just crossed above threshold -- start tracking
        aboveThreshold = true;
        stallStartTime = clock.getAsDouble();
      }

      if (isStalled()) {
        Logger.recordOutput("StallDetector/" + name + "/Stalled", true);
      }
    } else {
      // Current is below threshold -- clear tracking
      aboveThreshold = false;
      stallStartTime = 0;
    }
  }

  /**
   * Whether a stall condition is currently active: current is above threshold AND has been above
   * threshold for longer than the configured duration.
   *
   * @return true if stalled
   */
  public boolean isStalled() {
    if (!aboveThreshold) {
      return false;
    }
    return (clock.getAsDouble() - stallStartTime) >= durationThresholdSeconds;
  }

  /**
   * How long the current has been above the stall threshold, in seconds. Returns 0 if not currently
   * above threshold.
   *
   * @return stall duration in seconds, or 0 if not above threshold
   */
  public double getStallDurationSeconds() {
    if (!aboveThreshold) {
      return 0.0;
    }
    return clock.getAsDouble() - stallStartTime;
  }

  /** Clears all stall tracking state. */
  public void reset() {
    aboveThreshold = false;
    stallStartTime = 0;
  }
}
