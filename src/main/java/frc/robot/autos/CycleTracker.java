package frc.robot.autos;

import edu.wpi.first.wpilibj.Timer;
import java.util.ArrayList;
import java.util.List;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Tracks autonomous cycle performance (pickup to score to pickup to score).
 *
 * <p>A complete cycle: {@link #startCycle()} -> {@link #markPickup()} -> {@link #markScore()}.
 * Cycle time is measured from {@code startCycle()} to {@code markScore()}.
 */
public class CycleTracker {

  /** Phase within a single cycle. */
  public enum CyclePhase {
    IDLE,
    SEEKING,
    CARRYING,
    SCORING
  }

  private final DoubleSupplier clock;
  private CyclePhase currentPhase = CyclePhase.IDLE;
  private double cycleStartTime = 0.0;
  private final List<Double> cycleTimes = new ArrayList<>();

  /**
   * Creates a CycleTracker with a custom clock (for testability).
   *
   * @param clock supplier returning the current time in seconds
   */
  public CycleTracker(DoubleSupplier clock) {
    this.clock = clock;
  }

  /** Creates a CycleTracker using the FPGA timestamp as the clock. */
  public CycleTracker() {
    this(Timer::getFPGATimestamp);
  }

  /** Begin seeking a game piece (IDLE -> SEEKING). */
  public void startCycle() {
    if (currentPhase != CyclePhase.IDLE) {
      return;
    }
    currentPhase = CyclePhase.SEEKING;
    cycleStartTime = clock.getAsDouble();
  }

  /** Game piece acquired (SEEKING -> CARRYING). */
  public void markPickup() {
    if (currentPhase != CyclePhase.SEEKING) {
      return;
    }
    currentPhase = CyclePhase.CARRYING;
  }

  /** Score completed (CARRYING -> SCORING -> IDLE, cycle done). */
  public void markScore() {
    if (currentPhase != CyclePhase.CARRYING) {
      return;
    }
    currentPhase = CyclePhase.SCORING;
    double elapsed = clock.getAsDouble() - cycleStartTime;
    cycleTimes.add(elapsed);
    currentPhase = CyclePhase.IDLE;
  }

  /** Clear all state. */
  public void reset() {
    currentPhase = CyclePhase.IDLE;
    cycleStartTime = 0.0;
    cycleTimes.clear();
  }

  /** Returns the number of completed cycles. */
  public int getCycleCount() {
    return cycleTimes.size();
  }

  /** Returns the last completed cycle time in seconds, or 0 if none. */
  public double getLastCycleTimeSeconds() {
    if (cycleTimes.isEmpty()) {
      return 0.0;
    }
    return cycleTimes.get(cycleTimes.size() - 1);
  }

  /** Returns the average cycle time in seconds, or 0 if none. */
  public double getAverageCycleTimeSeconds() {
    if (cycleTimes.isEmpty()) {
      return 0.0;
    }
    double sum = 0.0;
    for (double t : cycleTimes) {
      sum += t;
    }
    return sum / cycleTimes.size();
  }

  /** Returns the current cycle phase. */
  public CyclePhase getCurrentPhase() {
    return currentPhase;
  }

  /** Publish all metrics to AdvantageKit. */
  public void logToAdvantageKit() {
    Logger.recordOutput("Auto/CycleTracker/Phase", currentPhase.name());
    Logger.recordOutput("Auto/CycleTracker/CycleCount", getCycleCount());
    Logger.recordOutput("Auto/CycleTracker/LastCycleTime", getLastCycleTimeSeconds());
    Logger.recordOutput("Auto/CycleTracker/AverageCycleTime", getAverageCycleTimeSeconds());
  }
}
