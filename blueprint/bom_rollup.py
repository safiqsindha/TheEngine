"""
The Blueprint — Full Robot BOM Rollup (B.8)
Team 2950 — The Devastators

Aggregates specs from all mechanism generators into a unified
Bill of Materials with:
  - Total weight budget vs 125 lb limit
  - Combined parts list (de-duplicated)
  - Total motor count + CAN device count
  - Current draw budget (peak and sustained)
  - Software constants master list

Usage:
  python3 bom_rollup.py rollup --elevator competition --intake coral_2026 --flywheel coral_2026
  python3 bom_rollup.py rollup --all-defaults
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from motor_model import MOTOR_DB

# Import generators
from elevator_generator import generate_elevator, PRESETS as ELEVATOR_PRESETS
from intake_generator import generate_intake, PRESETS as INTAKE_PRESETS
from flywheel_generator import generate_flywheel, PRESETS as FLYWHEEL_PRESETS
from arm_generator import generate_arm, PRESETS as ARM_PRESETS
from climber_generator import generate_climber, PRESETS as CLIMBER_PRESETS
from conveyor_generator import generate_conveyor, PRESETS as CONVEYOR_PRESETS

BASE_DIR = Path(__file__).parent

# FRC weight limit
MAX_ROBOT_WEIGHT_LB = 125.0
# FRC max circuit breakers (40A slots on PDP/PDH)
MAX_40A_SLOTS = 20
# Typical CAN device limit before latency concerns
CAN_WARNING_THRESHOLD = 25


@dataclass
class MotorAllocation:
    """Tracks motor usage across mechanisms."""
    mechanism: str = ""
    motor_type: str = ""
    motor_name: str = ""
    count: int = 0
    current_limit_a: float = 40.0
    peak_current_a: float = 0.0
    holding_current_a: float = 0.0


@dataclass
class BOMRollup:
    """Complete robot Bill of Materials rollup."""
    # Mechanism specs (stored as dicts for JSON serialization)
    mechanisms: dict = field(default_factory=dict)

    # Weight budget
    mechanism_weight_lb: float = 0.0
    drivetrain_weight_lb: float = 35.0  # typical swerve drivetrain
    bumper_weight_lb: float = 8.0
    battery_weight_lb: float = 13.0
    electronics_weight_lb: float = 5.0  # PDP, Rio, radio, etc.
    total_weight_lb: float = 0.0
    weight_margin_lb: float = 0.0
    weight_ok: bool = True

    # Motor / electrical budget
    motors: list = field(default_factory=list)
    total_motor_count: int = 0
    total_can_devices: int = 0
    peak_current_total_a: float = 0.0
    sustained_current_total_a: float = 0.0

    # Combined parts list
    combined_parts: list = field(default_factory=list)

    # Master software constants
    software_constants: dict = field(default_factory=dict)

    notes: list = field(default_factory=list)


def _extract_preset_params(preset_dict):
    """Extract params from a preset dict — handles both formats.
    Elevator presets: params at top level (with 'description' key to skip).
    Other presets: params inside a 'params' key.
    """
    if "params" in preset_dict:
        return preset_dict["params"].copy()
    return {k: v for k, v in preset_dict.items() if k != "description"}


def rollup_robot(
    elevator_preset: Optional[str] = None,
    intake_preset: Optional[str] = None,
    flywheel_preset: Optional[str] = None,
    arm_preset: Optional[str] = None,
    climber_preset: Optional[str] = None,
    conveyor_preset: Optional[str] = None,
    drivetrain_weight_lb: float = 35.0,
    bumper_weight_lb: float = 8.0,
) -> BOMRollup:
    """Generate a full robot BOM from mechanism presets."""
    rollup = BOMRollup(
        drivetrain_weight_lb=drivetrain_weight_lb,
        bumper_weight_lb=bumper_weight_lb,
    )

    # Generate each mechanism that's requested
    if elevator_preset:
        p = _extract_preset_params(ELEVATOR_PRESETS[elevator_preset])
        p["name"] = f"2950 {elevator_preset.title()} Elevator"
        spec = generate_elevator(**p)
        rollup.mechanisms["elevator"] = {
            "preset": elevator_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.motor_type,
            "motor_count": spec.motor_count,
            "current_limit_a": spec.current_limit_a,
            "peak_current_a": spec.peak_current_a,
            "holding_current_a": getattr(spec, 'holding_current_a', 0),
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    if intake_preset:
        p = _extract_preset_params(INTAKE_PRESETS[intake_preset])
        spec = generate_intake(**p, preset_name=intake_preset)
        rollup.mechanisms["intake"] = {
            "preset": intake_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.roller_motor_type,
            "motor_count": spec.roller_motor_count,
            "deploy_motor": spec.deploy_motor_type if spec.deploy_type != "none" else None,
            "current_limit_a": 40.0,
            "peak_current_a": 40.0,
            "holding_current_a": 5.0,
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    if flywheel_preset:
        p = _extract_preset_params(FLYWHEEL_PRESETS[flywheel_preset])
        spec = generate_flywheel(**p, preset_name=flywheel_preset)
        rollup.mechanisms["flywheel"] = {
            "preset": flywheel_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.motor_type,
            "motor_count": spec.motor_count,
            "current_limit_a": spec.current_limit_a,
            "peak_current_a": spec.spinup_peak_current_a,
            "holding_current_a": spec.holding_current_a,
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    if arm_preset:
        p = _extract_preset_params(ARM_PRESETS[arm_preset])
        spec = generate_arm(**p, preset_name=arm_preset)
        rollup.mechanisms["arm"] = {
            "preset": arm_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.motor_type,
            "motor_count": spec.motor_count,
            "current_limit_a": spec.current_limit_a,
            "peak_current_a": spec.peak_current_a,
            "holding_current_a": spec.holding_current_a,
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    if climber_preset:
        p = _extract_preset_params(CLIMBER_PRESETS[climber_preset])
        spec = generate_climber(**p, preset_name=climber_preset)
        rollup.mechanisms["climber"] = {
            "preset": climber_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.motor_type,
            "motor_count": spec.motor_count,
            "current_limit_a": spec.current_limit_a,
            "peak_current_a": spec.peak_current_a,
            "holding_current_a": spec.holding_current_a,
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    if conveyor_preset:
        p = _extract_preset_params(CONVEYOR_PRESETS[conveyor_preset])
        spec = generate_conveyor(**p, preset_name=conveyor_preset)
        rollup.mechanisms["conveyor"] = {
            "preset": conveyor_preset,
            "weight_lb": spec.total_weight_lb,
            "motor_type": spec.motor_type,
            "motor_count": spec.motor_count,
            "current_limit_a": spec.current_limit_a,
            "peak_current_a": spec.current_limit_a,
            "holding_current_a": spec.holding_current_a,
            "parts": spec.parts_list,
            "software_constants": spec.software_constants,
        }

    # ── Aggregate weight ──
    rollup.mechanism_weight_lb = round(
        sum(m["weight_lb"] for m in rollup.mechanisms.values()), 2
    )
    rollup.total_weight_lb = round(
        rollup.mechanism_weight_lb +
        rollup.drivetrain_weight_lb +
        rollup.bumper_weight_lb +
        rollup.battery_weight_lb +
        rollup.electronics_weight_lb,
        2,
    )
    rollup.weight_margin_lb = round(MAX_ROBOT_WEIGHT_LB - rollup.total_weight_lb, 2)
    rollup.weight_ok = rollup.weight_margin_lb >= 0

    # ── Motor / electrical budget ──
    # Drivetrain motors (assumed 4x swerve drive + 4x swerve steer)
    rollup.motors = [
        MotorAllocation("drivetrain_drive", "kraken_x60", "Kraken X60", 4, 40.0, 40.0, 5.0),
        MotorAllocation("drivetrain_steer", "neo_550", "NEO 550", 4, 20.0, 20.0, 2.0),
    ]

    for mech_name, mech in rollup.mechanisms.items():
        alloc = MotorAllocation(
            mechanism=mech_name,
            motor_type=mech["motor_type"],
            motor_name=MOTOR_DB[mech["motor_type"]].name if mech["motor_type"] in MOTOR_DB else mech["motor_type"],
            count=mech["motor_count"],
            current_limit_a=mech.get("current_limit_a", 40.0),
            peak_current_a=mech.get("peak_current_a", 40.0),
            holding_current_a=mech.get("holding_current_a", 5.0),
        )
        rollup.motors.append(alloc)

        # Check for deploy motor (intake)
        if mech.get("deploy_motor") and mech["deploy_motor"] != "none":
            rollup.motors.append(MotorAllocation(
                mechanism=f"{mech_name}_deploy",
                motor_type=mech["deploy_motor"],
                motor_name=MOTOR_DB[mech["deploy_motor"]].name if mech["deploy_motor"] in MOTOR_DB else mech["deploy_motor"],
                count=1, current_limit_a=20.0, peak_current_a=20.0, holding_current_a=2.0,
            ))

    rollup.total_motor_count = sum(m.count for m in rollup.motors)
    # CAN devices: each motor controller + RoboRIO + PDP/PDH + sensors
    rollup.total_can_devices = rollup.total_motor_count + 3  # +Rio, PDP, one sensor

    rollup.peak_current_total_a = round(
        sum(m.peak_current_a * m.count for m in rollup.motors), 1
    )
    rollup.sustained_current_total_a = round(
        sum(m.holding_current_a * m.count for m in rollup.motors), 1
    )

    # ── Combined parts list ──
    rollup.combined_parts = []
    for mech_name, mech in rollup.mechanisms.items():
        for part in mech.get("parts", []):
            rollup.combined_parts.append({
                **part,
                "mechanism": mech_name,
            })

    # ── Master software constants ──
    for mech_name, mech in rollup.mechanisms.items():
        prefix = mech_name.upper()
        for key, val in mech.get("software_constants", {}).items():
            rollup.software_constants[f"{prefix}_{key}"] = val

    # ── Notes ──
    rollup.notes = []
    if not rollup.weight_ok:
        rollup.notes.append(f"OVERWEIGHT by {abs(rollup.weight_margin_lb)} lb — reduce mechanism weight or swap to lighter motors")
    elif rollup.weight_margin_lb < 5:
        rollup.notes.append(f"Tight weight margin ({rollup.weight_margin_lb} lb) — leave room for competition repairs")
    else:
        rollup.notes.append(f"Weight margin: {rollup.weight_margin_lb} lb — healthy")

    if rollup.total_motor_count > MAX_40A_SLOTS:
        rollup.notes.append(f"Motor count ({rollup.total_motor_count}) exceeds PDP 40A slots ({MAX_40A_SLOTS})")

    if rollup.total_can_devices > CAN_WARNING_THRESHOLD:
        rollup.notes.append(f"CAN bus has {rollup.total_can_devices} devices — watch for latency")

    if rollup.peak_current_total_a > 400:
        rollup.notes.append(f"Peak current draw ({rollup.peak_current_total_a}A) — battery sag likely under full load")

    return rollup


def display_rollup(rollup: BOMRollup):
    print(f"\n{'═' * 65}")
    print(f"  2950 FULL ROBOT BOM ROLLUP")
    print(f"  Generated by The Blueprint B.8")
    print(f"{'═' * 65}")

    # Weight budget
    weight_status = "[PASS]" if rollup.weight_ok else "[OVERWEIGHT]"
    print(f"\n  WEIGHT BUDGET (limit: {MAX_ROBOT_WEIGHT_LB} lb)")
    print(f"    Drivetrain:        {rollup.drivetrain_weight_lb} lb")
    for name, mech in rollup.mechanisms.items():
        print(f"    {name.capitalize():19s}{mech['weight_lb']} lb")
    print(f"    Bumpers:           {rollup.bumper_weight_lb} lb")
    print(f"    Battery:           {rollup.battery_weight_lb} lb")
    print(f"    Electronics:       {rollup.electronics_weight_lb} lb")
    print(f"    {'─' * 35}")
    print(f"    TOTAL:             {rollup.total_weight_lb} lb {weight_status}")
    print(f"    MARGIN:            {rollup.weight_margin_lb} lb")

    # Motor budget
    print(f"\n  MOTOR BUDGET ({rollup.total_motor_count} motors, {rollup.total_can_devices} CAN devices)")
    print(f"    {'Mechanism':<20s} {'Motor':<20s} {'Qty':>4s} {'Peak':>6s} {'Hold':>6s}")
    print(f"    {'─' * 56}")
    for m in rollup.motors:
        print(f"    {m.mechanism:<20s} {m.motor_name:<20s} {m.count:>4d} {m.peak_current_a:>5.0f}A {m.holding_current_a:>5.1f}A")
    print(f"    {'─' * 56}")
    print(f"    {'TOTAL':<20s} {'':20s} {rollup.total_motor_count:>4d} {rollup.peak_current_total_a:>5.0f}A {rollup.sustained_current_total_a:>5.1f}A")

    # Notes
    if rollup.notes:
        print(f"\n  NOTES")
        for n in rollup.notes:
            print(f"    • {n}")

    print(f"\n{'═' * 65}\n")


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python3 bom_rollup.py rollup --elevator competition --intake coral_2026 --climber deep_climb")
        print("  python3 bom_rollup.py rollup --all-defaults")
        return

    if args[0] == "rollup":
        params = {}
        i = 1
        all_defaults = False
        while i < len(args):
            if args[i] == "--all-defaults":
                all_defaults = True; i += 1
            elif args[i] == "--elevator" and i + 1 < len(args):
                params["elevator_preset"] = args[i + 1]; i += 2
            elif args[i] == "--intake" and i + 1 < len(args):
                params["intake_preset"] = args[i + 1]; i += 2
            elif args[i] == "--flywheel" and i + 1 < len(args):
                params["flywheel_preset"] = args[i + 1]; i += 2
            elif args[i] == "--arm" and i + 1 < len(args):
                params["arm_preset"] = args[i + 1]; i += 2
            elif args[i] == "--climber" and i + 1 < len(args):
                params["climber_preset"] = args[i + 1]; i += 2
            elif args[i] == "--conveyor" and i + 1 < len(args):
                params["conveyor_preset"] = args[i + 1]; i += 2
            else:
                print(f"Unknown arg: {args[i]}"); return

        if all_defaults:
            params = {
                "elevator_preset": "competition",
                "intake_preset": "coral_2026",
                "flywheel_preset": "coral_2026",
                "climber_preset": "deep_climb",
                "conveyor_preset": "single_stage",
            }

        rollup = rollup_robot(**params)
        display_rollup(rollup)

        filepath = BASE_DIR / "2950_robot_bom.json"
        # Convert MotorAllocation objects to dicts for JSON
        export = {
            "mechanisms": rollup.mechanisms,
            "weight": {
                "mechanism_lb": rollup.mechanism_weight_lb,
                "drivetrain_lb": rollup.drivetrain_weight_lb,
                "bumpers_lb": rollup.bumper_weight_lb,
                "battery_lb": rollup.battery_weight_lb,
                "electronics_lb": rollup.electronics_weight_lb,
                "total_lb": rollup.total_weight_lb,
                "margin_lb": rollup.weight_margin_lb,
                "ok": rollup.weight_ok,
            },
            "motors": [asdict(m) for m in rollup.motors],
            "total_motor_count": rollup.total_motor_count,
            "total_can_devices": rollup.total_can_devices,
            "peak_current_a": rollup.peak_current_total_a,
            "sustained_current_a": rollup.sustained_current_total_a,
            "software_constants": rollup.software_constants,
            "notes": rollup.notes,
        }
        with open(filepath, "w") as f:
            json.dump(export, f, indent=2)
        print(f"BOM saved to: {filepath}")


if __name__ == "__main__":
    main()
