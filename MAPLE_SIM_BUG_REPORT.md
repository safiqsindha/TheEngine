# maple-sim GitHub Issue Draft
## For: Shenzhen-Robotics-Alliance/maple-sim
## File at: https://github.com/Shenzhen-Robotics-Alliance/maple-sim/issues/new

---

### Issue Title:
**Swerve modules produce reversed propelling force with REV SPARK MAX / NEO configuration via YAGSL**

### Labels:
`bug`, `simulation`, `rev-hardware`

---

### Description

When using maple-sim 0.4.0-beta integrated via YAGSL (2026.3.12) with REV SPARK MAX
motor controllers and NEO Brushless motors, the swerve module propelling forces are
applied in the wrong direction. Commanding forward velocity produces backward motion
in the physics simulation.

### Hardware Configuration
- **Motor controllers:** REV SPARK MAX (sparkmax type in YAGSL JSON)
- **Drive motors:** NEO Brushless
- **Steer motors:** NEO Brushless
- **Absolute encoders:** Thrifty 10-Pin Magnetic (attached to SPARK MAX data port)
- **Swerve modules:** Thrifty Swerve
- **YAGSL version:** 2026.3.12
- **maple-sim version:** 0.4.0-beta
- **WPILib version:** 2026.2.1

### Steps to Reproduce

1. Create a YAGSL swerve project with SPARK MAX / NEO configuration
2. Configure maple-sim simulation via YAGSL's built-in integration
3. Run `./gradlew simulateJava`
4. Command a forward chassis speed of `vx = 2.0 m/s` via `driveRobotRelative(new ChassisSpeeds(2.0, 0, 0))`
5. Observe the physics body velocity in AdvantageScope or via `swerveDrive.getRobotVelocity()`

### Expected Behavior
Robot accelerates forward at approximately 2.0 m/s in the +X direction.

### Actual Behavior
Robot accelerates **backward** with measured physics velocity of approximately `(-0.49, -0.30)`.
The propelling forces are actively reversed — the robot moves in the opposite direction of the
commanded velocity.

### Evidence
- Commanding `vx = +2.0` produces actual `vx ≈ -0.49`
- The sign is consistently inverted (not random noise or drift)
- This occurs for all four swerve modules simultaneously
- The behavior is specific to the dyn4j physics pipeline — when we bypass the physics
  (manual kinematic integration), the robot moves correctly

### Root Cause Analysis

We believe the issue is a sign convention mismatch between REV motor models and the
force calculation in `SwerveModuleSimulation`. Specifically:

**The propelling force direction vector appears to be computed using a motor rotation
convention that matches CTRE motors (Kraken X60, Falcon 500) but is inverted for
REV NEO motors when accessed through YAGSL's SPARK MAX abstraction layer.**

The force pipeline is approximately:
```
Motor voltage → Motor torque → Wheel torque (via gear ratio) → Propelling force → dyn4j body force
```

Somewhere in this pipeline, the sign of the force is negated for REV motors. Possible
locations:

1. **`SwerveModuleSimulation.getPropellingForce()`** — The module facing angle or
   force direction vector may assume CTRE's positive rotation convention.

2. **YAGSL's maple-sim shim** — When YAGSL feeds motor velocity/voltage into
   maple-sim's `SwerveModuleSimulation`, it may not account for the sign difference
   between `CANSparkMax.getEncoder().getVelocity()` (REV convention) and
   `TalonFX.getVelocity()` (CTRE convention).

3. **`DriveTrainSimulationConfig` motor model** — The `DCMotor.getNEO(1)` model
   may have a different sign convention than `DCMotor.getKrakenX60(1)` that isn't
   accounted for in the force calculation.

### Note on Testing Coverage

The maple-sim project README for the Maple-Swerve-Skeleton states:
> "This project supports Rev hardware. However, it has not been tested on a physical
> Rev Chassis simply because we don't have one."

This suggests the REV code path may not have been validated against expected behavior,
which is consistent with our findings.

### Workaround

We've implemented a kinematic bypass that works for both autonomous and teleop:

```java
// In SwerveSubsystem.java — store commanded speeds for sim bypass
private ChassisSpeeds lastCommandedSpeeds = new ChassisSpeeds();

public void driveRobotRelative(ChassisSpeeds speeds) {
    if (Robot.isSimulation()) {
        lastCommandedSpeeds = speeds;
    }
    swerveDrive.drive(speeds);
}

public void drive(Translation2d translation, double rotation, boolean fieldRelative) {
    if (Robot.isSimulation()) {
        ChassisSpeeds speeds;
        if (fieldRelative) {
            speeds = ChassisSpeeds.fromFieldRelativeSpeeds(
                translation.getX(), translation.getY(), rotation, getHeading());
        } else {
            speeds = new ChassisSpeeds(
                translation.getX(), translation.getY(), rotation);
        }
        lastCommandedSpeeds = speeds;
    }
    swerveDrive.drive(translation, rotation, fieldRelative, false);
}

@Override
public void periodic() {
    if (Robot.isSimulation() && lastCommandedSpeeds != null) {
        // Manually integrate position, bypassing broken physics
        double dt = 0.02; // 20ms loop
        Pose2d currentPose = getPose();
        Pose2d newPose = new Pose2d(
            currentPose.getX() + lastCommandedSpeeds.vxMetersPerSecond * dt,
            currentPose.getY() + lastCommandedSpeeds.vyMetersPerSecond * dt,
            currentPose.getRotation().plus(
                new Rotation2d(lastCommandedSpeeds.omegaRadiansPerSecond * dt))
        );
        resetOdometry(newPose);
    }
}
```

This kinematic bypass produces correct motion for all drive modes (autonomous,
teleop, pathfinding) but sacrifices the physics fidelity that maple-sim is designed
to provide (no collision detection, no friction modeling, no skid simulation).

### Suggested Fix

The most likely fix is a sign correction in the force calculation path for REV motors.
If the issue is in `SwerveModuleSimulation`, the fix would be:

```java
// In SwerveModuleSimulation.java (pseudocode)
double propellingForce = wheelTorque / wheelRadius;

// Add motor-type-aware sign correction:
// REV NEO positive rotation is opposite to CTRE convention
if (motorType.isREV()) {
    propellingForce = -propellingForce;
}
```

Alternatively, if the issue is in YAGSL's maple-sim integration layer, the fix would
be in how YAGSL reports motor velocity/position to maple-sim's simulation update method.

### Environment
- **OS:** macOS (Apple Silicon)
- **Java:** 17
- **YAGSL:** 2026.3.12 (via vendordep yagsl-2026.3.12.json)
- **maple-sim:** 0.4.0-beta (bundled with YAGSL)
- **Additional vendordeps:** REVLib, ThriftyLib, ReduxLib

### Team Information
FRC Team 2950 — The Devastators

---

## How to Submit

1. Go to: https://github.com/Shenzhen-Robotics-Alliance/maple-sim/issues/new
2. Select "Bug Report" template
3. Copy the title and description above
4. Add labels: bug, simulation
5. Submit

If the maple-sim team wants a minimal reproduction project, we can provide a stripped-down
YAGSL project with SPARK MAX configs that demonstrates the issue.
