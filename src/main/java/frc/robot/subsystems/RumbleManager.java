package frc.robot.subsystems;

import java.util.function.DoubleConsumer;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * Manages Xbox controller rumble patterns for driver haptic feedback. Each pattern is defined as a
 * sequence of (intensity, durationMs) segments. Call {@link #update()} every robot cycle to advance
 * through the active pattern.
 *
 * <p>Accepts a {@link DoubleSupplier} for time and a {@link DoubleConsumer} for rumble output so
 * that tests can capture behavior without a real controller.
 */
public class RumbleManager {

  /** Available rumble feedback patterns. */
  public enum RumblePattern {
    /** 0.3s strong pulse. */
    GAME_PIECE_ACQUIRED,
    /** 0.5s moderate pulse. */
    VISION_LOCK,
    /** Double pulse: 0.15s on, 0.1s off, 0.15s on. */
    AUTO_ALIGN_COMPLETE,
    /** Continuous light rumble (0.3 intensity). */
    BROWNOUT_WARNING,
    /** 0.8s strong pulse. */
    SCORING_COMPLETE,
    /** Triple quick pulse. */
    ENDGAME_WARNING
  }

  /**
   * A single segment in a rumble pattern: an intensity level held for a duration.
   *
   * @param intensity rumble intensity (0.0 to 1.0)
   * @param durationMs how long to hold this intensity in milliseconds
   */
  private record Segment(double intensity, double durationMs) {}

  private static final Segment[][] PATTERNS = {
    // GAME_PIECE_ACQUIRED: 0.3s strong pulse
    {new Segment(1.0, 300)},
    // VISION_LOCK: 0.5s moderate pulse
    {new Segment(0.6, 500)},
    // AUTO_ALIGN_COMPLETE: double pulse 0.15s on, 0.1s off, 0.15s on
    {new Segment(1.0, 150), new Segment(0.0, 100), new Segment(1.0, 150)},
    // BROWNOUT_WARNING: continuous light rumble
    {new Segment(0.3, 2000)},
    // SCORING_COMPLETE: 0.8s strong pulse
    {new Segment(1.0, 800)},
    // ENDGAME_WARNING: triple quick pulse
    {
      new Segment(1.0, 100),
      new Segment(0.0, 80),
      new Segment(1.0, 100),
      new Segment(0.0, 80),
      new Segment(1.0, 100)
    },
  };

  private final DoubleSupplier clock;
  private final DoubleConsumer rumbleOutput;

  private RumblePattern currentPattern;
  private Segment[] currentSegments;
  private int segmentIndex;
  private double segmentStartTimeMs;
  private boolean active;

  /**
   * Creates a RumbleManager.
   *
   * @param clock supplies the current time in seconds (e.g. Timer::getFPGATimestamp)
   * @param rumbleOutput consumes the rumble intensity value (0.0 to 1.0)
   */
  public RumbleManager(DoubleSupplier clock, DoubleConsumer rumbleOutput) {
    this.clock = clock;
    this.rumbleOutput = rumbleOutput;
    this.active = false;
    this.currentPattern = null;
  }

  /**
   * Request a rumble pattern. Overrides any currently active pattern.
   *
   * @param pattern the pattern to play
   */
  public void request(RumblePattern pattern) {
    currentPattern = pattern;
    currentSegments = PATTERNS[pattern.ordinal()];
    segmentIndex = 0;
    segmentStartTimeMs = clock.getAsDouble() * 1000.0;
    active = true;
    rumbleOutput.accept(currentSegments[0].intensity);
  }

  /** Advance the active pattern based on elapsed time. Call every robot cycle. */
  public void update() {
    if (!active) {
      Logger.recordOutput("Driver/RumbleActive", false);
      return;
    }

    double nowMs = clock.getAsDouble() * 1000.0;
    double elapsed = nowMs - segmentStartTimeMs;

    // Advance through segments whose duration has passed
    while (active && elapsed >= currentSegments[segmentIndex].durationMs) {
      elapsed -= currentSegments[segmentIndex].durationMs;
      segmentStartTimeMs += currentSegments[segmentIndex].durationMs;
      segmentIndex++;

      if (segmentIndex >= currentSegments.length) {
        // Pattern complete
        active = false;
        currentPattern = null;
        rumbleOutput.accept(0.0);
        Logger.recordOutput("Driver/RumbleActive", false);
        return;
      }
    }

    if (active) {
      rumbleOutput.accept(currentSegments[segmentIndex].intensity);
    }

    Logger.recordOutput("Driver/RumbleActive", active);
  }

  /** Immediately cancel any active pattern and set rumble to zero. */
  public void stop() {
    active = false;
    currentPattern = null;
    rumbleOutput.accept(0.0);
  }

  /** Whether a rumble pattern is currently playing. */
  public boolean isActive() {
    return active;
  }

  /**
   * The currently playing rumble pattern, or null if none.
   *
   * @return current pattern or null
   */
  public RumblePattern getCurrentPattern() {
    return currentPattern;
  }
}
