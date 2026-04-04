package frc.robot.autos;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.Collections;
import java.util.List;

/**
 * Immutable snapshot of game state used by {@link AutonomousStrategy} to evaluate targets.
 *
 * <p>Built with a fluent {@code .with*()} API. All fields have sensible defaults so only the
 * relevant state needs to be set in each call site / test.
 */
public final class GameState {

  private final Pose2d robotPose;
  private final int fuelHeld;
  private final boolean hubActive;
  private final double timeRemaining;
  private final List<Translation2d> detectedFuel;
  private final List<Translation2d> detectedOpponents;

  /** Create a default GameState (robot at origin, no fuel, hub inactive, 150 s remaining). */
  public GameState() {
    this(
        new Pose2d(0, 0, new Rotation2d()),
        0,
        false,
        150.0,
        Collections.emptyList(),
        Collections.emptyList());
  }

  private GameState(
      Pose2d robotPose,
      int fuelHeld,
      boolean hubActive,
      double timeRemaining,
      List<Translation2d> detectedFuel,
      List<Translation2d> detectedOpponents) {
    this.robotPose = robotPose;
    this.fuelHeld = fuelHeld;
    this.hubActive = hubActive;
    this.timeRemaining = timeRemaining;
    this.detectedFuel = detectedFuel;
    this.detectedOpponents = detectedOpponents;
  }

  // ---- fluent builders (return new immutable copy) ----

  public GameState withRobotPose(Pose2d pose) {
    return new GameState(pose, fuelHeld, hubActive, timeRemaining, detectedFuel, detectedOpponents);
  }

  public GameState withFuelHeld(int count) {
    return new GameState(
        robotPose, count, hubActive, timeRemaining, detectedFuel, detectedOpponents);
  }

  public GameState withHubActive(boolean active) {
    return new GameState(
        robotPose, fuelHeld, active, timeRemaining, detectedFuel, detectedOpponents);
  }

  public GameState withTimeRemaining(double seconds) {
    return new GameState(robotPose, fuelHeld, hubActive, seconds, detectedFuel, detectedOpponents);
  }

  public GameState withDetectedFuel(List<Translation2d> fuel) {
    return new GameState(
        robotPose, fuelHeld, hubActive, timeRemaining, List.copyOf(fuel), detectedOpponents);
  }

  public GameState withDetectedOpponents(List<Translation2d> opponents) {
    return new GameState(
        robotPose, fuelHeld, hubActive, timeRemaining, detectedFuel, List.copyOf(opponents));
  }

  // ---- getters ----

  public Pose2d getRobotPose() {
    return robotPose;
  }

  public int getFuelHeld() {
    return fuelHeld;
  }

  public boolean isHubActive() {
    return hubActive;
  }

  public double getTimeRemaining() {
    return timeRemaining;
  }

  public List<Translation2d> getDetectedFuel() {
    return detectedFuel;
  }

  public List<Translation2d> getDetectedOpponents() {
    return detectedOpponents;
  }
}
