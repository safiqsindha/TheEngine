package frc.robot.subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.RelativeEncoder;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.FeedbackSensor;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.system.plant.LinearSystemId;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.DCMotorSim;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import org.littletonrobotics.junction.Logger;

/**
 * Flywheel subsystem. Controls two SPARK Flex Vortex motors (main flywheel) and two SPARK MAX NEO
 * motors (lower feed wheels). PID runs on SPARK Flex onboard controller (velocity MAXMotion).
 *
 * <p>In simulation, the onboard SPARK PID does not execute. Instead, a {@link DCMotorSim} models
 * the flywheel physics (two NEO Vortex motors, 1:1 gear ratio, ~4g·m² moment of inertia) and a
 * software P+FF controller applies voltage each loop so that velocity PID behavior can be verified
 * in HALSim without hardware.
 */
public class Flywheel extends SubsystemBase {

  // The left Vortex is the primary motor and PID controller; right follows it.
  public final SparkFlex leftVortex =
      new SparkFlex(Constants.Flywheel.kLeftVortexId, MotorType.kBrushless);

  private final SparkFlex rightVortex =
      new SparkFlex(Constants.Flywheel.kRightVortexId, MotorType.kBrushless);

  private final SparkMax frontWheel =
      new SparkMax(Constants.Flywheel.kFrontWheelId, MotorType.kBrushless);

  private final SparkMax backWheel =
      new SparkMax(Constants.Flywheel.kBackWheelId, MotorType.kBrushless);

  private final SparkClosedLoopController closedLoopController =
      leftVortex.getClosedLoopController();

  private final RelativeEncoder encoder = leftVortex.getEncoder();

  // ─── Simulation ──────────────────────────────────────────────────────────
  // Moment of inertia for a typical FRC flywheel disk (~4 kg·m² × 10⁻³).
  private static final double kSimJKgM2 = 0.004;
  // Software P gain (volts per RPM error) — used only in sim; tuned separately from SPARK kP.
  private static final double kSimKpVoltsPerRpm = 0.008;

  private DCMotorSim flywheelSim;
  private double simTargetRpm = 0.0;
  private double simCurrentRpm = 0.0;

  public Flywheel() {
    SparkFlexConfig lVortexConfig = new SparkFlexConfig();
    lVortexConfig
        .smartCurrentLimit(80)
        .inverted(true)
        .closedLoop
        .feedbackSensor(FeedbackSensor.kPrimaryEncoder)
        .p(Constants.Flywheel.kP)
        .i(Constants.Flywheel.kI)
        .d(Constants.Flywheel.kD)
        .outputRange(0, 1)
        .feedForward
        .kS(Constants.Flywheel.kS)
        .kV(Constants.Flywheel.kV)
        .kA(0);
    lVortexConfig.closedLoop.maxMotion.maxAcceleration(1000);

    SparkFlexConfig rVortexConfig = new SparkFlexConfig();
    rVortexConfig.apply(lVortexConfig).follow(leftVortex, true);

    leftVortex.configure(
        lVortexConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    rightVortex.configure(
        rVortexConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    SparkMaxConfig fConfig = new SparkMaxConfig();
    fConfig.inverted(true).idleMode(IdleMode.kBrake).smartCurrentLimit(40);

    SparkMaxConfig bConfig = new SparkMaxConfig();
    bConfig.apply(fConfig).inverted(false);

    frontWheel.configure(fConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    backWheel.configure(bConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    // Warm-up call so the first REVLib CAN transaction happens during robotInit()
    // rather than inside the first command loop (which would cause a 2-second overrun
    // that expires the Choreo trajectory before it can move the robot).
    frontWheel.set(0);
    backWheel.set(0);
    leftVortex.set(0);
    rightVortex.set(0);

    // Build the sim model — two Vortex motors coupled 1:1 to the flywheel.
    if (RobotBase.isSimulation()) {
      DCMotor vortexPair = DCMotor.getNeoVortex(2);
      flywheelSim =
          new DCMotorSim(
              LinearSystemId.createDCMotorSystem(vortexPair, kSimJKgM2, 1.0), vortexPair);
    }
  }

  @Override
  public void periodic() {
    if (RobotBase.isSimulation() && flywheelSim != null) {
      // Software P+FF controller (SPARK onboard PID does not run in sim).
      // kV is V/RPM (SPARK convention), kS is static friction volts.
      double errorRpm = simTargetRpm - simCurrentRpm;
      double ffVolts =
          Constants.Flywheel.kS * Math.signum(simTargetRpm) + Constants.Flywheel.kV * simTargetRpm;
      double voltage = MathUtil.clamp(ffVolts + kSimKpVoltsPerRpm * errorRpm, 0.0, 12.0);

      flywheelSim.setInputVoltage(voltage);
      flywheelSim.update(0.02);

      // Convert rad/s → RPM; always report as positive (matches hardware getCurrentRpm).
      simCurrentRpm = Math.abs(flywheelSim.getAngularVelocityRadPerSec() * 60.0 / (2.0 * Math.PI));

      Logger.recordOutput("Flywheel/SimTargetRpm", simTargetRpm);
      Logger.recordOutput("Flywheel/SimCurrentRpm", simCurrentRpm);
      Logger.recordOutput("Flywheel/SimVoltage", voltage);
      Logger.recordOutput(
          "Flywheel/SimAtSpeed",
          simTargetRpm > 0
              && Math.abs(simCurrentRpm - simTargetRpm) / simTargetRpm
                  < Constants.Flywheel.kReadyThreshold);
    }
  }

  /**
   * Command the lower feed wheels to a percent output.
   *
   * @param percent output (-1 to 1)
   */
  public void setLower(double percent) {
    frontWheel.set(percent);
    backWheel.set(percent);
  }

  /**
   * Set the flywheel target speed. In simulation, stores the target for the software PID running in
   * {@link #periodic()}. On hardware, commands the SPARK Flex MAXMotion velocity controller.
   *
   * @param rpm target velocity in RPM
   */
  public void setTargetRpm(double rpm) {
    if (RobotBase.isSimulation()) {
      simTargetRpm = rpm;
      return;
    }
    closedLoopController.setSetpoint(rpm, ControlType.kMAXMotionVelocityControl);
  }

  /**
   * Get the current flywheel speed. In simulation, returns the DCMotorSim velocity. On hardware,
   * reads the SPARK Flex encoder. Always positive (absolute value).
   */
  public double getCurrentRpm() {
    if (RobotBase.isSimulation()) {
      return simCurrentRpm;
    }
    return Math.abs(encoder.getVelocity());
  }
}
