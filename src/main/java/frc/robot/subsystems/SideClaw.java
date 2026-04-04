package frc.robot.subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.RelativeEncoder;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.FeedbackSensor;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import org.littletonrobotics.junction.Logger;

/**
 * Side claw subsystem. Single NEO motor with position PID running on SPARK MAX onboard controller.
 */
public class SideClaw extends SubsystemBase {

  private final SparkMax vertical =
      new SparkMax(Constants.SideClaw.kVerticalMotorId, MotorType.kBrushless);

  private final SparkClosedLoopController clc = vertical.getClosedLoopController();
  private final RelativeEncoder encoder = vertical.getEncoder();

  public SideClaw() {
    SparkMaxConfig vConfig = new SparkMaxConfig();
    vConfig
        .smartCurrentLimit(30)
        .inverted(false)
        .idleMode(IdleMode.kBrake)
        .closedLoop
        .feedbackSensor(FeedbackSensor.kPrimaryEncoder)
        .p(Constants.SideClaw.kP)
        .i(0)
        .d(0)
        .outputRange(-1, 1)
        .feedForward
        .kS(Constants.SideClaw.kS)
        .kV(Constants.SideClaw.kV)
        .kA(0);

    vertical.configure(vConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  @Override
  public void periodic() {
    Logger.recordOutput("SideClaw/Position", encoder.getPosition());
    Logger.recordOutput("SideClaw/CurrentAmps", vertical.getOutputCurrent());
    Logger.recordOutput("SideClaw/AppliedOutput", vertical.getAppliedOutput());
  }

  /**
   * Set the target claw position using onboard position PID.
   *
   * @param position target position in encoder rotations
   */
  public void setTargetPosition(double position) {
    clc.setSetpoint(position, ControlType.kPosition);
  }

  /** Reset the claw encoder to zero. */
  public void resetEncoder() {
    encoder.setPosition(0);
  }
}
