package frc.robot;

import choreo.auto.AutoFactory;
import edu.wpi.first.wpilibj.smartdashboard.SendableChooser;
import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.autos.AutonomousStrategy;
import frc.robot.commands.AutoAlignCommand;
import frc.robot.commands.AutoScoreCommand;
import frc.robot.commands.ChoreoAutoCommand;
import frc.robot.commands.ConveyorControl;
import frc.robot.commands.DriveCommand;
import frc.robot.commands.DriveToGamePieceCommand;
import frc.robot.commands.FullAutonomousCommand;
import frc.robot.commands.IntakeControl;
import frc.robot.commands.flywheel.FlywheelAim;
import frc.robot.commands.flywheel.FlywheelAutoFeed;
import frc.robot.commands.flywheel.FlywheelDynamic;
import frc.robot.commands.flywheel.FlywheelStatic;
import frc.robot.subsystems.Conveyor;
import frc.robot.subsystems.Flywheel;
import frc.robot.subsystems.Intake;
import frc.robot.subsystems.LEDs;
import frc.robot.subsystems.LEDs.AnimationType;
import frc.robot.subsystems.SuperstructureStateMachine;
import frc.robot.subsystems.SwerveSubsystem;
import frc.robot.subsystems.VisionSubsystem;

/**
 * This class is where the bulk of the robot should be declared. Since Command-based is a
 * "declarative" paradigm, very little robot logic should actually be handled in the Robot class.
 * Instead, the structure of the robot (including subsystems, commands, and trigger mappings) should
 * be declared here.
 */
public class RobotContainer {

  // ─── Subsystems ───
  private final SwerveSubsystem swerve = new SwerveSubsystem();
  public final VisionSubsystem vision = new VisionSubsystem(swerve);
  private final LEDs leds = new LEDs();
  public final Intake intake = new Intake();
  private final Conveyor conveyor = new Conveyor();
  private final Flywheel flywheel = new Flywheel();
  private final SuperstructureStateMachine ssm = new SuperstructureStateMachine(intake);

  // ─── Controllers ───
  // ControllerAdapter auto-detects Xbox vs Pro Controller and remaps axes accordingly.
  // Kids use Xbox controllers at competition; Pro Controller works for sim testing.
  private final CommandXboxController driver =
      new CommandXboxController(Constants.OI.kDriverControllerPort);
  private final ControllerAdapter driverAdapter = new ControllerAdapter(driver);
  private final CommandXboxController operator =
      new CommandXboxController(Constants.OI.kOperatorControllerPort);

  // ─── Autonomous ───
  private final AutoFactory autoFactory = ChoreoAutoCommand.factory(swerve);
  private final SendableChooser<Command> autoChooser = new SendableChooser<>();
  private final AutonomousStrategy autonomousStrategy = new AutonomousStrategy();

  // ─── Driver Practice (simulation only) ───
  private final DriverPracticeMode practiceMode = new DriverPracticeMode(swerve);

  public RobotContainer() {
    configureDefaultCommands();
    configureDriverBindings();
    configureAutonomous();
  }

  private void configureDefaultCommands() {
    swerve.setDefaultCommand(
        new DriveCommand(
            swerve,
            () -> {
              driverAdapter.tick();
              return -driverAdapter.getLeftY();
            },
            () -> -driverAdapter.getLeftX(),
            () -> -driverAdapter.getRightX()));

    flywheel.setDefaultCommand(new FlywheelDynamic(flywheel, driver));
    intake.setDefaultCommand(new IntakeControl(intake, driver));
    conveyor.setDefaultCommand(new ConveyorControl(conveyor, driver));

    leds.setDefaultCommand(
        Commands.run(
                () -> leds.setAnimation(AnimationType.ENABLED_IDLE, Constants.LEDs.kPriorityIdle),
                leds)
            .ignoringDisable(true));
  }

  private void configureDriverBindings() {
    // A: zero gyro (robot facing away from driver)
    driver.a().onTrue(Commands.runOnce(swerve::zeroGyro, swerve));

    // Right bumper: auto-align to nearest AprilTag scoring target (driver keeps translation)
    driver
        .rightBumper()
        .whileTrue(
            new AutoAlignCommand(
                swerve, vision, () -> -driverAdapter.getLeftY(), () -> -driverAdapter.getLeftX()));

    // Y: lock wheels in X pattern (relocated from right bumper)
    driver.y().whileTrue(Commands.run(swerve::lock, swerve));

    // POV presets: static flywheel shots at known distances
    driver.povRight().whileTrue(new FlywheelStatic(flywheel, conveyor, 2400));
    driver.povDown().whileTrue(new FlywheelStatic(flywheel, conveyor, 2500));
    driver.povLeft().whileTrue(new FlywheelStatic(flywheel, conveyor, 3000));
    driver.povUp().whileTrue(new FlywheelStatic(flywheel, conveyor, 3500));

    // Left bumper: drive toward nearest detected game piece (driver keeps rotation)
    driver
        .leftBumper()
        .whileTrue(new DriveToGamePieceCommand(swerve, vision, () -> -driverAdapter.getRightX()));

    // Left trigger (axis > 0.5): manual flywheel aim + auto-feed (relocated from left bumper)
    driver
        .leftTrigger(0.5)
        .whileTrue(
            Commands.parallel(new FlywheelAim(swerve), new FlywheelAutoFeed(flywheel, conveyor)));

    // B: blink LEDs when vision has a target (diagnostic)
    driver
        .b()
        .whileTrue(
            Commands.run(
                () -> {
                  AnimationType anim =
                      vision.hasTarget() ? AnimationType.ALIGNING_BLINK : AnimationType.ERROR_FLASH;
                  leds.setAnimation(anim, Constants.LEDs.kPriorityAligning);
                },
                leds));

    // X: automated vision-aligned scoring sequence
    driver.x().onTrue(AutoScoreCommand.build(swerve, flywheel, conveyor, vision, ssm, leds));

    // Back + Start together: teleport robot back to scenario start pose (sim practice reset)
    // Uses combo to prevent accidental resets — Pro Controller ZR maps to Xbox Start (button 8)
    driver.back().and(driver.start()).onTrue(Commands.runOnce(practiceMode::resetToStart));
  }

  private void configureAutonomous() {
    // ── Default: leave-only (drive off the line) ─────────────────────────────
    autoChooser.addOption(
        "Shoot Only",
        Commands.parallel(new FlywheelAutoFeed(flywheel, conveyor), new FlywheelAim(swerve))
            .withTimeout(19));

    // ── Choreo mobility autos ────────────────────────────────────────────────
    // Requires corresponding .traj files in src/main/deploy/choreo/.
    // See ChoreoAutoCommand for trajectory file name constants.
    // "Leave Only (Raw)" uses direct driveRobotRelative to test swerve sim without Choreo.
    autoChooser.setDefaultOption("Leave Only", ChoreoAutoCommand.leaveRoutine(autoFactory).cmd());

    autoChooser.addOption(
        "Leave Only (Raw)",
        Commands.sequence(
            Commands.waitSeconds(3.0),
            Commands.run(
                    () ->
                        swerve.driveRobotRelative(
                            new edu.wpi.first.math.kinematics.ChassisSpeeds(1.0, 0, 0)),
                    swerve)
                .withTimeout(2.0)));

    autoChooser.addOption(
        "Score + Leave",
        ChoreoAutoCommand.scoreAndLeaveRoutine(autoFactory, flywheel, conveyor).cmd());

    autoChooser.addOption(
        "2 Coral", ChoreoAutoCommand.twoCoralRoutine(autoFactory, flywheel, conveyor, ssm).cmd());

    autoChooser.addOption(
        "3 Coral", ChoreoAutoCommand.threeCoralRoutine(autoFactory, flywheel, conveyor, ssm).cmd());

    // ── Full Autonomous (Phase 3) ─────────────────────────────────────────────
    // Strategy-driven loop: evaluate targets → pathfind → execute → repeat.
    // FuelDetectionConsumer feeds confirmed FUEL positions from the Limelight
    // neural detector (llpython array) into AutonomousStrategy each cycle.
    autoChooser.addOption(
        "Full Autonomous",
        new FullAutonomousCommand(
            swerve,
            ssm,
            autonomousStrategy,
            vision::getFuelPositions,
            vision::getOpponentPositions));

    // ── Safe Mode (no vision, no pathfinding — timed dead reckoning) ─────────
    // Fallback if Limelight fails at competition. Drives forward 2m, shoots, then stops.
    autoChooser.addOption(
        "Safe Mode (No Vision)",
        Commands.sequence(
            // Drive forward at 1.0 m/s for 2 seconds (~2m)
            Commands.run(
                    () ->
                        swerve.driveRobotRelative(
                            new edu.wpi.first.math.kinematics.ChassisSpeeds(1.0, 0, 0)),
                    swerve)
                .withTimeout(2.0),
            // Stop
            Commands.runOnce(
                () -> swerve.driveRobotRelative(new edu.wpi.first.math.kinematics.ChassisSpeeds()),
                swerve),
            // Fire preloaded game piece (blind shot at preset RPM)
            Commands.parallel(
                    new FlywheelStatic(flywheel, conveyor, 2800),
                    Commands.run(
                        () ->
                            leds.setAnimation(
                                AnimationType.ALIGNING_BLINK, Constants.LEDs.kPriorityAlert),
                        leds))
                .withTimeout(3.0)));

    SmartDashboard.putData("Auto Chooser", autoChooser);
  }

  public Command getAutonomousCommand() {
    return autoChooser.getSelected();
  }

  public void setMotorBrake(boolean brake) {
    swerve.setMotorBrake(brake);
  }

  public DriverPracticeMode getPracticeMode() {
    return practiceMode;
  }
}
