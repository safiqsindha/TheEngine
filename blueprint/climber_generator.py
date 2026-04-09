"""
The Blueprint — Parametric Climber Generator (B.6)
Team 2950 — The Devastators

Generates a climber specification from parameters:
  - Climb height (distance from hook engagement to final position)
  - Robot weight (determines motor/winch requirements)
  - Climb style (winch, telescope, hook-and-pull)
  - Motor type + count
  - Current limit + efficiency

Physics: winch torque = weight × spool_radius / (gear_ratio × efficiency),
climb time from current-limited Euler simulation.
Based on 254/1678 championship climber architectures.

Usage:
  python3 climber_generator.py generate --preset deep_climb
  python3 climber_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from motor_model import (
    DCMotor, MOTOR_DB, simulate_linear_motion,
    V_NOMINAL, LB_TO_N, IN_TO_M, GRAVITY_MPS2, RPM_TO_RADS,
)

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# CLIMBER SPEC
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ClimberSpec:
    """Complete parametric climber specification."""
    # Inputs
    climb_height_in: float = 26.0
    robot_weight_lb: float = 125.0
    climb_style: str = "winch"
    motor_type: str = "neo"
    motor_count: int = 2
    gear_ratio: float = 50.0
    spool_diameter_in: float = 1.0
    current_limit_a: float = 40.0
    efficiency: float = 0.80

    # Computed — performance
    climb_time_sec: float = 0.0
    max_climb_speed_in_s: float = 0.0
    peak_current_a: float = 0.0
    holding_current_a: float = 0.0
    stall_load_lb: float = 0.0
    safety_factor: float = 0.0

    # Weight
    motor_weight_lb: float = 0.0
    mechanism_weight_lb: float = 0.0
    total_weight_lb: float = 0.0

    # Software constants
    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    preset_name: str = ""


# ═══════════════════════════════════════════════════════════════════
# CLIMB STYLES
# ═══════════════════════════════════════════════════════════════════

CLIMB_STYLES = {
    "winch": {
        "name": "Winch Climber",
        "description": "Spool + hook on telescoping tube. Most reliable.",
        "mechanism_weight_lb": 3.0,
        "complexity": "low",
    },
    "telescope": {
        "name": "Telescoping Climber",
        "description": "Motorized telescoping tube with hook. Smooth motion.",
        "mechanism_weight_lb": 5.0,
        "complexity": "medium",
    },
    "continuous": {
        "name": "Continuous Climber",
        "description": "Elevator-style continuous belt/chain climb. Fastest but heaviest.",
        "mechanism_weight_lb": 7.0,
        "complexity": "high",
    },
}


def recommend_climb_ratio(
    motor: DCMotor,
    motor_count: int,
    robot_weight_lb: float,
    spool_diameter_in: float,
    current_limit_a: float = 40.0,
    efficiency: float = 0.80,
    target_time_sec: float = 3.0,
    climb_height_in: float = 26.0,
) -> dict:
    """Sweep gear ratios to find the fastest climb that can hold the robot."""
    spool_radius_m = (spool_diameter_in / 2) * IN_TO_M
    load_force_n = robot_weight_lb * LB_TO_N

    best_ratio = 50.0
    best_time = float('inf')

    for ratio_x10 in range(200, 1001, 10):  # 20:1 to 100:1 in steps of 1
        ratio = ratio_x10 / 10.0

        # Check: can this ratio hold the robot?
        effective_current = min(current_limit_a, motor.stall_current_a)
        stall_torque = motor.kT * effective_current * motor_count * ratio * efficiency
        stall_force = stall_torque / spool_radius_m
        if stall_force < load_force_n * 1.5:  # need 1.5x safety factor
            continue

        # Simulate climb
        sim = simulate_linear_motion(
            motor, motor_count, ratio, spool_diameter_in,
            robot_weight_lb, climb_height_in,
            current_limit_a, efficiency, angle_deg=90.0, dt=0.001,
        )
        if sim.travel_time_sec < best_time:
            best_time = sim.travel_time_sec
            best_ratio = ratio

    return {
        "recommended_ratio": best_ratio,
        "estimated_time_sec": round(best_time, 3),
    }


def generate_climber(
    climb_height_in: float = 26.0,
    robot_weight_lb: float = 125.0,
    climb_style: str = "winch",
    motor_type: str = "neo",
    motor_count: int = 2,
    gear_ratio: float = 50.0,
    spool_diameter_in: float = 1.0,
    current_limit_a: float = 40.0,
    efficiency: float = 0.80,
    preset_name: str = "",
) -> ClimberSpec:
    """Generate a complete climber specification."""
    if motor_type not in MOTOR_DB:
        raise ValueError(f"Unknown motor: {motor_type}. Options: {list(MOTOR_DB.keys())}")
    if climb_style not in CLIMB_STYLES:
        raise ValueError(f"Unknown climb style: {climb_style}. Options: {list(CLIMB_STYLES.keys())}")

    dc_motor = MOTOR_DB[motor_type]
    style = CLIMB_STYLES[climb_style]

    spec = ClimberSpec(
        climb_height_in=climb_height_in, robot_weight_lb=robot_weight_lb,
        climb_style=climb_style, motor_type=motor_type, motor_count=motor_count,
        gear_ratio=gear_ratio, spool_diameter_in=spool_diameter_in,
        current_limit_a=current_limit_a, efficiency=efficiency,
        preset_name=preset_name,
    )

    spool_radius_m = (spool_diameter_in / 2) * IN_TO_M

    # Stall load (max weight the climber can hold)
    spec.stall_load_lb = dc_motor.stall_load_lb(
        gear_ratio, spool_radius_m, motor_count, current_limit_a, efficiency,
    )
    spec.safety_factor = round(spec.stall_load_lb / robot_weight_lb, 2)

    # Holding current at full robot weight
    load_torque_per_motor = (robot_weight_lb * LB_TO_N * spool_radius_m) / (gear_ratio * motor_count * efficiency)
    spec.holding_current_a = round(load_torque_per_motor / dc_motor.kT, 1)

    # Simulate climb motion
    sim = simulate_linear_motion(
        dc_motor, motor_count, gear_ratio, spool_diameter_in,
        robot_weight_lb, climb_height_in,
        current_limit_a, efficiency, angle_deg=90.0, dt=0.001,
    )
    spec.climb_time_sec = sim.travel_time_sec
    spec.max_climb_speed_in_s = round(sim.max_velocity_mps / IN_TO_M, 1)
    spec.peak_current_a = sim.peak_current_a

    # Weight
    spec.motor_weight_lb = round(dc_motor.weight_lb * motor_count + 1.0, 2)  # +1 for gearbox
    spec.mechanism_weight_lb = style["mechanism_weight_lb"]
    spec.total_weight_lb = round(spec.motor_weight_lb + spec.mechanism_weight_lb + 0.5, 2)  # +0.5 hardware

    # Software constants
    spec.software_constants = {
        "CLIMB_GEAR_RATIO": gear_ratio,
        "CLIMB_MOTOR_COUNT": motor_count,
        "SPOOL_DIAMETER_IN": spool_diameter_in,
        "CLIMB_HEIGHT_IN": climb_height_in,
        "CURRENT_LIMIT_A": current_limit_a,
        "CLIMB_SPEED": 0.8,  # default motor output (tune on robot)
        "HOLD_SPEED": 0.1,   # minimal power to maintain position
        "CLIMB_POSITION_TOLERANCE_IN": 0.5,
    }

    # Notes
    spec.notes = []
    if spec.safety_factor < 2.0:
        spec.notes.append(f"WARNING: Safety factor {spec.safety_factor}x — should be >= 2.0x. Add motors or increase ratio.")
    if spec.safety_factor >= 3.0:
        spec.notes.append(f"Safety factor {spec.safety_factor}x — excellent margin")
    if spec.climb_time_sec > 5.0:
        spec.notes.append("Climb > 5s — consider lower gear ratio or more motors")
    if spec.holding_current_a > current_limit_a * 0.8:
        spec.notes.append("Holding current near limit — risk of brownout while holding")
    if climb_style == "winch":
        spec.notes.append("Winch climber: use Dyneema rope (200+ lb rated) on 3D printed spool")

    # Parts list
    spec.parts_list = [
        {"qty": motor_count, "item": f"{dc_motor.name} motor", "notes": f"With {dc_motor.controller}"},
        {"qty": 1, "item": f"MAXPlanetary gearbox ({gear_ratio}:1)", "notes": "High reduction for climb"},
        {"qty": 1, "item": f"Winch spool ({spool_diameter_in}\" dia)", "notes": "3D printed or machined"},
    ]
    if climb_style == "winch":
        spec.parts_list.extend([
            {"qty": 1, "item": "Dyneema rope (1/8\" dia, 200+ lb)", "notes": f"{climb_height_in + 12}\" length"},
            {"qty": 1, "item": "Hook assembly", "notes": "Bent 1/4\" steel plate or tube"},
            {"qty": 1, "item": "Telescoping tube (1x1 or 1.5x1.5)", "notes": f"{climb_height_in}\" travel"},
        ])
    elif climb_style == "telescope":
        spec.parts_list.extend([
            {"qty": 2, "item": "Telescoping tube stages", "notes": f"1.5x1.5 → 1x1, {climb_height_in}\" travel"},
            {"qty": 1, "item": "Continuous rigging (belt or rope)", "notes": "Drives extension"},
            {"qty": 1, "item": "Hook assembly", "notes": "Passive or motorized"},
        ])
    elif climb_style == "continuous":
        spec.parts_list.extend([
            {"qty": 1, "item": "Climb chain/belt (#25 chain)", "notes": f"{climb_height_in * 2 + 12}\" loop"},
            {"qty": 2, "item": "Sprockets (#25, 16T + 24T)", "notes": "Top and bottom"},
            {"qty": 1, "item": "Carriage + hook", "notes": "Rides on chain loop"},
        ])
    spec.parts_list.append(
        {"qty": 1, "item": "Hardware assortment", "notes": "Bolts, shaft collars, bearings"},
    )

    return spec


def display_spec(spec: ClimberSpec):
    motor = MOTOR_DB[spec.motor_type]
    style = CLIMB_STYLES[spec.climb_style]
    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Climber" if spec.preset_name else "2950 Custom Climber"
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.6")
    print(f"{'═' * 60}")
    print(f"\n  CONFIGURATION")
    print(f"    Style:             {style['name']}")
    print(f"    Climb height:      {spec.climb_height_in}\"")
    print(f"    Robot weight:      {spec.robot_weight_lb} lb")
    print(f"    Motors:            {spec.motor_count}x {motor.name}")
    print(f"    Gear ratio:        {spec.gear_ratio}:1")
    print(f"    Spool diameter:    {spec.spool_diameter_in}\"")
    print(f"\n  PERFORMANCE (simulated with {spec.current_limit_a}A limit)")
    print(f"    Climb time:        {spec.climb_time_sec}s")
    print(f"    Max climb speed:   {spec.max_climb_speed_in_s} in/s")
    print(f"    Peak current:      {spec.peak_current_a}A per motor")
    print(f"    Holding current:   {spec.holding_current_a}A per motor")
    print(f"    Stall load:        {round(spec.stall_load_lb, 1)} lb")
    sf_status = "[OK]" if spec.safety_factor >= 2.0 else "[LOW]"
    print(f"    Safety factor:     {spec.safety_factor}x {sf_status}")
    print(f"\n  WEIGHT: {spec.total_weight_lb} lb")
    print(f"\n  SOFTWARE CONSTANTS")
    print(f"    ```java")
    for k, v in spec.software_constants.items():
        print(f"    public static final double {k} = {v};")
    print(f"    ```")
    if spec.notes:
        print(f"\n  NOTES")
        for n in spec.notes:
            print(f"    • {n}")
    print(f"\n{'═' * 60}\n")


PRESETS = {
    "deep_climb": {
        "description": "Standard deep climb (26\" travel, dual NEO)",
        "params": {
            "climb_height_in": 26.0, "robot_weight_lb": 125.0,
            "climb_style": "winch", "motor_type": "neo", "motor_count": 2,
            "gear_ratio": 50.0, "spool_diameter_in": 1.0,
        },
    },
    "shallow_climb": {
        "description": "Shallow/low climb (12\" travel, single NEO)",
        "params": {
            "climb_height_in": 12.0, "robot_weight_lb": 125.0,
            "climb_style": "winch", "motor_type": "neo", "motor_count": 1,
            "gear_ratio": 60.0, "spool_diameter_in": 1.0,
        },
    },
    "fast_climb": {
        "description": "Fast climb with Krakens (26\" travel, dual Kraken)",
        "params": {
            "climb_height_in": 26.0, "robot_weight_lb": 125.0,
            "climb_style": "winch", "motor_type": "kraken_x60", "motor_count": 2,
            "gear_ratio": 40.0, "spool_diameter_in": 1.25,
        },
    },
    "telescope_climb": {
        "description": "Telescoping climber (30\" travel, dual NEO)",
        "params": {
            "climb_height_in": 30.0, "robot_weight_lb": 125.0,
            "climb_style": "telescope", "motor_type": "neo", "motor_count": 2,
            "gear_ratio": 50.0, "spool_diameter_in": 1.0,
        },
    },
}


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 climber_generator.py generate --preset deep_climb")
        print("       python3 climber_generator.py presets")
        return
    if args[0] == "presets":
        for name, p in PRESETS.items():
            print(f"  {name:20s} {p['description']}")
        return
    if args[0] == "generate":
        preset_name = None
        i = 1
        while i < len(args):
            if args[i] == "--preset" and i + 1 < len(args):
                preset_name = args[i + 1]; i += 2
            else:
                i += 1
        if preset_name and preset_name in PRESETS:
            spec = generate_climber(**PRESETS[preset_name]["params"], preset_name=preset_name)
        else:
            spec = generate_climber()
        display_spec(spec)
        filepath = BASE_DIR / f"2950_{spec.preset_name or 'custom'}_climber_spec.json"
        with open(filepath, "w") as f:
            json.dump(asdict(spec), f, indent=2)
        print(f"Spec saved to: {filepath}")


if __name__ == "__main__":
    main()
