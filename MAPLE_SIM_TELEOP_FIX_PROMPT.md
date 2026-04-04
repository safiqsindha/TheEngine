# maple-sim Teleop Sim Fix — Paste into Claude Code

There is a known upstream bug in maple-sim 0.4.0-beta where swerve module propelling
forces are inverted for REV SPARK MAX / NEO configurations. We already have a working
kinematic bypass in periodic() that manually integrates position from lastCommandedSpeeds
for the driveRobotRelative() path. Autonomous and pathfinding work correctly in sim.

The problem: the drive(Translation2d, double, boolean) method used by teleop DriveCommand
does NOT go through this bypass. Teleop driving in sim is broken — robot moves backward
or not at all.

Implement Option A — extend the bypass to cover drive() too:

1. In SwerveSubsystem.java, find the drive(Translation2d translation, double rotation,
   boolean fieldRelative) method.

2. Add a sim check at the top of this method that converts the Translation2d + rotation
   into a ChassisSpeeds and stores it in lastCommandedSpeeds (the same field used by
   the existing driveRobotRelative bypass).

3. The conversion is:
   - If fieldRelative: ChassisSpeeds.fromFieldRelativeSpeeds(translation.getX(),
     translation.getY(), rotation, getHeading())
   - If not fieldRelative: new ChassisSpeeds(translation.getX(), translation.getY(), rotation)

4. Only do this when Robot.isSimulation() is true. The real hardware path must remain
   completely unchanged.

5. The existing periodic() bypass should already pick up lastCommandedSpeeds and do the
   kinematic integration. Verify it does.

6. After implementing, test by running ./gradlew simulateJava. In the SimGUI driver
   station panel, manually set joystick axis values (or plug in a controller). The robot
   should now move correctly in sim when driven via teleop.

7. Add a comment in the code explaining this is a workaround for maple-sim 0.4.0-beta
   force direction bug with REV motors, and reference MAPLE_SIM_BUG_REPORT.md.

8. Log to PROGRESS.md: "Implemented maple-sim teleop bypass. Both autonomous and teleop
   now work correctly in simulation via kinematic integration. Upstream bug documented
   in MAPLE_SIM_BUG_REPORT.md."

This is a ~5-10 line change. Do not refactor the existing bypass — just extend it to
cover the additional drive() entry point.
