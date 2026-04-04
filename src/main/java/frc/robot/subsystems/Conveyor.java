package frc.robot.subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.Constants;
import org.littletonrobotics.junction.Logger;

/**
 * Conveyor subsystem. Controls a brushed conveyor belt motor and a brushless spindexer motor that
 * index fuel into the flywheel.
 */
public class Conveyor extends SubsystemBase {

  private final SparkMax conveyorMotor =
      new SparkMax(Constants.Conveyor.kConveyorMotorId, MotorType.kBrushed);

  private final SparkMax spindexerMotor =
      new SparkMax(Constants.Conveyor.kSpindexerMotorId, MotorType.kBrushless);

  public Conveyor() {
    SparkMaxConfig config = new SparkMaxConfig();
    config.inverted(false).idleMode(IdleMode.kBrake).smartCurrentLimit(40);
    conveyorMotor.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    SparkMaxConfig spinConfig = new SparkMaxConfig();
    spinConfig.apply(config).inverted(true);
    spindexerMotor.configure(
        spinConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  @Override
  public void periodic() {
    Logger.recordOutput("Conveyor/ConveyorOutput", conveyorMotor.getAppliedOutput());
    Logger.recordOutput("Conveyor/SpindexerOutput", spindexerMotor.getAppliedOutput());
    Logger.recordOutput("Conveyor/ConveyorCurrentAmps", conveyorMotor.getOutputCurrent());
    Logger.recordOutput("Conveyor/SpindexerCurrentAmps", spindexerMotor.getOutputCurrent());
  }

  /**
   * Set conveyor belt and spindexer to the same percent output.
   *
   * @param percent output (-1 to 1)
   */
  public void setConveyor(double percent) {
    conveyorMotor.set(percent);
    spindexerMotor.set(percent);
  }
}
