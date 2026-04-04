package frc.robot.autos;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Unit tests for GameState's immutable builder. No hardware or HAL dependency. */
class GameStateTest {

  @Test
  void testDefaultState_hasExpectedValues() {
    GameState state = new GameState();
    assertEquals(0.0, state.getRobotPose().getX(), 1e-9);
    assertEquals(0.0, state.getRobotPose().getY(), 1e-9);
    assertEquals(0, state.getFuelHeld());
    assertFalse(state.isHubActive());
    assertEquals(150.0, state.getTimeRemaining(), 1e-9);
    assertTrue(state.getDetectedFuel().isEmpty());
    assertTrue(state.getDetectedOpponents().isEmpty());
  }

  @Test
  void testWithRobotPose_changesPose_preservesOtherFields() {
    GameState original = new GameState().withFuelHeld(2).withHubActive(true);
    Pose2d newPose = new Pose2d(3.0, 4.0, Rotation2d.fromDegrees(90));
    GameState updated = original.withRobotPose(newPose);

    assertEquals(3.0, updated.getRobotPose().getX(), 1e-9);
    assertEquals(4.0, updated.getRobotPose().getY(), 1e-9);
    assertEquals(2, updated.getFuelHeld());
    assertTrue(updated.isHubActive());
  }

  @Test
  void testWithFuelHeld_changesFuel_doesNotMutateOriginal() {
    GameState original = new GameState();
    GameState updated = original.withFuelHeld(5);

    assertEquals(0, original.getFuelHeld());
    assertEquals(5, updated.getFuelHeld());
  }

  @Test
  void testWithHubActive_togglesHub() {
    GameState inactive = new GameState().withHubActive(false);
    GameState active = inactive.withHubActive(true);

    assertFalse(inactive.isHubActive());
    assertTrue(active.isHubActive());
  }

  @Test
  void testWithTimeRemaining_changesTime() {
    GameState state = new GameState().withTimeRemaining(30.0);
    assertEquals(30.0, state.getTimeRemaining(), 1e-9);
  }

  @Test
  void testWithDetectedFuel_storesList() {
    List<Translation2d> fuel = List.of(new Translation2d(2.0, 3.0), new Translation2d(5.0, 1.0));
    GameState state = new GameState().withDetectedFuel(fuel);

    assertEquals(2, state.getDetectedFuel().size());
    assertEquals(2.0, state.getDetectedFuel().get(0).getX(), 1e-9);
  }

  @Test
  void testWithDetectedOpponents_storesList() {
    List<Translation2d> opponents = List.of(new Translation2d(8.0, 4.0));
    GameState state = new GameState().withDetectedOpponents(opponents);

    assertEquals(1, state.getDetectedOpponents().size());
    assertEquals(8.0, state.getDetectedOpponents().get(0).getX(), 1e-9);
  }

  @Test
  void testWithDetectedFuel_returnsDefensiveCopy() {
    List<Translation2d> fuel = List.of(new Translation2d(2.0, 3.0));
    GameState state = new GameState().withDetectedFuel(fuel);
    // Should throw if unmodifiable — the returned list must not allow mutation
    assertThrows(
        UnsupportedOperationException.class,
        () -> state.getDetectedFuel().add(new Translation2d()));
  }

  @Test
  void testChainedBuilds_allFieldsSet() {
    Pose2d pose = new Pose2d(1.0, 2.0, new Rotation2d());
    GameState state =
        new GameState()
            .withRobotPose(pose)
            .withFuelHeld(3)
            .withHubActive(true)
            .withTimeRemaining(45.0)
            .withDetectedFuel(List.of(new Translation2d(3.0, 3.0)))
            .withDetectedOpponents(List.of(new Translation2d(10.0, 4.0)));

    assertEquals(1.0, state.getRobotPose().getX(), 1e-9);
    assertEquals(3, state.getFuelHeld());
    assertTrue(state.isHubActive());
    assertEquals(45.0, state.getTimeRemaining(), 1e-9);
    assertEquals(1, state.getDetectedFuel().size());
    assertEquals(1, state.getDetectedOpponents().size());
  }
}
