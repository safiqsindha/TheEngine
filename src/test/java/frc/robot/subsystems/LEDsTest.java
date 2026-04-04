package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import frc.robot.Constants;
import frc.robot.subsystems.LEDs.AnimationType;
import frc.robot.subsystems.LEDs.PriorityController;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Tests for the LED priority animation system.
 *
 * <p>Tests the {@link LEDs.PriorityController} directly — a pure-Java class with zero WPILib
 * hardware dependencies — so no HAL initialization or robot simulation is required. The {@link
 * LEDs} subsystem delegates all priority logic to {@link LEDs.PriorityController}, so testing the
 * controller fully covers the behavior.
 */
class LEDsTest {

  private PriorityController controller;

  @BeforeEach
  void setUp() {
    controller = new PriorityController();
  }

  @Test
  @DisplayName("Gate 1: Single animation at priority 1 becomes active")
  void testSetAnimation_singlePriority_animationActive() {
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityDriving);

    assertEquals(
        AnimationType.ENABLED_IDLE,
        controller.getCurrentAnimation(),
        "Animation set at priority 1 should be active");
    assertEquals(Constants.LEDs.kPriorityDriving, controller.getCurrentPriority());
  }

  @Test
  @DisplayName("Gate 2: Higher priority overrides lower priority")
  void testHigherPriority_overridesLower() {
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityDriving); // p=1
    controller.setAnimation(AnimationType.ALIGNING_BLINK, Constants.LEDs.kPriorityAligning); // p=2

    assertEquals(
        AnimationType.ALIGNING_BLINK,
        controller.getCurrentAnimation(),
        "Priority 2 should override priority 1");
    assertEquals(Constants.LEDs.kPriorityAligning, controller.getCurrentPriority());
  }

  @Test
  @DisplayName("Gate 2: Lower priority does not override higher priority")
  void testLowerPriority_doesNotOverrideHigher() {
    controller.setAnimation(AnimationType.ALIGNING_BLINK, Constants.LEDs.kPriorityAligning); // p=2
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityDriving); // p=1

    assertEquals(
        AnimationType.ALIGNING_BLINK,
        controller.getCurrentAnimation(),
        "Lower priority should not override the existing higher priority animation");
  }

  @Test
  @DisplayName("Gate 2: Same priority replaces current animation (most recent wins)")
  void testSamePriority_replacesAnimation() {
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityAligning);
    controller.setAnimation(AnimationType.ALIGNING_BLINK, Constants.LEDs.kPriorityAligning);

    assertEquals(
        AnimationType.ALIGNING_BLINK,
        controller.getCurrentAnimation(),
        "Same priority should replace with the most recent animation");
  }

  @Test
  @DisplayName("Gate 2: clearAnimation() resets to OFF and priority -1")
  void testClearAnimation_resetsToOff() {
    controller.setAnimation(AnimationType.ERROR_FLASH, Constants.LEDs.kPriorityAlert);
    controller.clearAnimation();

    assertEquals(
        AnimationType.OFF,
        controller.getCurrentAnimation(),
        "After clearAnimation(), animation should be OFF");
    assertEquals(
        -1, controller.getCurrentPriority(), "After clearAnimation(), priority should be -1");
  }

  @Test
  @DisplayName("Gate 2: After clear, new low-priority animation can be set")
  void testAfterClear_lowPriorityCanBeSet() {
    controller.setAnimation(AnimationType.ERROR_FLASH, Constants.LEDs.kPriorityAlert);
    controller.clearAnimation();
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityIdle);

    assertEquals(
        AnimationType.ENABLED_IDLE,
        controller.getCurrentAnimation(),
        "After clear, even a priority-0 animation should be accepted");
  }

  @Test
  @DisplayName("Gate 3: Alert priority (3) overrides all lower priorities")
  void testAlertPriority_overridesEverything() {
    controller.setAnimation(AnimationType.DISABLED_PULSE, Constants.LEDs.kPriorityIdle); // p=0
    controller.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityDriving); // p=1
    controller.setAnimation(AnimationType.ALIGNING_BLINK, Constants.LEDs.kPriorityAligning); // p=2
    controller.setAnimation(AnimationType.ERROR_FLASH, Constants.LEDs.kPriorityAlert); // p=3

    assertEquals(
        AnimationType.ERROR_FLASH,
        controller.getCurrentAnimation(),
        "Alert priority (3) should override all lower priorities");
    assertEquals(Constants.LEDs.kPriorityAlert, controller.getCurrentPriority());
  }
}
