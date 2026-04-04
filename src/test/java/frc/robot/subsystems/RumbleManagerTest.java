package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import frc.robot.subsystems.RumbleManager.RumblePattern;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link RumbleManager}. Uses a mutable time supplier and a capturing consumer to verify
 * pattern playback without hardware.
 */
class RumbleManagerTest {

  private double currentTimeSeconds;
  private final List<Double> capturedIntensities = new ArrayList<>();
  private final AtomicReference<Double> lastIntensity = new AtomicReference<>(0.0);
  private RumbleManager manager;

  @BeforeEach
  void setUp() {
    currentTimeSeconds = 0.0;
    capturedIntensities.clear();
    lastIntensity.set(0.0);
    manager =
        new RumbleManager(
            () -> currentTimeSeconds,
            intensity -> {
              capturedIntensities.add(intensity);
              lastIntensity.set(intensity);
            });
  }

  @Test
  void gamePieceAcquired_isActiveAndPatternMatches() {
    manager.request(RumblePattern.GAME_PIECE_ACQUIRED);
    manager.update();

    assertTrue(manager.isActive());
    assertEquals(RumblePattern.GAME_PIECE_ACQUIRED, manager.getCurrentPattern());
  }

  @Test
  void gamePieceAcquired_completesAfter300ms() {
    manager.request(RumblePattern.GAME_PIECE_ACQUIRED);
    manager.update();
    assertTrue(manager.isActive());

    // Advance past 0.3s
    currentTimeSeconds = 0.31;
    manager.update();

    assertFalse(manager.isActive());
    assertNull(manager.getCurrentPattern());
    assertEquals(0.0, lastIntensity.get(), 1e-9);
  }

  @Test
  void newRequest_overridesCurrentPattern() {
    manager.request(RumblePattern.SCORING_COMPLETE);
    manager.update();
    assertTrue(manager.isActive());
    assertEquals(RumblePattern.SCORING_COMPLETE, manager.getCurrentPattern());

    // Override with a different pattern mid-play
    currentTimeSeconds = 0.1;
    manager.request(RumblePattern.VISION_LOCK);
    manager.update();

    assertTrue(manager.isActive());
    assertEquals(RumblePattern.VISION_LOCK, manager.getCurrentPattern());
  }

  @Test
  void stop_immediatelyClears() {
    manager.request(RumblePattern.GAME_PIECE_ACQUIRED);
    manager.update();
    assertTrue(manager.isActive());

    manager.stop();

    assertFalse(manager.isActive());
    assertNull(manager.getCurrentPattern());
    assertEquals(0.0, lastIntensity.get(), 1e-9);
  }

  @Test
  void autoAlignComplete_doublePulsePattern() {
    // AUTO_ALIGN_COMPLETE: 0.15s on, 0.1s off, 0.15s on
    manager.request(RumblePattern.AUTO_ALIGN_COMPLETE);

    // First segment: intensity high
    manager.update();
    assertTrue(manager.isActive());
    assertEquals(1.0, lastIntensity.get(), 1e-9);

    // During gap (0.15s into pattern): should be at segment 2 (intensity 0)
    currentTimeSeconds = 0.16;
    manager.update();
    assertTrue(manager.isActive());
    assertEquals(0.0, lastIntensity.get(), 1e-9);

    // During second pulse (0.26s into pattern): should be at segment 3 (intensity 1)
    currentTimeSeconds = 0.26;
    manager.update();
    assertTrue(manager.isActive());
    assertEquals(1.0, lastIntensity.get(), 1e-9);

    // After pattern completes (0.41s into pattern): done
    currentTimeSeconds = 0.41;
    manager.update();
    assertFalse(manager.isActive());
    assertEquals(0.0, lastIntensity.get(), 1e-9);
  }

  @Test
  void noRequest_updateDoesNothing() {
    manager.update();

    assertFalse(manager.isActive());
    assertNull(manager.getCurrentPattern());
  }
}
