package frc.robot.commands;

import static org.junit.jupiter.api.Assertions.*;

import frc.robot.commands.SpeedModeManager.SpeedMode;
import org.junit.jupiter.api.Test;

/** Tests for {@link SpeedModeManager}. */
class SpeedModeManagerTest {

  @Test
  void defaultIsFull_scaleIsOne() {
    SpeedModeManager manager = new SpeedModeManager();
    assertEquals(SpeedMode.FULL, manager.getCurrentMode());
    assertEquals(1.0, manager.getSpeedScale(), 1e-9);
  }

  @Test
  void toggleToPrecision() {
    SpeedModeManager manager = new SpeedModeManager();
    manager.toggle();

    assertEquals(SpeedMode.PRECISION, manager.getCurrentMode());
    assertEquals(0.40, manager.getSpeedScale(), 1e-9);
  }

  @Test
  void toggleBackToFull() {
    SpeedModeManager manager = new SpeedModeManager();
    manager.toggle(); // FULL -> PRECISION
    manager.toggle(); // PRECISION -> FULL

    assertEquals(SpeedMode.FULL, manager.getCurrentMode());
    assertEquals(1.0, manager.getSpeedScale(), 1e-9);
  }

  @Test
  void multipleTogglesCycleCorrectly() {
    SpeedModeManager manager = new SpeedModeManager();

    for (int i = 0; i < 5; i++) {
      manager.toggle();
      assertEquals(SpeedMode.PRECISION, manager.getCurrentMode());
      assertEquals(0.40, manager.getSpeedScale(), 1e-9);

      manager.toggle();
      assertEquals(SpeedMode.FULL, manager.getCurrentMode());
      assertEquals(1.0, manager.getSpeedScale(), 1e-9);
    }
  }
}
