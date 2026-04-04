package frc.robot.subsystems;

import edu.wpi.first.wpilibj.AddressableLED;
import edu.wpi.first.wpilibj.AddressableLEDBuffer;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import org.littletonrobotics.junction.Logger;

/**
 * LED subsystem with priority-based animation system.
 *
 * <p>Adopted from 1678 (state mapping) and Spectrum 3847 (priority override). Higher priority
 * animations always override lower priority ones. Same priority = most recent wins.
 *
 * <p>Priority levels (from Constants.LEDs):
 *
 * <ul>
 *   <li>0 (lowest): Disabled pulse, idle breathing
 *   <li>1: Driving indicators, mode display
 *   <li>2: Aligning, intake active
 *   <li>3 (highest): Error/no-tag, game piece scored
 * </ul>
 */
public class LEDs extends SubsystemBase {

  /** Available animation types. */
  public enum AnimationType {
    OFF,
    DISABLED_PULSE,
    ENABLED_IDLE,
    DRIVING_BREATHE,
    ALIGNING_BLINK,
    SCORED_FLASH,
    ACQUIRED_FLASH,
    ERROR_FLASH
  }

  /**
   * Pure-Java priority animation state tracker with zero WPILib hardware dependencies. Extracted
   * from {@link LEDs} so that unit tests can verify the priority logic without HAL initialization
   * or CommandScheduler/SubsystemBase involvement.
   *
   * <p>This is the Spectrum 3847 pattern: higher priority always wins; same priority replaces;
   * {@link #clearAnimation()} fully resets to {@link AnimationType#OFF}.
   */
  public static final class PriorityController {

    private int currentPriority = -1;
    private AnimationType currentAnimation = AnimationType.OFF;

    /**
     * Request an animation at a given priority. Only applies if {@code priority >=} the current
     * priority.
     *
     * @param animation desired animation
     * @param priority priority level (0–3)
     */
    public void setAnimation(AnimationType animation, int priority) {
      if (priority >= currentPriority) {
        currentAnimation = animation;
        currentPriority = priority;
      }
    }

    /** Force-clear the current animation and reset priority to -1. */
    public void clearAnimation() {
      currentAnimation = AnimationType.OFF;
      currentPriority = -1;
    }

    /** The currently active animation. */
    public AnimationType getCurrentAnimation() {
      return currentAnimation;
    }

    /** The currently active priority (-1 when cleared). */
    public int getCurrentPriority() {
      return currentPriority;
    }
  }

  private final AddressableLED led;
  private final AddressableLEDBuffer buffer;

  // Delegates all priority tracking to PriorityController (pure Java, testable without HAL).
  private final PriorityController controller = new PriorityController();

  // Tracks when the current animation started, for time-based animations (pulse/blink).
  private double animationStartTime = 0;

  /** Creates the LED subsystem. */
  public LEDs() {
    led = new AddressableLED(Constants.LEDs.kLedPort);
    buffer = new AddressableLEDBuffer(Constants.LEDs.kLedLength);
    led.setLength(buffer.getLength());
    led.setData(buffer);
    led.start();
  }

  @Override
  public void periodic() {
    double time = Timer.getFPGATimestamp() - animationStartTime;

    switch (controller.getCurrentAnimation()) {
      case DISABLED_PULSE:
        applyPulse(0, 0, 255, time, 2.0); // Blue, 2s period
        break;
      case ENABLED_IDLE:
        applySolid(0, 180, 0); // Solid green
        break;
      case DRIVING_BREATHE:
        applyPulse(0, 200, 0, time, 1.5); // Green breathing
        break;
      case ALIGNING_BLINK:
        applyBlink(255, 200, 0, time, 0.15); // Fast yellow blink
        break;
      case SCORED_FLASH:
        applyBlink(255, 255, 255, time, 0.08); // Rapid white flash
        break;
      case ACQUIRED_FLASH:
        applyBlink(0, 255, 0, time, 0.1); // Rapid green flash
        break;
      case ERROR_FLASH:
        applyBlink(255, 0, 0, time, 0.08); // Rapid red flash
        break;
      case OFF:
      default:
        applySolid(0, 0, 0);
        break;
    }

    led.setData(buffer);
    Logger.recordOutput("LEDs/Animation", controller.getCurrentAnimation().name());
    Logger.recordOutput("LEDs/Priority", controller.getCurrentPriority());
  }

  /**
   * Request an LED animation. Only applies if the priority is >= current priority. This implements
   * the Spectrum 3847 priority override pattern.
   *
   * @param animation the desired animation
   * @param priority the priority level (0-3)
   */
  public void setAnimation(AnimationType animation, int priority) {
    boolean changed = priority >= controller.getCurrentPriority();
    controller.setAnimation(animation, priority);
    if (changed) {
      animationStartTime = Timer.getFPGATimestamp();
    }
  }

  /** Force-clear the current animation. Used when transitioning robot modes. */
  public void clearAnimation() {
    controller.clearAnimation();
  }

  /** The currently active animation type. Exposed for dashboard logging. */
  public AnimationType getCurrentAnimation() {
    return controller.getCurrentAnimation();
  }

  /** The currently active priority level (-1 when cleared). */
  public int getCurrentPriority() {
    return controller.getCurrentPriority();
  }

  // ─── Animation primitives ───

  private void applySolid(int r, int g, int b) {
    for (int i = 0; i < buffer.getLength(); i++) {
      buffer.setRGB(i, r, g, b);
    }
  }

  private void applyPulse(int r, int g, int b, double time, double periodSeconds) {
    double brightness = (Math.sin(2 * Math.PI * time / periodSeconds) + 1.0) / 2.0;
    for (int i = 0; i < buffer.getLength(); i++) {
      buffer.setRGB(i, (int) (r * brightness), (int) (g * brightness), (int) (b * brightness));
    }
  }

  private void applyBlink(int r, int g, int b, double time, double halfPeriodSeconds) {
    boolean on = ((int) (time / halfPeriodSeconds)) % 2 == 0;
    if (on) {
      applySolid(r, g, b);
    } else {
      applySolid(0, 0, 0);
    }
  }
}
