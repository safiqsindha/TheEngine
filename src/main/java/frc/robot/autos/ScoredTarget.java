package frc.robot.autos;

import edu.wpi.first.math.geometry.Pose2d;

/**
 * A candidate autonomous target with its computed utility score.
 *
 * @param actionType what the robot would do at this target
 * @param targetPose field-relative pose to drive to
 * @param utility computed score (higher = more desirable)
 */
public record ScoredTarget(ActionType actionType, Pose2d targetPose, double utility) {}
