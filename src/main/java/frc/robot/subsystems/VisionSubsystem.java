package frc.robot.subsystems;

import edu.wpi.first.math.VecBuilder;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.networktables.DoubleArraySubscriber;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTable;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import java.util.List;
import org.littletonrobotics.junction.Logger;

/**
 * Vision subsystem. Reads Limelight MegaTag2 botpose from NetworkTables and fuses it into the
 * swerve pose estimator via {@link SwerveSubsystem#addVisionMeasurement}.
 *
 * <p>Uses the {@code botpose_orb_wpiblue} key — this is MegaTag2's orientation-robust botpose in
 * the WPI blue-origin coordinate system. Published by Limelight firmware ≥ 2024.1.
 *
 * <p>NT4 array layout (index → meaning):
 *
 * <ul>
 *   <li>0 → X (meters, field-relative)
 *   <li>1 → Y (meters, field-relative)
 *   <li>2 → Z (meters, ignored for 2D)
 *   <li>3–5 → roll, pitch, yaw (degrees — yaw used as heading)
 *   <li>6 → total latency (ms, pipeline + capture)
 *   <li>7 → tag count
 *   <li>8 → tag span (meters)
 *   <li>9 → average tag distance (meters)
 *   <li>10 → average tag area (% of image)
 * </ul>
 */
public class VisionSubsystem extends SubsystemBase {

  // Minimum tags visible before we trust the measurement
  private static final int kMinTagCount = 1;
  // Maximum total latency before we discard the measurement (ms)
  private static final double kMaxLatencyMs = 50.0;
  // Maximum average tag distance before we discount heavily (meters)
  private static final double kMaxTagDistM = 4.0;

  private final SwerveSubsystem swerve;

  private final DoubleArraySubscriber botposeSub;
  private final DoubleArraySubscriber llpythonSub;
  private final IntegerPublisher pipelinePub;

  /** Parses the llpython neural-detection array for FUEL positions. */
  private final FuelDetectionConsumer fuelDetection = new FuelDetectionConsumer();

  private boolean hasTarget = false;
  private Pose2d lastPose = new Pose2d();

  // Timestamp (FPGA seconds) when the vision target was first confirmed valid this streak
  private double targetValidSince = Double.MAX_VALUE;

  /** Creates the vision subsystem. */
  public VisionSubsystem(SwerveSubsystem swerve) {
    this.swerve = swerve;

    NetworkTable limelightTable = NetworkTableInstance.getDefault().getTable("limelight");

    // MegaTag2 orientation-robust botpose in WPI blue origin
    botposeSub = limelightTable.getDoubleArrayTopic("botpose_orb_wpiblue").subscribe(new double[0]);

    // Neural detector output: [numFuel, x1, y1, conf1, x2, y2, conf2, ...]
    llpythonSub = limelightTable.getDoubleArrayTopic("llpython").subscribe(new double[0]);

    // Pipeline command publisher — write pipeline index to switch Limelight mode
    pipelinePub = limelightTable.getIntegerTopic("pipeline").publish();
  }

  @Override
  public void periodic() {
    // Feed neural-detection array into the fuel/opponent consumer every loop cycle
    fuelDetection.updateFromRawArray(llpythonSub.get());
    Logger.recordOutput(
        "Vision/FuelDetectionCount", fuelDetection.getDetectedFuelPositions().size());
    Logger.recordOutput(
        "Vision/OpponentDetectionCount", fuelDetection.getDetectedOpponentPositions().size());

    double[] botpose = botposeSub.get();

    if (!isValidBotpose(botpose, kMinTagCount, kMaxLatencyMs, kMaxTagDistM)) {
      hasTarget = false;
      Logger.recordOutput("Vision/HasTarget", false);
      return;
    }

    double x = botpose[0];
    double y = botpose[1];
    double yawDeg = botpose[5];
    double latencyMs = botpose[6];
    int tagCount = (int) botpose[7];
    double avgTagDistM = botpose[9];

    lastPose = new Pose2d(new Translation2d(x, y), Rotation2d.fromDegrees(yawDeg));

    // Reject if vision pose is >1.0m from current odometry — likely a tag misidentification
    double distFromOdometry =
        lastPose.getTranslation().getDistance(swerve.getPose().getTranslation());
    if (distFromOdometry > 1.0) {
      hasTarget = false;
      Logger.recordOutput("Vision/HasTarget", false);
      Logger.recordOutput("Vision/RejectedDistM", distFromOdometry);
      return;
    }

    // Timestamp: current time minus latency (convert ms → seconds)
    double timestampSeconds = edu.wpi.first.wpilibj.Timer.getFPGATimestamp() - (latencyMs / 1000.0);

    // Distance-based standard deviations: trust close tags more, distant tags less.
    // Base std dev 0.5m at 1m distance, scaling quadratically with distance.
    // Multi-tag measurements get tighter std devs (divided by sqrt(tagCount)).
    double xyStdDev = 0.5 * Math.pow(avgTagDistM, 2) / Math.sqrt(tagCount);
    double thetaStdDev = tagCount >= 2 ? 0.1 : 0.5 * avgTagDistM;
    swerve.addVisionMeasurement(
        lastPose, timestampSeconds, VecBuilder.fill(xyStdDev, xyStdDev, thetaStdDev));

    // Start (or continue) the continuous-valid timer
    if (!hasTarget) {
      targetValidSince = Timer.getFPGATimestamp();
    }
    hasTarget = true;

    Logger.recordOutput("Vision/HasTarget", true);
    Logger.recordOutput("Vision/BotPose", lastPose);
    Logger.recordOutput("Vision/TagCount", tagCount);
    Logger.recordOutput("Vision/LatencyMs", latencyMs);
    Logger.recordOutput("Vision/AvgTagDistM", avgTagDistM);
    Logger.recordOutput("Vision/StdDevXY", xyStdDev);
    Logger.recordOutput("Vision/StdDevTheta", thetaStdDev);
    Logger.recordOutput(
        "Vision/TargetValidDurationSec", Timer.getFPGATimestamp() - targetValidSince);
  }

  /** Whether a valid MegaTag2 measurement was received this cycle. */
  public boolean hasTarget() {
    return hasTarget;
  }

  /**
   * Whether the vision target has been continuously valid for at least {@code seconds}. Used by
   * AutoScoreCommand to confirm the Limelight has a stable AprilTag lock before firing.
   *
   * @param seconds minimum continuous lock duration
   * @return true if target has been valid without interruption for at least this long
   */
  public boolean isTargetValidFor(double seconds) {
    if (!hasTarget) return false;
    return (Timer.getFPGATimestamp() - targetValidSince) >= seconds;
  }

  /**
   * Switch the Limelight to the AprilTag pipeline (teleop / scoring mode). Pipeline index from
   * {@link frc.robot.Constants.Superstructure#kAprilTagPipeline}.
   */
  public void setAprilTagPipeline() {
    pipelinePub.set(Constants.Superstructure.kAprilTagPipeline);
    Logger.recordOutput("Vision/Pipeline", "AprilTag");
  }

  /**
   * Switch the Limelight to the neural detector pipeline (autonomous game piece detection).
   * Pipeline index from {@link frc.robot.Constants.Superstructure#kNeuralPipeline}.
   */
  public void setNeuralPipeline() {
    pipelinePub.set(Constants.Superstructure.kNeuralPipeline);
    Logger.recordOutput("Vision/Pipeline", "Neural");
  }

  /** The most recent accepted MegaTag2 pose estimate. */
  public Pose2d getLastPose() {
    return lastPose;
  }

  /**
   * Confirmed FUEL positions from the Limelight neural detector. Requires 3 consecutive frames at
   * ≥80% confidence. Capped at {@link Constants.Pathfinding#kMaxFuelDetections} entries.
   *
   * @return unmodifiable list of field-space FUEL positions (meters)
   */
  public List<Translation2d> getFuelPositions() {
    return fuelDetection.getDetectedFuelPositions();
  }

  /**
   * Detected opponent robot positions from the Limelight neural detector. Single-frame confirmed
   * (no persistence gate — opponents are immediate hazards). ≥80% confidence required.
   *
   * @return unmodifiable list of field-space opponent positions (meters)
   */
  public List<Translation2d> getOpponentPositions() {
    return fuelDetection.getDetectedOpponentPositions();
  }

  /**
   * Validates a {@code botpose_orb_wpiblue} MegaTag2 array against quality thresholds and field
   * bounds. Package-private for unit testing.
   *
   * @param botpose the raw NT4 double array (must be ≥11 elements)
   * @param minTagCount minimum number of AprilTags required
   * @param maxLatencyMs maximum allowed total latency in milliseconds
   * @param maxTagDistM maximum allowed average tag distance in meters
   * @return true if the measurement passes all checks
   */
  static boolean isValidBotpose(
      double[] botpose, int minTagCount, double maxLatencyMs, double maxTagDistM) {
    if (botpose == null || botpose.length < 11) return false;
    int tagCount = (int) botpose[7];
    double latencyMs = botpose[6];
    double avgTagDistM = botpose[9];
    if (tagCount < minTagCount || latencyMs > maxLatencyMs || avgTagDistM > maxTagDistM) {
      return false;
    }
    double x = botpose[0];
    double y = botpose[1];
    return x >= 0 && x <= Constants.kFieldLengthMeters && y >= 0 && y <= Constants.kFieldWidthMeters;
  }
}
