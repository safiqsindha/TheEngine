package frc.robot.subsystems;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Tests for FuelDetectionConsumer. Verifies parsing of llpython NetworkTables array, confidence
 * filtering, and 3-frame detection persistence.
 */
class FuelDetectionConsumerTest {

  private FuelDetectionConsumer consumer;

  @BeforeEach
  void setUp() {
    consumer = new FuelDetectionConsumer();
  }

  @Test
  void testParseArray_singleDetection() {
    // llpython format: [numFuel, x1, y1, conf1, ...]
    double[] raw = {1.0, 5.0, 3.0, 0.95};
    consumer.updateFromRawArray(raw); // frame 1
    consumer.updateFromRawArray(raw); // frame 2
    consumer.updateFromRawArray(raw); // frame 3 — persistence met
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(1, detections.size());
    assertEquals(5.0, detections.get(0).getX(), 0.01);
    assertEquals(3.0, detections.get(0).getY(), 0.01);
  }

  @Test
  void testParseArray_multipleDetections() {
    // 3 FUEL detections
    double[] raw = {3.0, 5.0, 3.0, 0.95, 7.0, 4.0, 0.88, 9.0, 2.0, 0.92};
    for (int i = 0; i < 3; i++) consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(3, detections.size());
  }

  @Test
  void testParseArray_emptyArray() {
    // No detections
    double[] raw = {0.0};
    consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertTrue(detections.isEmpty());
  }

  @Test
  void testConfidenceFilter_belowThreshold_rejected() {
    // Detection with 70% confidence should be filtered out (threshold is 80%)
    double[] raw = {1.0, 5.0, 3.0, 0.70};
    for (int i = 0; i < 3; i++) consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertTrue(detections.isEmpty(), "Low confidence detection should be rejected");
  }

  @Test
  void testConfidenceFilter_atThreshold_accepted() {
    // Detection at exactly 80% should be accepted
    double[] raw = {1.0, 5.0, 3.0, 0.80};
    for (int i = 0; i < 3; i++) consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(1, detections.size());
  }

  @Test
  void testPersistence_twoFrames_notYetAvailable() {
    // After only 2 frames, detection should NOT be available
    double[] raw = {1.0, 5.0, 3.0, 0.95};
    consumer.updateFromRawArray(raw); // frame 1
    consumer.updateFromRawArray(raw); // frame 2
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertTrue(detections.isEmpty(), "2 frames should not satisfy 3-frame persistence");
  }

  @Test
  void testPersistence_threeFrames_available() {
    // After 3 consecutive frames, detection should be available
    double[] raw = {1.0, 5.0, 3.0, 0.95};
    for (int i = 0; i < 3; i++) consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(1, detections.size());
  }

  @Test
  void testPersistence_gapResetsCounter() {
    // 2 frames detected, then 1 frame missing, then 1 frame detected = reset to 1
    double[] detected = {1.0, 5.0, 3.0, 0.95};
    double[] empty = {0.0};
    consumer.updateFromRawArray(detected); // frame 1
    consumer.updateFromRawArray(detected); // frame 2
    consumer.updateFromRawArray(empty); // gap — resets counter
    consumer.updateFromRawArray(detected); // frame 1 again
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertTrue(detections.isEmpty(), "Gap should reset persistence counter");
  }

  @Test
  void testMaxDetections_capsAtEight() {
    // Array with 8 high-confidence detections should return exactly 8
    double[] raw = new double[1 + 8 * 3];
    raw[0] = 8.0;
    for (int i = 0; i < 8; i++) {
      raw[1 + i * 3] = i + 1.0;
      raw[2 + i * 3] = 4.0;
      raw[3 + i * 3] = 0.95;
    }
    for (int f = 0; f < 3; f++) consumer.updateFromRawArray(raw);
    List<Translation2d> detections = consumer.getDetectedFuelPositions();
    assertEquals(8, detections.size());
  }

  // ---- Opponent detection tests ----
  // The Wave Robotics YOLOv11n model is fuel-only (single class: fuel ball).
  // getDetectedOpponentPositions() always returns an empty list regardless of
  // what appears in the llpython array.  These tests document that contract.

  @Test
  void testOpponentParsing_singleOpponent_appearsImmediately() {
    // Wave model is fuel-only — even if old-format opponent data were present
    // in the array, getDetectedOpponentPositions() must always be empty.
    double[] raw = {0.0, 1.0, 8.0, 4.0, 0.92};
    consumer.updateFromRawArray(raw);
    assertTrue(
        consumer.getDetectedOpponentPositions().isEmpty(),
        "Wave model is fuel-only: opponents always empty");
  }

  @Test
  void testOpponentParsing_afterFuelSection_correctOffset() {
    // Wave model is fuel-only — extra bytes after fuel section are ignored.
    double[] raw = {1.0, 2.0, 3.0, 0.95, 1.0, 10.0, 5.0, 0.88};
    consumer.updateFromRawArray(raw);
    assertTrue(
        consumer.getDetectedOpponentPositions().isEmpty(),
        "Wave model is fuel-only: opponents always empty");
  }

  @Test
  void testOpponentConfidenceFilter_belowThreshold_rejected() {
    double[] raw = {0.0, 1.0, 8.0, 4.0, 0.70};
    consumer.updateFromRawArray(raw);
    assertTrue(
        consumer.getDetectedOpponentPositions().isEmpty(),
        "Wave model is fuel-only: opponents always empty");
  }

  @Test
  void testOpponentParsing_noOpponentSection_returnsEmpty() {
    // Array ends after fuel data — no opponent section present.
    double[] raw = {1.0, 2.0, 3.0, 0.95};
    for (int i = 0; i < 3; i++) consumer.updateFromRawArray(raw);
    assertTrue(consumer.getDetectedOpponentPositions().isEmpty());
  }

  @Test
  void testOpponentParsing_multipleOpponents() {
    // Wave model is fuel-only — multi-opponent arrays still return empty.
    double[] raw = {0.0, 2.0, 8.0, 4.0, 0.90, 12.0, 4.0, 0.85};
    consumer.updateFromRawArray(raw);
    assertTrue(
        consumer.getDetectedOpponentPositions().isEmpty(),
        "Wave model is fuel-only: opponents always empty");
  }
}
