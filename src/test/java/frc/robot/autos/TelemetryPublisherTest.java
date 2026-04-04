package frc.robot.autos;

import static org.junit.jupiter.api.Assertions.*;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Translation2d;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Tests for {@link TelemetryPublisher} data conversion methods. */
class TelemetryPublisherTest {

  @Test
  void translationsToPoses_threePoints_returnsArrayOfThree() {
    List<Translation2d> points =
        List.of(
            new Translation2d(1.0, 2.0), new Translation2d(3.0, 4.0), new Translation2d(5.0, 6.0));

    Pose2d[] result = TelemetryPublisher.translationsToPoses(points);

    assertEquals(3, result.length);
  }

  @Test
  void translationsToPoses_emptyList_returnsEmptyArray() {
    Pose2d[] result = TelemetryPublisher.translationsToPoses(List.of());

    assertEquals(0, result.length);
  }

  @Test
  void translationsToPoses_singlePoint_returnsArrayOfOne() {
    List<Translation2d> points = List.of(new Translation2d(7.5, 3.2));

    Pose2d[] result = TelemetryPublisher.translationsToPoses(points);

    assertEquals(1, result.length);
  }

  @Test
  void translationsToPoses_xyValuesMatchInput() {
    List<Translation2d> points =
        List.of(
            new Translation2d(1.5, 2.5), new Translation2d(3.5, 4.5), new Translation2d(5.5, 6.5));

    Pose2d[] result = TelemetryPublisher.translationsToPoses(points);

    for (int i = 0; i < points.size(); i++) {
      assertEquals(points.get(i).getX(), result[i].getX(), 1e-9, "X mismatch at index " + i);
      assertEquals(points.get(i).getY(), result[i].getY(), 1e-9, "Y mismatch at index " + i);
    }
  }

  @Test
  void translationsToPoses_allHeadingsAreZero() {
    List<Translation2d> points =
        List.of(
            new Translation2d(1.0, 2.0), new Translation2d(3.0, 4.0), new Translation2d(5.0, 6.0));

    Pose2d[] result = TelemetryPublisher.translationsToPoses(points);

    for (int i = 0; i < result.length; i++) {
      assertEquals(
          0.0, result[i].getRotation().getRadians(), 1e-9, "Heading not zero at index " + i);
    }
  }
}
