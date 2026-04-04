#!/usr/bin/env python3
"""
Pre-match health check for FRC Team 2950 — The Devastators.

Connects to the robot via NetworkTables 4 and runs a checklist of
pass/fail checks before enabling the robot at competition.

Usage:
    python3 tools/pre_match_check.py [--host ROBOT_IP]

Default host: 10.29.50.2  (roboRIO mDNS: roborio-2950-frc.local)
For sim:      python3 tools/pre_match_check.py --host localhost

Requires: pyntcore (pip install pyntcore)
"""

import argparse
import sys
import time

try:
    import ntcore
except ImportError:
    print("ERROR: pyntcore not installed. Run: pip install pyntcore")
    sys.exit(1)

# ── Thresholds ────────────────────────────────────────────────────────────────
BATTERY_WARN_VOLTS = 12.0       # Warn if battery below this at match start
BATTERY_FAIL_VOLTS = 11.0       # Fail if below this
CAN_UTIL_WARN_PCT  = 70.0       # Warn if CAN bus utilization above this
CAN_UTIL_FAIL_PCT  = 90.0       # Fail if above this
MATCH_TIME_STALE   = -1.0       # DriverStation not yet connected to FMS

PASS  = "\033[92m PASS \033[0m"
WARN  = "\033[93m WARN \033[0m"
FAIL  = "\033[91m FAIL \033[0m"
INFO  = "\033[96m INFO \033[0m"


def check(label, result, detail=""):
    icon = {True: PASS, False: FAIL, "warn": WARN, "info": INFO}[result]
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{icon}] {label}{suffix}")
    return result is True


def run_checks(nt_host: str):
    # ── Connect ───────────────────────────────────────────────────────────────
    inst = ntcore.NetworkTableInstance.getDefault()
    inst.setServer(nt_host)
    inst.startClient4("pre_match_check")

    print(f"\nConnecting to NT4 at {nt_host}...")
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if inst.isConnected():
            break
        time.sleep(0.1)

    if not inst.isConnected():
        print(f"  [{FAIL}] Could not connect to NT4 server at {nt_host}")
        print("         Is the robot powered on and connected?")
        sys.exit(1)

    print(f"  [{PASS}] NT4 connected\n")
    time.sleep(0.5)  # Let topics populate

    # ── Subscribe to keys ─────────────────────────────────────────────────────
    robot_table  = inst.getTable("AdvantageKit").getSubTable("Robot")
    drive_table  = inst.getTable("AdvantageKit").getSubTable("Drive")
    vision_table = inst.getTable("AdvantageKit").getSubTable("Vision")
    smart_dash   = inst.getTable("SmartDashboard")

    def get(table, key, default=None):
        entry = table.getEntry(key)
        val = entry.getValue()
        if val is None or not val.isValid():
            return default
        return val.value()

    # ── Battery voltage ───────────────────────────────────────────────────────
    print("── Battery ──────────────────────────────────────────────────────────")
    volts = get(robot_table, "BatteryVoltage", -1.0)
    if volts < 0:
        check("Battery voltage readable", False, "key missing — robot may not be in teleop yet")
    elif volts < BATTERY_FAIL_VOLTS:
        check(f"Battery voltage ({volts:.2f}V)", False, f"CHARGE BATTERY — below {BATTERY_FAIL_VOLTS}V")
    elif volts < BATTERY_WARN_VOLTS:
        check(f"Battery voltage ({volts:.2f}V)", "warn", f"below {BATTERY_WARN_VOLTS}V, consider fresh battery")
    else:
        check(f"Battery voltage ({volts:.2f}V)", True)

    brownout = get(robot_table, "BrownoutActive", None)
    if brownout is not None:
        check("No brownout active", not brownout, "BrownoutActive=True — battery critically low")

    # ── CAN bus ───────────────────────────────────────────────────────────────
    print("\n── CAN Bus ──────────────────────────────────────────────────────────")
    can_util = get(robot_table, "CANBusUtilization", -1.0)
    if can_util < 0:
        check("CAN utilization readable", False, "key missing")
    elif can_util > CAN_UTIL_FAIL_PCT:
        check(f"CAN utilization ({can_util:.1f}%)", False, f"above {CAN_UTIL_FAIL_PCT}% — check for bad motors/wiring")
    elif can_util > CAN_UTIL_WARN_PCT:
        check(f"CAN utilization ({can_util:.1f}%)", "warn", "elevated — watch for loop overruns")
    else:
        check(f"CAN utilization ({can_util:.1f}%)", True)

    # ── Drive / odometry ─────────────────────────────────────────────────────
    print("\n── Drive ────────────────────────────────────────────────────────────")
    pose_entry = drive_table.getEntry("Pose")
    pose_val   = pose_entry.getValue()
    check("Odometry pose publishing", pose_val is not None and pose_val.isValid(),
          "Drive/Pose key not found — swerve may not have initialized")

    gyro_entry = drive_table.getEntry("GyroYaw")
    gyro_val   = gyro_entry.getValue()
    check("Gyro publishing", gyro_val is not None and gyro_val.isValid(),
          "Drive/GyroYaw key not found")

    # ── Vision ────────────────────────────────────────────────────────────────
    print("\n── Vision ───────────────────────────────────────────────────────────")
    has_target = get(vision_table, "HasTarget", None)
    if has_target is None:
        check("Vision subsystem publishing", False, "Vision/HasTarget key missing")
    else:
        check("Vision subsystem publishing", True)
        if has_target:
            tag_count = get(vision_table, "TagCount", 0)
            avg_dist  = get(vision_table, "AvgTagDistM", 0.0)
            latency   = get(vision_table, "LatencyMs", 0.0)
            check(f"AprilTag locked ({int(tag_count)} tags, {avg_dist:.1f}m, {latency:.0f}ms latency)", True)
        else:
            check("Limelight sees AprilTags", "warn",
                  "No target — OK if pointed away from tags, verify at field")

    pipeline_entry = inst.getTable("limelight").getEntry("pipeline")
    pipeline_val   = pipeline_entry.getValue()
    if pipeline_val is not None and pipeline_val.isValid():
        pipeline_idx = int(pipeline_val.value())
        pipeline_name = "AprilTag" if pipeline_idx == 0 else "Neural" if pipeline_idx == 1 else f"idx={pipeline_idx}"
        check(f"Pipeline active: {pipeline_name}", True)
    else:
        check("Pipeline command publishing", False, "limelight/pipeline key not found")

    # ── Autonomous chooser ────────────────────────────────────────────────────
    print("\n── Autonomous ───────────────────────────────────────────────────────")
    auto_entry = smart_dash.getEntry("Auto Chooser/active")
    auto_val   = auto_entry.getValue()
    if auto_val is not None and auto_val.isValid():
        auto_name = auto_val.value()
        check(f"Auto selected: \"{auto_name}\"", True)
        if "Safe Mode" in auto_name:
            check("Auto is NOT safe mode fallback", "warn",
                  "Safe Mode selected — is Limelight working?")
    else:
        check("Auto chooser readable", False, "SmartDashboard/Auto Chooser not found")

    # ── Match phase ───────────────────────────────────────────────────────────
    print("\n── Match Phase ──────────────────────────────────────────────────────")
    phase = get(robot_table, "Phase", None)
    if phase is not None:
        check(f"Robot phase: {phase}", True)
    else:
        check("Match phase logging", False, "Robot/Phase key missing")

    match_time = get(robot_table, "MatchTimeRemaining", MATCH_TIME_STALE)
    if match_time == MATCH_TIME_STALE:
        check("FMS/DS match time", "warn", "DriverStation not sending match time (-1) — OK until FMS connected")
    else:
        check(f"Match time: {match_time:.0f}s remaining", True)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n─────────────────────────────────────────────────────────────────────")
    inst.stopClient()


def main():
    parser = argparse.ArgumentParser(description="Pre-match health check for Team 2950")
    parser.add_argument("--host", default="10.29.50.2",
                        help="Robot IP or hostname (default: 10.29.50.2). Use 'localhost' for sim.")
    args = parser.parse_args()

    print("=" * 69)
    print("  FRC Team 2950 — The Devastators — Pre-Match Health Check")
    print("=" * 69)

    run_checks(args.host)

    print("  Run with --host localhost to check the simulator.")
    print("  Fix all FAIL items before enabling. WARN items are optional.\n")


if __name__ == "__main__":
    main()
