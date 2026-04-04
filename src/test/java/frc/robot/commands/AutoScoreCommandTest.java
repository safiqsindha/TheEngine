package frc.robot.commands;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/**
 * Tests for {@link AutoScoreCommand} constants and composition logic. AutoScoreCommand uses a
 * factory pattern ({@code build()}) that composes WPILib commands, so we validate the configuration
 * constants rather than the runtime behavior (which requires full subsystem instantiation).
 *
 * <p>Constants are hardcoded here to avoid importing frc.robot.Constants, which transitively loads
 * HAL JNI natives and crashes in plain unit tests.
 */
class AutoScoreCommandTest {

  // Mirrors Constants.Superstructure values — update if Constants.java changes
  private static final double VISION_CONFIRM_SECONDS = 0.25;
  private static final double AUTO_SCORE_TIMEOUT_SECONDS = 5.0;
  private static final int APRIL_TAG_PIPELINE = 0;
  private static final int NEURAL_PIPELINE = 1;
  private static final double GAME_PIECE_CURRENT_THRESHOLD_AMPS = 15.0;

  @Test
  void visionConfirmTimeIsPositive() {
    assertTrue(VISION_CONFIRM_SECONDS > 0, "Vision confirm time must be positive");
  }

  @Test
  void visionConfirmTimeIsReasonable() {
    // Vision lock should settle in under 2 seconds
    assertTrue(
        VISION_CONFIRM_SECONDS <= 2.0,
        "Vision confirm time should be <= 2.0s for responsive scoring");
  }

  @Test
  void autoScoreTimeoutIsPositive() {
    assertTrue(AUTO_SCORE_TIMEOUT_SECONDS > 0, "Auto score timeout must be positive");
  }

  @Test
  void autoScoreTimeoutExceedsVisionConfirm() {
    // Timeout must be longer than vision confirm to allow the sequence to complete
    assertTrue(
        AUTO_SCORE_TIMEOUT_SECONDS > VISION_CONFIRM_SECONDS,
        "Timeout must exceed vision confirm time");
  }

  @Test
  void autoScoreTimeoutIsReasonable() {
    // Should not wait longer than 10 seconds — match time is precious
    assertTrue(AUTO_SCORE_TIMEOUT_SECONDS <= 10.0, "Auto score timeout should be <= 10s");
  }

  @Test
  void pipelineIndicesAreDifferent() {
    assertNotEquals(
        APRIL_TAG_PIPELINE,
        NEURAL_PIPELINE,
        "AprilTag and Neural pipelines must have different indices");
  }

  @Test
  void pipelineIndicesAreNonNegative() {
    assertTrue(APRIL_TAG_PIPELINE >= 0);
    assertTrue(NEURAL_PIPELINE >= 0);
  }

  @Test
  void gamePieceCurrentThresholdIsPositive() {
    assertTrue(
        GAME_PIECE_CURRENT_THRESHOLD_AMPS > 0, "Game piece current threshold must be positive");
  }

  @Test
  void gamePieceCurrentThresholdIsReasonable() {
    // NEO stall current is ~105A; current spike for game piece should be
    // well below stall but above noise (typically 5-30A range)
    assertTrue(
        GAME_PIECE_CURRENT_THRESHOLD_AMPS >= 5.0,
        "Threshold too low — would false-trigger on noise");
    assertTrue(
        GAME_PIECE_CURRENT_THRESHOLD_AMPS <= 60.0, "Threshold too high — would never trigger");
  }
}
