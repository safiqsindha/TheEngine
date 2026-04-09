"""
The Blueprint — Parametric Arm Generator (B.5)
Team 2950 — The Devastators

Generates a pivot arm specification from parameters:
  - Arm length (pivot to end effector)
  - Load at end effector
  - Angular range
  - Motor type + gear ratio
  - Counterbalance spring

Physics: DC motor torque vs gravity torque at angle,
Euler-integrated motion profile.
Based on ReCalc arm calculator.

Usage:
  python3 arm_generator.py generate --preset scoring_arm
  python3 arm_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from motor_model import DCMotor, MOTOR_DB, V_NOMINAL, LB_TO_N, IN_TO_M, GRAVITY_MPS2, RPM_TO_RADS

BASE_DIR = Path(__file__).parent


@dataclass
class ArmSpec:
    """Complete parametric arm specification."""
    # Inputs
    arm_length_in: float = 24.0
    com_distance_in: float = 12.0  # pivot to center of mass
    arm_mass_lb: float = 5.0
    end_effector_weight_lb: float = 3.0
    motor_type: str = "neo"
    motor_count: int = 1
    gear_ratio: float = 100.0
    current_limit_a: float = 40.0
    efficiency: float = 0.85
    start_angle_deg: float = -30.0  # below horizontal
    end_angle_deg: float = 110.0    # above horizontal

    # Computed
    total_mass_lb: float = 0.0
    max_gravity_torque_nm: float = 0.0
    travel_time_sec: float = 0.0
    max_angular_velocity_deg_s: float = 0.0
    holding_current_a: float = 0.0
    peak_current_a: float = 0.0
    spring_force_lb: float = 0.0

    # Weight
    motor_weight_lb: float = 0.0
    total_weight_lb: float = 0.0

    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    preset_name: str = ""


def simulate_arm_motion(
    motor: DCMotor,
    motor_count: int,
    gear_ratio: float,
    com_distance_in: float,
    total_mass_lb: float,
    start_angle_deg: float,
    end_angle_deg: float,
    current_limit_a: float = 40.0,
    efficiency: float = 0.85,
    dt: float = 0.0005,
) -> dict:
    """Simulate arm motion from start_angle to end_angle using Euler integration."""
    com_m = com_distance_in * IN_TO_M
    mass_kg = total_mass_lb * LB_TO_N / GRAVITY_MPS2
    j_arm = mass_kg * com_m**2  # point mass approximation

    theta = math.radians(start_angle_deg)
    target_theta = math.radians(end_angle_deg)
    omega = 0.0  # arm angular velocity (rad/s)
    t = 0.0

    direction = 1.0 if end_angle_deg > start_angle_deg else -1.0
    max_omega = 0.0
    peak_current = 0.0

    max_steps = int(5.0 / dt)
    for _ in range(max_steps):
        # Gravity torque at arm output: τ = L_com · m · g · cos(θ)
        gravity_torque = com_m * mass_kg * GRAVITY_MPS2 * math.cos(theta)

        # Motor state: compute current at motor speed
        motor_rpm = abs(omega) * gear_ratio / RPM_TO_RADS
        motor_omega = abs(omega) * gear_ratio
        current = motor.current_at_speed(motor_omega)
        effective_current = min(max(current, 0), current_limit_a)
        if effective_current > peak_current:
            peak_current = effective_current

        # Motor torque at output
        motor_torque = motor.kT * effective_current * motor_count * gear_ratio * efficiency * direction

        # Net torque
        net_torque = motor_torque - gravity_torque

        # Angular acceleration
        alpha = net_torque / j_arm if j_arm > 0 else 0

        # Euler integration
        omega += alpha * dt
        theta += omega * dt
        t += dt

        if abs(omega) > max_omega:
            max_omega = abs(omega)

        # Check completion
        if direction > 0 and theta >= target_theta:
            break
        if direction < 0 and theta <= target_theta:
            break

    return {
        "travel_time_sec": round(t, 3),
        "max_angular_velocity_deg_s": round(max_omega * 180 / math.pi, 1),
        "peak_current_a": round(peak_current, 1),
    }


def generate_arm(
    arm_length_in: float = 24.0,
    com_distance_in: float = 12.0,
    arm_mass_lb: float = 5.0,
    end_effector_weight_lb: float = 3.0,
    motor_type: str = "neo",
    motor_count: int = 1,
    gear_ratio: float = 100.0,
    current_limit_a: float = 40.0,
    efficiency: float = 0.85,
    start_angle_deg: float = -30.0,
    end_angle_deg: float = 110.0,
    preset_name: str = "",
) -> ArmSpec:
    """Generate a complete arm specification."""
    if motor_type not in MOTOR_DB:
        raise ValueError(f"Unknown motor: {motor_type}. Options: {list(MOTOR_DB.keys())}")

    dc_motor = MOTOR_DB[motor_type]
    spec = ArmSpec(
        arm_length_in=arm_length_in, com_distance_in=com_distance_in,
        arm_mass_lb=arm_mass_lb, end_effector_weight_lb=end_effector_weight_lb,
        motor_type=motor_type, motor_count=motor_count, gear_ratio=gear_ratio,
        current_limit_a=current_limit_a, efficiency=efficiency,
        start_angle_deg=start_angle_deg, end_angle_deg=end_angle_deg,
        preset_name=preset_name,
    )

    spec.total_mass_lb = arm_mass_lb + end_effector_weight_lb
    total_mass_kg = spec.total_mass_lb * LB_TO_N / GRAVITY_MPS2
    com_m = com_distance_in * IN_TO_M

    # Max gravity torque (at horizontal)
    spec.max_gravity_torque_nm = round(total_mass_kg * GRAVITY_MPS2 * com_m, 2)

    # Holding current at worst case (horizontal)
    holding_torque_per_motor = spec.max_gravity_torque_nm / (gear_ratio * motor_count * efficiency)
    spec.holding_current_a = round(holding_torque_per_motor / dc_motor.kT, 1)

    # Counterbalance spring recommendation
    spec.spring_force_lb = round(spec.total_mass_lb * (com_distance_in / arm_length_in), 1)

    # Simulate motion
    sim = simulate_arm_motion(
        dc_motor, motor_count, gear_ratio, com_distance_in, spec.total_mass_lb,
        start_angle_deg, end_angle_deg, current_limit_a, efficiency,
    )
    spec.travel_time_sec = sim["travel_time_sec"]
    spec.max_angular_velocity_deg_s = sim["max_angular_velocity_deg_s"]
    spec.peak_current_a = sim["peak_current_a"]

    # Weight
    spec.motor_weight_lb = round(dc_motor.weight_lb * motor_count + 1.0, 2)  # +1 for gearbox
    spec.total_weight_lb = round(spec.arm_mass_lb + spec.motor_weight_lb + 0.5, 2)  # +0.5 hardware

    # Software constants
    angular_range = abs(end_angle_deg - start_angle_deg)
    spec.software_constants = {
        "ARM_GEAR_RATIO": gear_ratio,
        "ARM_LENGTH_IN": arm_length_in,
        "MIN_ANGLE_DEG": start_angle_deg,
        "MAX_ANGLE_DEG": end_angle_deg,
        "CURRENT_LIMIT_A": current_limit_a,
        "kS": 0.1,
        "kG": round(spec.max_gravity_torque_nm / (dc_motor.kT * gear_ratio * motor_count) * dc_motor.R, 3),
        "kV": round(V_NOMINAL / (dc_motor.free_speed_rads / gear_ratio * 180 / math.pi), 5),
        "kA": 0.01,
        "POSITION_TOLERANCE_DEG": 2.0,
    }

    # Parts
    spec.parts_list = [
        {"qty": motor_count, "item": f"{dc_motor.name} motor", "notes": f"With {dc_motor.controller}"},
        {"qty": 1, "item": f"MAXPlanetary gearbox ({gear_ratio}:1)", "notes": "High reduction for arm control"},
        {"qty": 1, "item": "Arm tube (1x1 or 2x1 aluminum)", "notes": f"{arm_length_in}\" long"},
        {"qty": 2, "item": "Pivot bearing + shaft", "notes": "1/2\" hex through pivot point"},
        {"qty": 1, "item": "Absolute encoder (through-bore)", "notes": "REV Through Bore or equivalent"},
        {"qty": 1, "item": "Hardware assortment", "notes": "Bolts, spacers, shaft collar"},
    ]
    if spec.spring_force_lb > 2:
        spec.parts_list.append(
            {"qty": 1, "item": f"Counterbalance spring ({spec.spring_force_lb} lb)",
             "notes": "Constant force spring to offset gravity"}
        )

    spec.notes = []
    if spec.holding_current_a > current_limit_a * 0.5:
        spec.notes.append("High holding current — counterbalance spring strongly recommended")
    if spec.travel_time_sec > 1.0:
        spec.notes.append("Arm travel > 1s — consider higher gear ratio or more motors")
    if angular_range > 180:
        spec.notes.append("Large angular range — verify no mechanical interference")

    return spec


PRESETS = {
    "scoring_arm": {
        "description": "Medium arm for scoring at 2 heights (24\" reach)",
        "params": {
            "arm_length_in": 24.0, "com_distance_in": 12.0,
            "arm_mass_lb": 5.0, "end_effector_weight_lb": 3.0,
            "motor_type": "neo", "motor_count": 1, "gear_ratio": 100.0,
            "start_angle_deg": -30.0, "end_angle_deg": 110.0,
        },
    },
    "wrist": {
        "description": "Short wrist joint for end effector angle (8\" reach)",
        "params": {
            "arm_length_in": 8.0, "com_distance_in": 4.0,
            "arm_mass_lb": 1.5, "end_effector_weight_lb": 2.0,
            "motor_type": "neo_550", "motor_count": 1, "gear_ratio": 50.0,
            "start_angle_deg": -45.0, "end_angle_deg": 90.0,
        },
    },
    "long_arm": {
        "description": "Long arm for high scoring (36\" reach, dual motor)",
        "params": {
            "arm_length_in": 36.0, "com_distance_in": 18.0,
            "arm_mass_lb": 8.0, "end_effector_weight_lb": 5.0,
            "motor_type": "neo", "motor_count": 2, "gear_ratio": 150.0,
            "start_angle_deg": -20.0, "end_angle_deg": 120.0,
        },
    },
}


def display_spec(spec: ArmSpec):
    motor = MOTOR_DB[spec.motor_type]
    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Arm" if spec.preset_name else "2950 Custom Arm"
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.5")
    print(f"{'═' * 60}")
    print(f"\n  CONFIGURATION")
    print(f"    Length:            {spec.arm_length_in}\" (CoM at {spec.com_distance_in}\")")
    print(f"    Mass:              {spec.arm_mass_lb} lb arm + {spec.end_effector_weight_lb} lb end effector")
    print(f"    Motors:            {spec.motor_count}x {motor.name}")
    print(f"    Gear ratio:        {spec.gear_ratio}:1")
    print(f"    Range:             {spec.start_angle_deg}° to {spec.end_angle_deg}°")
    print(f"\n  PERFORMANCE (simulated with {spec.current_limit_a}A limit)")
    print(f"    Travel time:       {spec.travel_time_sec}s")
    print(f"    Max angular vel:   {spec.max_angular_velocity_deg_s}°/s")
    print(f"    Peak current:      {spec.peak_current_a}A")
    print(f"    Holding current:   {spec.holding_current_a}A (at horizontal)")
    print(f"    Max gravity torque: {spec.max_gravity_torque_nm} N·m")
    print(f"    Spring recommend:  {spec.spring_force_lb} lb constant force")
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


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 arm_generator.py generate --preset scoring_arm")
        print("       python3 arm_generator.py presets")
        return
    if args[0] == "presets":
        for name, p in PRESETS.items():
            print(f"  {name:20s} {p['description']}")
        return
    if args[0] == "generate":
        preset_name = None
        params = {}
        i = 1
        while i < len(args):
            if args[i] == "--preset" and i+1 < len(args):
                preset_name = args[i+1]; i += 2
            else:
                i += 1
        if preset_name and preset_name in PRESETS:
            spec = generate_arm(**PRESETS[preset_name]["params"], preset_name=preset_name)
        else:
            spec = generate_arm(**params)
        display_spec(spec)
        filepath = BASE_DIR / f"2950_{spec.preset_name or 'custom'}_arm_spec.json"
        with open(filepath, "w") as f:
            json.dump(asdict(spec), f, indent=2)
        print(f"Spec saved to: {filepath}")


if __name__ == "__main__":
    main()
