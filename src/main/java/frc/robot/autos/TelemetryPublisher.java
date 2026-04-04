package frc.robot.autos;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.littletonrobotics.junction.Logger;

/**
 * Static utility that publishes autonomous state to AdvantageKit in formats AdvantageScope can
 * render as field overlays.
 *
 * <p>AdvantageScope renders {@code Pose2d[]} arrays as robot ghosts on the field. This class
 * converts various geometry types into that format and publishes them under {@code Auto/Viz/}
 * namespaced keys.
 */
public class TelemetryPublisher {

  private TelemetryPublisher() {}

  /**
   * Convert a list of Translation2d points to a Pose2d array (heading = 0 for all) suitable for
   * AdvantageScope field overlay rendering.
   */
  static Pose2d[] translationsToPoses(List<Translation2d> points) {
    return points.stream().map(t -> new Pose2d(t, new Rotation2d())).toArray(Pose2d[]::new);
  }

  /** Publish planned path waypoints as a field overlay. */
  public static void publishPlannedPath(List<Translation2d> waypoints) {
    Logger.recordOutput("Auto/Viz/PlannedPath", translationsToPoses(waypoints));
  }

  /** Publish current autonomous target. */
  public static void publishCurrentTarget(Pose2d target) {
    Logger.recordOutput("Auto/Viz/CurrentTarget", new Pose2d[] {target});
  }

  /** Publish detected fuel ball positions. */
  public static void publishFuelDetections(List<Translation2d> fuel) {
    Logger.recordOutput("Auto/Viz/DetectedFuel", translationsToPoses(fuel));
  }

  /** Publish detected opponent positions. */
  public static void publishOpponentPositions(List<Translation2d> opponents) {
    Logger.recordOutput("Auto/Viz/Opponents", translationsToPoses(opponents));
  }

  /** Publish robot trajectory breadcrumb trail. */
  public static void publishTrajectoryHistory(List<Pose2d> history) {
    Logger.recordOutput("Auto/Viz/History", history.toArray(new Pose2d[0]));
  }

  /** Publish dynamic obstacle positions (opponent exclusion zones). */
  public static void publishDynamicObstacles(List<Translation2d> obstacles) {
    Logger.recordOutput("Auto/Viz/DynamicObstacles", translationsToPoses(obstacles));
  }

  /** Clear all visualizations by publishing empty arrays. */
  public static void clearAll() {
    Pose2d[] empty = new Pose2d[0];
    Logger.recordOutput("Auto/Viz/PlannedPath", empty);
    Logger.recordOutput("Auto/Viz/CurrentTarget", empty);
    Logger.recordOutput("Auto/Viz/DetectedFuel", empty);
    Logger.recordOutput("Auto/Viz/Opponents", empty);
    Logger.recordOutput("Auto/Viz/History", empty);
    Logger.recordOutput("Auto/Viz/DynamicObstacles", empty);
  }
}
