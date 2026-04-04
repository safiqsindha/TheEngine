package frc.robot.commands;

import org.littletonrobotics.junction.Logger;

/**
 * Manages a toggle between full-speed and precision driving modes. Precision mode scales driver
 * input by {@link #PRECISION_SCALE} for fine-grained control during alignment or scoring.
 */
public class SpeedModeManager {

  /** Available speed modes. */
  public enum SpeedMode {
    /** Full speed (scale 1.0). */
    FULL,
    /** Precision speed (scale 0.40). */
    PRECISION
  }

  private static final double PRECISION_SCALE = 0.40;

  private SpeedMode current = SpeedMode.FULL;

  /** Toggle between FULL and PRECISION modes. */
  public void toggle() {
    current = (current == SpeedMode.FULL) ? SpeedMode.PRECISION : SpeedMode.FULL;
    Logger.recordOutput("Driver/SpeedMode", current.name());
  }

  /**
   * The current speed mode.
   *
   * @return current mode
   */
  public SpeedMode getCurrentMode() {
    return current;
  }

  /**
   * The speed scale factor for the current mode.
   *
   * @return 1.0 for FULL, 0.40 for PRECISION
   */
  public double getSpeedScale() {
    return current == SpeedMode.FULL ? 1.0 : PRECISION_SCALE;
  }
}
