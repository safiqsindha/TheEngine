package frc.robot;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import org.littletonrobotics.junction.Logger;

/**
 * Adapter that auto-detects controller type and remaps axes accordingly.
 *
 * <p>Xbox controllers use axes 0-5 (LX, LY, LTrigger, RTrigger, RX, RY). Nintendo Switch Pro
 * Controllers use axes 0-3 (LX, LY, RX, RY) with no analog triggers. This adapter detects which
 * controller is connected and returns the correct axis values for right stick, so the same code
 * works with both.
 *
 * <p>On macOS, the Pro Controller axes often have incorrect center calibration (e.g., resting at
 * -0.82 instead of 0). This adapter auto-calibrates by sampling the first N readings as center
 * offsets, then subtracting them from all subsequent reads.
 *
 * <p>Detection happens once on first call (lazy) by reading the HID device name.
 */
public class ControllerAdapter {

  /** Supported controller types. */
  public enum ControllerType {
    XBOX,
    PRO_CONTROLLER,
    UNKNOWN
  }

  private final CommandXboxController xbox;
  private ControllerType type = null; // null = not yet detected

  // Pro Controller axis indices on macOS HID:
  // Axis 0 = Left X, Axis 1 = Left Y, Axis 2 = Right X, Axis 3 = Right Y
  // (Axes 4-5 are always 0 — no analog triggers)
  private static final int PRO_LEFT_X = 0;
  private static final int PRO_LEFT_Y = 1;
  private static final int PRO_RIGHT_X = 2;
  private static final int PRO_RIGHT_Y = 3;
  private static final int PRO_AXIS_COUNT = 4;

  // Auto-calibration: accumulate center offsets from first N samples
  private static final int CALIBRATION_SAMPLES = 50; // ~1 second at 50Hz
  private final double[] axisAccum = new double[PRO_AXIS_COUNT];
  private final double[] axisCenter = new double[PRO_AXIS_COUNT];
  private int calibrationCount = 0;
  private boolean calibrated = false;

  /**
   * Creates a new ControllerAdapter wrapping a CommandXboxController.
   *
   * @param xbox the WPILib Xbox controller wrapper
   */
  public ControllerAdapter(CommandXboxController xbox) {
    this.xbox = xbox;
  }

  /**
   * Lazily detects the controller type from the HID device name. Called automatically on first axis
   * read. Safe to call multiple times.
   */
  private void detectIfNeeded() {
    if (type != null) {
      return;
    }

    String name = "";
    try {
      name = xbox.getHID().getName();
    } catch (Exception e) {
      // HID not ready yet
    }

    if (name == null || name.isEmpty()) {
      // Don't cache — try again next cycle
      return;
    }

    String lower = name.toLowerCase();
    if (lower.contains("pro controller") || lower.contains("nintendo")) {
      type = ControllerType.PRO_CONTROLLER;
    } else {
      type = ControllerType.XBOX;
    }

    Logger.recordOutput("Controller/Type", type.name());
    Logger.recordOutput("Controller/Name", name);
  }

  /**
   * Accumulates calibration samples for Pro Controller axes. Call every robot cycle. Once enough
   * samples are collected, computes the center offsets and marks calibration complete.
   */
  private void calibrateIfNeeded() {
    if (calibrated || type != ControllerType.PRO_CONTROLLER) {
      return;
    }

    for (int i = 0; i < PRO_AXIS_COUNT; i++) {
      axisAccum[i] += xbox.getHID().getRawAxis(i);
    }
    calibrationCount++;

    if (calibrationCount >= CALIBRATION_SAMPLES) {
      for (int i = 0; i < PRO_AXIS_COUNT; i++) {
        axisCenter[i] = axisAccum[i] / calibrationCount;
      }
      calibrated = true;
      Logger.recordOutput(
          "Controller/CenterOffsets",
          String.format(
              "ax0=%.3f ax1=%.3f ax2=%.3f ax3=%.3f",
              axisCenter[0], axisCenter[1], axisCenter[2], axisCenter[3]));
    }
  }

  /**
   * Read a Pro Controller axis with center-offset correction.
   *
   * @param axisIndex raw HID axis index (0-3)
   * @return corrected value in [-1, 1], or 0 if not yet calibrated
   */
  private double readProAxis(int axisIndex) {
    if (!calibrated) {
      return 0.0; // Don't move until calibrated
    }
    double raw = xbox.getHID().getRawAxis(axisIndex);
    double corrected = raw - axisCenter[axisIndex];
    return MathUtil.clamp(corrected, -1.0, 1.0);
  }

  /** Returns the controller type, or UNKNOWN if not yet detected. */
  public ControllerType getType() {
    detectIfNeeded();
    return type != null ? type : ControllerType.UNKNOWN;
  }

  /**
   * Tick calibration from the drive loop. Call once per cycle so the Pro Controller calibration
   * accumulates samples at startup. No-ops after calibration completes.
   */
  public void tick() {
    detectIfNeeded();
    calibrateIfNeeded();
  }

  /** Left stick X axis. Xbox: axis 0 via WPILib. Pro Controller: axis 0 with calibration. */
  public double getLeftX() {
    detectIfNeeded();
    calibrateIfNeeded();
    if (type == ControllerType.PRO_CONTROLLER) {
      return readProAxis(PRO_LEFT_X);
    }
    return xbox.getLeftX();
  }

  /** Left stick Y axis. Xbox: axis 1 via WPILib. Pro Controller: axis 1 with calibration. */
  public double getLeftY() {
    detectIfNeeded();
    calibrateIfNeeded();
    if (type == ControllerType.PRO_CONTROLLER) {
      return readProAxis(PRO_LEFT_Y);
    }
    return xbox.getLeftY();
  }

  /**
   * Right stick X axis. Xbox = axis 4 via WPILib, Pro Controller = axis 2 with calibration.
   *
   * <p>Falls back to Xbox mapping if controller not yet detected.
   */
  public double getRightX() {
    detectIfNeeded();
    calibrateIfNeeded();
    if (type == ControllerType.PRO_CONTROLLER) {
      return readProAxis(PRO_RIGHT_X);
    }
    return xbox.getRightX(); // Xbox axis 4
  }

  /**
   * Right stick Y axis. Xbox = axis 5 via WPILib, Pro Controller = axis 3 with calibration.
   *
   * <p>Falls back to Xbox mapping if controller not yet detected.
   */
  public double getRightY() {
    detectIfNeeded();
    calibrateIfNeeded();
    if (type == ControllerType.PRO_CONTROLLER) {
      return readProAxis(PRO_RIGHT_Y);
    }
    return xbox.getRightY(); // Xbox axis 5
  }

  /** Returns the underlying CommandXboxController for button bindings. */
  public CommandXboxController getXbox() {
    return xbox;
  }
}
