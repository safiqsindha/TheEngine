package frc.robot.subsystems;

import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.config.ModuleConfig;
import com.pathplanner.lib.config.PIDConstants;
import com.pathplanner.lib.config.RobotConfig;
import com.pathplanner.lib.controllers.PPHolonomicDriveController;
import com.pathplanner.lib.path.PathConstraints;
import com.pathplanner.lib.pathfinding.LocalADStar;
import com.pathplanner.lib.pathfinding.Pathfinding;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.util.Units;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.DriverStation.Alliance;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import java.io.File;
import org.littletonrobotics.junction.Logger;
import swervelib.SwerveDrive;
import swervelib.math.SwerveMath;
import swervelib.parser.SwerveDriveConfiguration;
import swervelib.parser.SwerveParser;
import swervelib.telemetry.SwerveDriveTelemetry;
import swervelib.telemetry.SwerveDriveTelemetry.TelemetryVerbosity;

/**
 * The swerve drive subsystem. This is the ONLY class that interacts directly with YAGSL's
 * SwerveDrive. All other subsystems and commands go through this class.
 *
 * <p>YAGSL handles all motor controller instantiation, module kinematics, and odometry internally.
 * AdvantageKit logs YAGSL telemetry as a consumer (not a control-path wrapper).
 *
 * <p>Hardware: 4x NEO + SPARK MAX (drive), 4x NEO + SPARK MAX (steer), Thrifty 10-pin encoders
 * attached to SPARK MAX data port, ADIS16470 gyro.
 */
public final class SwerveSubsystem extends SubsystemBase {

  // Static init: configure telemetry before SwerveDrive is instantiated.
  // Avoids ST_WRITE_TO_STATIC_FROM_INSTANCE_METHOD SpotBugs warning.
  static {
    SwerveDriveTelemetry.verbosity = TelemetryVerbosity.HIGH;
  }

  private final SwerveDrive swerveDrive;

  /**
   * Last commanded robot-relative speeds, stored so we can re-apply them after the physics step.
   * The maple-sim motor force pipeline applies forces in the wrong direction, so we must override
   * the physics body velocity each tick after updateOdometry() steps the sim.
   */
  private ChassisSpeeds lastCommandedSpeeds = new ChassisSpeeds();

  /**
   * Manually integrated pose for simulation, bypassing the broken physics position tracking. Null
   * until the first periodic() tick in simulation.
   */
  private Pose2d simOverridePose;

  /** Creates the swerve subsystem by parsing YAGSL JSON configuration. */
  public SwerveSubsystem() {
    File swerveJsonDir =
        new File(Filesystem.getDeployDirectory(), Constants.Swerve.kSwerveJsonDirectory);
    try {
      swerveDrive =
          new SwerveParser(swerveJsonDir).createSwerveDrive(Constants.Swerve.kMaxSpeedMetersPerSec);
    } catch (Exception e) {
      throw new RuntimeException("Failed to create swerve drive from JSON config", e);
    }

    // Hardware-verified settings from swerve-test branch:
    // Heading correction off — only useful with absolute angle control mode
    swerveDrive.setHeadingCorrection(false);
    // Cosine compensation off — causes discrepancies not seen in real life when enabled
    swerveDrive.setCosineCompensator(false);
    // Correct for skew that worsens with angular velocity (coefficient tuned on hardware)
    swerveDrive.setAngularVelocityCompensation(true, true, 0.1);
    // Encoder auto-sync disabled — encoder sync is done manually if needed
    swerveDrive.setModuleEncoderAutoSynchronize(false, 1);

    // In simulation, stop YAGSL's 4ms Notifier and drive odometry manually from periodic().
    // The Notifier does not fire reliably in HALSim — calling updateOdometry() from the 20ms
    // robot loop avoids missed physics steps and keeps simulated time advancing correctly.
    // stopOdometryThread() also configures SimulatedArena for 5 sub-ticks per 20ms period.
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      swerveDrive.stopOdometryThread();
    }

    // In simulation, spawn the robot at a clearly visible field position instead of (0,0)
    // which clips into the corner wall.
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      swerveDrive.resetOdometry(new Pose2d(2.0, 4.0, new Rotation2d(0)));
    }

    setupPathPlanner();
  }

  /**
   * Configure PathPlannerLib's AutoBuilder and AD* pathfinder for runtime path planning. Uses our
   * hardware-confirmed gear ratios, wheel diameter, and module locations. The AD* pathfinder loads
   * the navigation grid from {@code deploy/pathplanner/navgrid.json}.
   */
  private void setupPathPlanner() {
    double halfTrack = Units.inchesToMeters(Constants.Swerve.kModuleLocationInches);
    double wheelRadiusM = Units.inchesToMeters(Constants.Swerve.kWheelDiameterInches / 2.0);

    // Build module config from hardware-confirmed constants.
    ModuleConfig moduleConfig =
        new ModuleConfig(
            wheelRadiusM,
            Constants.Swerve.kMaxSpeedMetersPerSec,
            1.2, // wheel coefficient of friction (carpet)
            DCMotor.getNEO(1).withReduction(Constants.Swerve.kDriveGearRatio),
            40, // drive motor current limit (amps)
            1); // one drive motor per module

    // Moment of inertia estimate for square chassis: (1/6) * m * L^2
    double sideLength = 2.0 * halfTrack;
    double moi = (1.0 / 6.0) * Constants.kRobotMassKg * sideLength * sideLength;

    RobotConfig config =
        new RobotConfig(
            Constants.kRobotMassKg,
            moi,
            moduleConfig,
            new Translation2d(halfTrack, halfTrack), // FL
            new Translation2d(halfTrack, -halfTrack), // FR
            new Translation2d(-halfTrack, halfTrack), // BL
            new Translation2d(-halfTrack, -halfTrack)); // BR

    AutoBuilder.configure(
        this::getPose,
        this::resetOdometry,
        this::getRobotVelocity,
        (speeds, feedforwards) -> driveRobotRelative(speeds),
        new PPHolonomicDriveController(
            new PIDConstants(5.0, 0.0, 0.0), // Translation PID
            new PIDConstants(5.0, 0.0, 0.0)), // Rotation PID
        config,
        this::isRedAlliance,
        this);

    // Use AD* pathfinder (loads navgrid.json from deploy/pathplanner/)
    Pathfinding.setPathfinder(new LocalADStar());
  }

  @Override
  public void periodic() {
    // In simulation, manually step odometry (and maple-sim physics) each robot loop tick.
    // YAGSL's Notifier does not fire in HALSim; stopOdometryThread() was called in the constructor.
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      // Step the physics engine (needed for encoder/gyro sim state updates).
      swerveDrive.updateOdometry();

      // Full physics position bypass: the maple-sim motor force pipeline applies forces in the
      // wrong direction, corrupting both velocity and position during the physics step. Instead of
      // relying on physics for pose tracking, we integrate position manually from the last
      // commanded ChassisSpeeds and override odometry each tick.
      double dt = 0.02; // 20ms robot loop period
      Pose2d current = simOverridePose != null ? simOverridePose : getPose();
      double heading = current.getRotation().getRadians();
      double vx = lastCommandedSpeeds.vxMetersPerSecond;
      double vy = lastCommandedSpeeds.vyMetersPerSecond;
      double omega = lastCommandedSpeeds.omegaRadiansPerSecond;
      // Robot-relative to field-relative conversion
      double dx = (vx * Math.cos(heading) - vy * Math.sin(heading)) * dt;
      double dy = (vx * Math.sin(heading) + vy * Math.cos(heading)) * dt;
      double dtheta = omega * dt;
      simOverridePose =
          new Pose2d(current.getX() + dx, current.getY() + dy, new Rotation2d(heading + dtheta));
      // Override the physics-corrupted pose and velocity
      swerveDrive.resetOdometry(simOverridePose);
      swerveDrive.getMapleSimDrive().ifPresent(sim -> sim.setRobotSpeeds(lastCommandedSpeeds));
    }
    Pose2d logPose = getPose();
    Logger.recordOutput("Drive/Pose", logPose);
    Logger.recordOutput("Drive/GyroYaw", getHeading().getDegrees());
    Logger.recordOutput("Drive/RobotVelocity", getRobotVelocity());
    swerveDrive
        .getSimulationDriveTrainPose()
        .ifPresent(p -> Logger.recordOutput("Drive/SimGroundTruth", p));
  }

  /**
   * Drive the robot using field-relative or robot-relative speeds.
   *
   * <p>In simulation, captures the commanded speeds (converted to robot-relative) so the maple-sim
   * kinematic bypass in {@link #periodic()} can integrate pose correctly. Without this, teleop
   * joystick commands bypass {@link #driveRobotRelative} and the sim robot stays frozen or moves
   * backwards due to the maple-sim force-direction bug.
   *
   * @param translation desired X/Y velocity in meters per second
   * @param rotation desired angular velocity in radians per second
   * @param fieldRelative whether the translation is field-relative
   */
  public void drive(Translation2d translation, double rotation, boolean fieldRelative) {
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      // Mirror YAGSL's internal conversion so lastCommandedSpeeds is always robot-relative,
      // matching the format the periodic() bypass integrates.
      ChassisSpeeds speeds = new ChassisSpeeds(translation.getX(), translation.getY(), rotation);
      if (fieldRelative) {
        speeds = ChassisSpeeds.fromFieldRelativeSpeeds(speeds, getHeading());
      }
      lastCommandedSpeeds = speeds;
    }
    swerveDrive.drive(translation, rotation, fieldRelative, false);
  }

  /**
   * Drive using a ChassisSpeeds object (field-oriented). Used by YAGSL SwerveInputStream and Choreo
   * trajectory following.
   *
   * @param velocity field-relative chassis speeds
   */
  public void driveFieldOriented(ChassisSpeeds velocity) {
    swerveDrive.driveFieldOriented(velocity);
  }

  /**
   * Drive the robot using robot-relative ChassisSpeeds. Used by Choreo trajectory following.
   *
   * <p>In simulation, the maple-sim motor-force pipeline is currently non-functional (propelling
   * forces from motor voltage produce zero velocity change in dyn4j despite correct math — root
   * cause TBD). As a bypass, we directly set the physics body velocity so the robot visibly follows
   * trajectories in HALSim. {@code swerveDrive.drive()} is still called so module encoder states
   * update for odometry and friction forces stay consistent.
   *
   * @param chassisSpeeds robot-relative chassis speeds
   */
  public void driveRobotRelative(ChassisSpeeds chassisSpeeds) {
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      lastCommandedSpeeds = chassisSpeeds;
      swerveDrive.getMapleSimDrive().ifPresent(sim -> sim.setRobotSpeeds(chassisSpeeds));
    }
    swerveDrive.drive(chassisSpeeds);
  }

  /** Get the robot's current pose from odometry. */
  public Pose2d getPose() {
    return swerveDrive.getPose();
  }

  /** Reset odometry to a specific pose. */
  public void resetOdometry(Pose2d pose) {
    if (edu.wpi.first.wpilibj.RobotBase.isSimulation()) {
      simOverridePose = pose;
    }
    swerveDrive.resetOdometry(pose);
  }

  /** Get the robot's current heading from the gyroscope. */
  public Rotation2d getHeading() {
    return getPose().getRotation();
  }

  /** Get the robot's current robot-relative chassis speeds. */
  public ChassisSpeeds getRobotVelocity() {
    return swerveDrive.getRobotVelocity();
  }

  /** Get the robot's current field-relative chassis speeds. */
  public ChassisSpeeds getFieldVelocity() {
    return swerveDrive.getFieldVelocity();
  }

  /**
   * Get target chassis speeds from two-joystick heading control (absolute heading mode).
   *
   * @param xInput X translation (-1 to 1)
   * @param yInput Y translation (-1 to 1)
   * @param headingX heading vector X component
   * @param headingY heading vector Y component
   * @return target ChassisSpeeds
   */
  public ChassisSpeeds getTargetSpeeds(
      double xInput, double yInput, double headingX, double headingY) {
    Translation2d scaledInputs = SwerveMath.cubeTranslation(new Translation2d(xInput, yInput));
    return swerveDrive.swerveController.getTargetSpeeds(
        scaledInputs.getX(),
        scaledInputs.getY(),
        headingX,
        headingY,
        getHeading().getRadians(),
        Constants.Swerve.kMaxSpeedMetersPerSec);
  }

  /**
   * Get target chassis speeds from translation + absolute angle (heading setpoint mode).
   *
   * @param xInput X translation (-1 to 1)
   * @param yInput Y translation (-1 to 1)
   * @param angle target heading as Rotation2d
   * @return target ChassisSpeeds
   */
  public ChassisSpeeds getTargetSpeeds(double xInput, double yInput, Rotation2d angle) {
    Translation2d scaledInputs = SwerveMath.cubeTranslation(new Translation2d(xInput, yInput));
    return swerveDrive.swerveController.getTargetSpeeds(
        scaledInputs.getX(),
        scaledInputs.getY(),
        angle.getRadians(),
        getHeading().getRadians(),
        Constants.Swerve.kMaxSpeedMetersPerSec);
  }

  /** Zero the gyroscope heading. Call this when robot is facing away from driver. */
  public void zeroGyro() {
    swerveDrive.zeroGyro();
  }

  /**
   * Zero gyro with alliance-relative heading. Red alliance: faces 180 degrees after zero. Blue
   * alliance: faces 0 degrees (same as zeroGyro).
   */
  public void zeroGyroWithAlliance() {
    if (isRedAlliance()) {
      zeroGyro();
      resetOdometry(new Pose2d(getPose().getTranslation(), Rotation2d.fromDegrees(180)));
    } else {
      zeroGyro();
    }
  }

  /** Lock the swerve modules in an X pattern to prevent pushing. */
  public void lock() {
    swerveDrive.lockPose();
  }

  /**
   * Returns the raw YAGSL SwerveModule array. Used by {@link
   * frc.robot.commands.EncoderCalibrationCommand} to read absolute encoder positions.
   */
  public swervelib.SwerveModule[] getModules() {
    return swerveDrive.getModules();
  }

  /**
   * Set all drive motors to brake or coast idle mode.
   *
   * @param brake true for brake mode, false for coast
   */
  public void setMotorBrake(boolean brake) {
    swerveDrive.setMotorIdleMode(brake);
  }

  /**
   * Add a vision pose measurement to the pose estimator.
   *
   * @param pose the measured robot pose
   * @param timestampSeconds the timestamp of the measurement in seconds
   */
  public void addVisionMeasurement(Pose2d pose, double timestampSeconds) {
    swerveDrive.addVisionMeasurement(pose, timestampSeconds);
  }

  /**
   * Add a vision pose measurement with explicit standard deviations for the Kalman filter.
   *
   * @param pose the measured robot pose
   * @param timestampSeconds the timestamp of the measurement in seconds
   * @param stdDevs standard deviations [x meters, y meters, theta radians]
   */
  public void addVisionMeasurement(
      Pose2d pose,
      double timestampSeconds,
      edu.wpi.first.math.Matrix<edu.wpi.first.math.numbers.N3, edu.wpi.first.math.numbers.N1>
          stdDevs) {
    swerveDrive.addVisionMeasurement(pose, timestampSeconds, stdDevs);
  }

  /** Get the current pitch angle from the IMU. */
  public Rotation2d getPitch() {
    return swerveDrive.getPitch();
  }

  /** Get the YAGSL SwerveDriveConfiguration. Used by velocity limiting utilities. */
  public SwerveDriveConfiguration getSwerveDriveConfiguration() {
    return swerveDrive.swerveDriveConfiguration;
  }

  /** Get the underlying SwerveDrive for advanced operations. Use sparingly. */
  public SwerveDrive getSwerveDrive() {
    return swerveDrive;
  }

  /**
   * Create a command that pathfinds to the given pose using PathPlannerLib's AD* algorithm. The
   * robot avoids static field obstacles loaded from navgrid.json. Used by PathfindToGoalCommand and
   * FullAutonomousCommand.
   *
   * @param targetPose the desired end pose (field-relative)
   * @return a Command that drives the robot to the target, finishing when it arrives
   */
  public Command pathfindToPose(Pose2d targetPose) {
    return AutoBuilder.pathfindToPose(
        targetPose,
        new PathConstraints(
            Constants.Swerve.kMaxSpeedMetersPerSec,
            Constants.Swerve.kMaxSpeedMetersPerSec, // max accel ≈ max speed for snappy response
            Constants.Swerve.kMaxAngularSpeedRadPerSec,
            Constants.Swerve.kMaxAngularSpeedRadPerSec));
  }

  private boolean isRedAlliance() {
    var alliance = DriverStation.getAlliance();
    return alliance.isPresent() && alliance.get() == Alliance.Red;
  }
}
