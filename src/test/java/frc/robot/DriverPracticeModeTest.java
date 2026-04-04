package frc.robot;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import frc.robot.DriverPracticeMode.Scenario;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link DriverPracticeMode.Scenario}. Validates scenario configuration without requiring
 * HAL or subsystem instantiation. Avoids importing AllianceStationID (requires HAL JNI).
 */
class DriverPracticeModeTest {

  @Test
  void allScenariosHaveNonNullFields() {
    for (Scenario s : Scenario.values()) {
      assertNotNull(s.label, s.name() + " has null label");
      assertNotNull(s.station, s.name() + " has null station");
      assertNotNull(s.startPose, s.name() + " has null startPose");
    }
  }

  @Test
  void sixScenariosExist() {
    assertEquals(6, Scenario.values().length);
  }

  @Test
  void autoScenariosHaveAutoModeTrue() {
    assertTrue(Scenario.FULL_AUTO_BLUE.autoMode);
    assertTrue(Scenario.FULL_AUTO_RED.autoMode);
  }

  @Test
  void teleopScenariosHaveAutoModeFalse() {
    assertFalse(Scenario.TELEOP_BLUE_CENTER.autoMode);
    assertFalse(Scenario.TELEOP_RED_CENTER.autoMode);
    assertFalse(Scenario.TELEOP_BLUE_NEAR_HUB.autoMode);
    assertFalse(Scenario.STRESS_TEST.autoMode);
  }

  @Test
  void blueAllianceScenariosUseBlueStations() {
    // Check station name contains "Blue" without importing AllianceStationID
    assertTrue(Scenario.FULL_AUTO_BLUE.station.name().contains("Blue"));
    assertTrue(Scenario.TELEOP_BLUE_CENTER.station.name().contains("Blue"));
    assertTrue(Scenario.TELEOP_BLUE_NEAR_HUB.station.name().contains("Blue"));
    assertTrue(Scenario.STRESS_TEST.station.name().contains("Blue"));
  }

  @Test
  void redAllianceScenariosUseRedStations() {
    assertTrue(Scenario.FULL_AUTO_RED.station.name().contains("Red"));
    assertTrue(Scenario.TELEOP_RED_CENTER.station.name().contains("Red"));
  }

  @Test
  void startPosesAreWithinFieldBounds() {
    double fieldLength = 16.541; // Constants.kFieldLengthMeters — hardcoded to avoid HAL JNI
    double fieldWidth = 8.21;
    for (Scenario s : Scenario.values()) {
      Pose2d pose = s.startPose;
      assertTrue(
          pose.getX() >= 0 && pose.getX() <= fieldLength,
          s.name() + " X=" + pose.getX() + " out of field bounds");
      assertTrue(
          pose.getY() >= 0 && pose.getY() <= fieldWidth,
          s.name() + " Y=" + pose.getY() + " out of field bounds");
    }
  }

  @Test
  void redScenariosAreMirroredFromBlue() {
    double fieldLength = 16.541; // Constants.kFieldLengthMeters — hardcoded to avoid HAL JNI
    double blueX = Scenario.FULL_AUTO_BLUE.startPose.getX();
    double redX = Scenario.FULL_AUTO_RED.startPose.getX();
    assertEquals(fieldLength - blueX, redX, 0.01, "Red auto X should mirror blue auto X");

    assertEquals(
        Scenario.FULL_AUTO_BLUE.startPose.getY(),
        Scenario.FULL_AUTO_RED.startPose.getY(),
        0.01,
        "Mirrored scenarios should have same Y");
  }

  @Test
  void redScenariosHave180DegreeHeading() {
    assertEquals(180.0, Scenario.FULL_AUTO_RED.startPose.getRotation().getDegrees(), 0.01);
    assertEquals(180.0, Scenario.TELEOP_RED_CENTER.startPose.getRotation().getDegrees(), 0.01);
  }

  @Test
  void blueScenariosHave0DegreeHeading() {
    assertEquals(0.0, Scenario.FULL_AUTO_BLUE.startPose.getRotation().getDegrees(), 0.01);
    assertEquals(0.0, Scenario.TELEOP_BLUE_CENTER.startPose.getRotation().getDegrees(), 0.01);
  }

  @Test
  void stressTestHas45DegreeHeading() {
    assertEquals(45.0, Scenario.STRESS_TEST.startPose.getRotation().getDegrees(), 0.01);
  }

  @Test
  void scenarioLabelsAreUnique() {
    Scenario[] scenarios = Scenario.values();
    for (int i = 0; i < scenarios.length; i++) {
      for (int j = i + 1; j < scenarios.length; j++) {
        assertNotEquals(
            scenarios[i].label, scenarios[j].label, "Duplicate label: " + scenarios[i].label);
      }
    }
  }
}
