"""
The Blueprint — Parametric Elevator Generator (B.3)
Team 2950 — The Devastators

Generates a complete elevator specification from parameters:
  - Travel height (determines stage count and tube lengths)
  - End effector weight (determines motor count, gear ratio, spring force)
  - Motor type (Kraken X60, NEO, NEO Vortex)
  - Rigging type (continuous or cascade)
  - Tube stock (wall thickness)
  - Current limit (per motor, default 40A)
  - Efficiency (gearbox + belt, default 85%)

Output is an ElevatorSpec JSON with:
  - Tube cut list, belt lengths, hardware list
  - Motor selection + gear ratio recommendation
  - Spring force calculation
  - Motion profile simulation (current-limited, with efficiency)
  - Feedforward gain starting points derived from physics
  - Weight budget
  - Software constants ready to paste into Java

Physics model: DC motor with derived constants (R, kV, kT, b),
current limiting, and Euler-integrated motion profile.
Based on ReCalc (reca.lc) + 254 championship elevator architecture.

Usage:
  python3 elevator_generator.py generate --height 48
  python3 elevator_generator.py generate --height 72 --motor kraken --effector-weight 8
  python3 elevator_generator.py generate --preset competition --current-limit 40
  python3 elevator_generator.py presets
  python3 elevator_generator.py ratio-calc --height 48 --weight 8
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from motor_model import (
    DCMotor, MOTOR_DB, simulate_linear_motion,
    V_NOMINAL, LB_TO_N, IN_TO_M, GRAVITY_MPS2, RPM_TO_RADS,
)

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# MOTOR DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

class MotorType(str, Enum):
    KRAKEN_X60 = "kraken_x60"
    NEO = "neo"
    NEO_VORTEX = "neo_vortex"


# Legacy dict format (kept for weight budget + display) — specs now come from DCMotor
MOTORS = {
    MotorType.KRAKEN_X60: {
        "name": MOTOR_DB["kraken_x60"].name,
        "free_speed_rpm": MOTOR_DB["kraken_x60"].free_speed_rpm,
        "stall_torque_nm": MOTOR_DB["kraken_x60"].stall_torque_nm,
        "stall_current_a": MOTOR_DB["kraken_x60"].stall_current_a,
        "weight_lb": MOTOR_DB["kraken_x60"].weight_lb,
        "controller": MOTOR_DB["kraken_x60"].controller,
    },
    MotorType.NEO: {
        "name": MOTOR_DB["neo"].name,
        "free_speed_rpm": MOTOR_DB["neo"].free_speed_rpm,
        "stall_torque_nm": MOTOR_DB["neo"].stall_torque_nm,
        "stall_current_a": MOTOR_DB["neo"].stall_current_a,
        "weight_lb": MOTOR_DB["neo"].weight_lb,
        "controller": MOTOR_DB["neo"].controller,
    },
    MotorType.NEO_VORTEX: {
        "name": MOTOR_DB["neo_vortex"].name,
        "free_speed_rpm": MOTOR_DB["neo_vortex"].free_speed_rpm,
        "stall_torque_nm": MOTOR_DB["neo_vortex"].stall_torque_nm,
        "stall_current_a": MOTOR_DB["neo_vortex"].stall_current_a,
        "weight_lb": MOTOR_DB["neo_vortex"].weight_lb,
        "controller": MOTOR_DB["neo_vortex"].controller,
    },
}


# ═══════════════════════════════════════════════════════════════════
# RIGGING TYPE
# ═══════════════════════════════════════════════════════════════════

class RiggingType(str, Enum):
    CONTINUOUS = "continuous"  # All stages move simultaneously (254 standard)
    CASCADE = "cascade"       # Stages extend sequentially


RIGGING = {
    RiggingType.CONTINUOUS: {
        "name": "Continuous (2:1)",
        "speed_multiplier": 2.0,  # carriage moves at 2x stage 1 speed
        "description": "All stages move simultaneously. Faster. More complex rigging.",
        "belt_path": "anchor → up stage 1 → over idler → down to carriage",
    },
    RiggingType.CASCADE: {
        "name": "Cascade",
        "speed_multiplier": 1.0,  # stages move sequentially
        "description": "Stages extend one at a time. Simpler rigging. Slower.",
        "belt_path": "motor → stage 1 extends → stage 2 extends",
    },
}


# ═══════════════════════════════════════════════════════════════════
# COMPONENT SPECS
# ═══════════════════════════════════════════════════════════════════

BELT_SPECS = {
    "9mm_htd3": {
        "name": "9mm HTD3 Timing Belt",
        "width_mm": 9,
        "pitch_mm": 3,
        "break_strength_lb": 180,
        "weight_per_foot_lb": 0.02,
    },
    "15mm_htd3": {
        "name": "15mm HTD3 Timing Belt",
        "width_mm": 15,
        "pitch_mm": 3,
        "break_strength_lb": 320,
        "weight_per_foot_lb": 0.035,
    },
}

TUBE_WALL = {
    # 2x1 6061-T6 tube: weight = 2*(W+H)*t * 0.098 lb/in³
    # 1/16" wall: ~0.035 lb/in, 1/8" wall: ~0.067 lb/in
    0.0625: {"name": "1/16\" wall", "weight_per_in": 0.035},   # 254 standard, lightest
    0.125:  {"name": "1/8\" wall", "weight_per_in": 0.067},     # heavier, stiffer
}

PULLEY_SPECS = {
    "18t_htd3": {
        "name": "18T HTD3 Pulley",
        "teeth": 18,
        "pitch_diameter_in": (18 * 3) / (math.pi * 25.4),  # teeth * pitch / (pi * 25.4)
        "circumference_in": (18 * 3) / 25.4,  # teeth * pitch_mm / 25.4
        "weight_lb": 0.08,
    },
    "24t_htd3": {
        "name": "24T HTD3 Pulley",
        "teeth": 24,
        "pitch_diameter_in": (24 * 3) / (math.pi * 25.4),
        "circumference_in": (24 * 3) / 25.4,
        "weight_lb": 0.12,
    },
}


# ═══════════════════════════════════════════════════════════════════
# ELEVATOR SPEC
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ElevatorSpec:
    """Complete parametric elevator specification."""
    # Metadata
    name: str = "2950 Elevator"
    version: str = "1.0"
    generator: str = "The Blueprint B.3"

    # Configuration inputs
    travel_height_in: float = 48.0
    end_effector_weight_lb: float = 8.0
    motor_type: str = "kraken_x60"
    motor_count: int = 2
    rigging_type: str = "continuous"
    tube_wall_in: float = 0.0625

    # Computed — stages
    stage_count: int = 2
    tube_length_in: float = 0.0  # length of each stage tube
    bearing_block_height_in: float = 4.0  # lost travel at bearing blocks

    # Computed — drive system
    gear_ratio: float = 7.0
    belt_type: str = "9mm_htd3"
    belt_length_in: float = 0.0
    pulley_type: str = "18t_htd3"
    pulley_circumference_in: float = 0.0

    # Simulation parameters
    current_limit_a: float = 40.0
    efficiency: float = 0.85

    # Computed — performance (from motion profile simulation)
    max_speed_in_per_sec: float = 0.0
    full_travel_time_sec: float = 0.0
    max_acceleration_in_per_sec2: float = 0.0
    peak_current_a: float = 0.0
    stall_load_lb: float = 0.0

    # Computed — springs
    spring_force_lb: float = 0.0
    spring_type: str = ""

    # Computed — weight
    tube_weight_lb: float = 0.0
    bearing_block_weight_lb: float = 0.0
    belt_pulley_weight_lb: float = 0.0
    motor_gearbox_weight_lb: float = 0.0
    spring_weight_lb: float = 0.0
    carriage_weight_lb: float = 0.0
    hardware_weight_lb: float = 0.5
    total_weight_lb: float = 0.0

    # Software constants
    software_constants: dict = field(default_factory=dict)

    # Parts list
    parts_list: list = field(default_factory=list)

    # Validation
    travel_time_ok: bool = True  # < 0.5s
    weight_ok: bool = True       # < 15 lb (without end effector)


# ═══════════════════════════════════════════════════════════════════
# GEAR RATIO CALCULATOR
# ═══════════════════════════════════════════════════════════════════

def recommend_gear_ratio(
    end_effector_weight_lb: float,
    motor_type: str = "kraken_x60",
    motor_count: int = 2,
    travel_height_in: float = 48.0,
    target_travel_time_sec: float = 0.5,
    current_limit_a: float = 40.0,
    efficiency: float = 0.85,
    rigging_type: str = "continuous",
) -> dict:
    """
    Recommend a gear ratio using DC motor physics + motion profile simulation.

    Uses the proper motor model (R, kV, kT from datasheet) with current limiting
    and efficiency losses. Simulates the actual motion profile to find travel time
    rather than using peak-speed estimates.

    Returns recommended ratio, simulated travel time, and performance data.
    """
    dc_motor = MOTOR_DB[motor_type]
    pulley = PULLEY_SPECS["18t_htd3"]
    rigging = RIGGING[RiggingType(rigging_type)]
    rigging_multiplier = rigging["speed_multiplier"]

    # Total carriage weight (end effector + carriage plate + stage 2 tubes + bearings)
    carriage_weight_lb = end_effector_weight_lb + 3.5

    # Effective spool diameter: pulley circumference accounts for belt pitch
    # For continuous rigging, the effective spool diameter is multiplied by rigging ratio
    spool_diameter_in = pulley["circumference_in"] / math.pi * rigging_multiplier

    # Sweep ratios from 3:1 to 15:1 and simulate each to find best
    best_ratio = 5.0
    best_time = float('inf')
    best_result = None

    for ratio_x10 in range(30, 151, 5):  # 3.0 to 15.0 in 0.5 steps
        ratio = ratio_x10 / 10.0
        result = simulate_linear_motion(
            motor=dc_motor,
            motor_count=motor_count,
            gear_ratio=ratio,
            spool_diameter_in=spool_diameter_in,
            load_lb=carriage_weight_lb,
            travel_distance_in=travel_height_in,
            current_limit_a=current_limit_a,
            efficiency=efficiency,
            angle_deg=90.0,
            dt=0.002,  # coarser dt for sweep
        )
        if result.travel_time_sec < best_time:
            best_time = result.travel_time_sec
            best_ratio = ratio
            best_result = result

    # Re-simulate at best ratio with finer dt
    result = simulate_linear_motion(
        motor=dc_motor,
        motor_count=motor_count,
        gear_ratio=best_ratio,
        spool_diameter_in=spool_diameter_in,
        load_lb=carriage_weight_lb,
        travel_distance_in=travel_height_in,
        current_limit_a=current_limit_a,
        efficiency=efficiency,
        angle_deg=90.0,
        dt=0.001,
    )

    # Holding current from DC motor model
    pulley_radius_m = (spool_diameter_in / 2) * IN_TO_M
    weight_n = carriage_weight_lb * LB_TO_N
    torque_per_motor = weight_n * pulley_radius_m / (best_ratio * motor_count)
    holding_current = torque_per_motor / dc_motor.kT
    torque_margin = dc_motor.stall_torque_nm / torque_per_motor if torque_per_motor > 0 else float('inf')

    return {
        "recommended_ratio": best_ratio,
        "actual_speed_in_per_sec": round(result.max_velocity_mps / IN_TO_M, 1),
        "travel_time_sec": round(result.travel_time_sec, 3),
        "max_acceleration_in_per_sec2": round(result.max_acceleration_mps2 / IN_TO_M, 1),
        "peak_current_a": result.peak_current_a,
        "stall_load_lb": result.stall_load_lb,
        "torque_margin": round(torque_margin, 1),
        "holding_current_per_motor_a": round(holding_current, 1),
        "notes": _ratio_notes(best_ratio, result.travel_time_sec, torque_margin),
    }


def _ratio_notes(ratio: float, travel_time: float, torque_margin: float) -> str:
    notes = []
    if travel_time > 0.8:
        notes.append("WARNING: Travel time > 0.8s — consider lower ratio or more motors")
    elif travel_time > 0.5:
        notes.append("Travel time above 0.5s target but acceptable")
    else:
        notes.append("Travel time meets 254's <0.5s benchmark")

    if torque_margin < 3:
        notes.append("WARNING: Low torque margin — springs are critical")
    elif torque_margin < 5:
        notes.append("Adequate torque margin with springs")
    else:
        notes.append("Strong torque margin")

    return "; ".join(notes)


# ═══════════════════════════════════════════════════════════════════
# ELEVATOR GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_elevator(
    travel_height_in: float = 48.0,
    end_effector_weight_lb: float = 8.0,
    motor_type: str = "kraken_x60",
    motor_count: int = 2,
    rigging_type: str = "continuous",
    tube_wall_in: float = 0.0625,
    current_limit_a: float = 40.0,
    efficiency: float = 0.85,
    name: str = "2950 Elevator",
) -> ElevatorSpec:
    """Generate a complete parametric elevator specification."""
    spec = ElevatorSpec(name=name)
    spec.travel_height_in = travel_height_in
    spec.end_effector_weight_lb = end_effector_weight_lb
    spec.motor_type = motor_type
    spec.motor_count = motor_count
    spec.rigging_type = rigging_type
    spec.tube_wall_in = tube_wall_in
    spec.current_limit_a = current_limit_a
    spec.efficiency = efficiency

    motor = MOTORS[MotorType(motor_type)]
    rigging = RIGGING[RiggingType(rigging_type)]
    pulley = PULLEY_SPECS["18t_htd3"]

    # ── Stage count (from R5) ──
    if travel_height_in <= 24:
        spec.stage_count = 1
    elif travel_height_in <= 55:
        spec.stage_count = 2
    else:
        spec.stage_count = 3  # rare, complex

    # ── Tube lengths ──
    spec.bearing_block_height_in = 4.0
    spec.tube_length_in = round(travel_height_in / spec.stage_count + spec.bearing_block_height_in, 2)

    # ── Gear ratio (from motion profile simulation) ──
    ratio_calc = recommend_gear_ratio(
        end_effector_weight_lb, motor_type, motor_count, travel_height_in,
        current_limit_a=current_limit_a, efficiency=efficiency, rigging_type=rigging_type,
    )
    spec.gear_ratio = ratio_calc["recommended_ratio"]

    # ── Belt ──
    spec.belt_type = "9mm_htd3" if end_effector_weight_lb < 12 else "15mm_htd3"
    belt = BELT_SPECS[spec.belt_type]
    spec.pulley_type = "18t_htd3"
    spec.pulley_circumference_in = pulley["circumference_in"]

    # Belt length: approximate — 2x tube length + pulley wrap + slack
    spec.belt_length_in = round(2 * spec.tube_length_in * spec.stage_count + 12, 1)

    # ── Performance (from current-limited motion profile simulation) ──
    spec.max_speed_in_per_sec = ratio_calc["actual_speed_in_per_sec"]
    spec.full_travel_time_sec = ratio_calc["travel_time_sec"]
    spec.max_acceleration_in_per_sec2 = ratio_calc.get("max_acceleration_in_per_sec2", 0)
    spec.peak_current_a = ratio_calc.get("peak_current_a", 0)
    spec.stall_load_lb = ratio_calc.get("stall_load_lb", 0)
    spec.travel_time_ok = spec.full_travel_time_sec <= 0.5

    # ── Spring force ──
    # Springs should offset: stage 2 tubes + bearing blocks + carriage + end effector
    stage2_tube_weight = 2 * spec.tube_length_in * TUBE_WALL[tube_wall_in]["weight_per_in"]  # 2x1 tube
    carriage_assembly_weight = 0.8 + end_effector_weight_lb  # carriage plate + end effector
    bearing_block_weight = 0.4 * spec.stage_count  # ~0.4 lb per stage of blocks
    total_gravity_load = stage2_tube_weight + carriage_assembly_weight + bearing_block_weight
    spec.spring_force_lb = round(total_gravity_load, 1)

    # Spring selection
    if spec.spring_force_lb < 5:
        spec.spring_type = "WCP 5 lb constant force spring"
    elif spec.spring_force_lb < 8:
        spec.spring_type = "WCP 8 lb constant force spring"
    elif spec.spring_force_lb < 12:
        spec.spring_type = "WCP 12 lb constant force spring"
    else:
        spec.spring_type = "WCP 15 lb constant force spring (or dual 8 lb)"

    # ── Weight budget ──
    # Tubes: 4 tubes (2 per rail) for 2-stage, 6 for 3-stage
    tubes_per_stage = 2  # left rail + right rail
    total_tubes = tubes_per_stage * (spec.stage_count + 1)  # +1 for fixed stage
    tube_weight_per_inch = TUBE_WALL[tube_wall_in]["weight_per_in"]
    spec.tube_weight_lb = round(total_tubes * spec.tube_length_in * tube_weight_per_inch, 2)

    spec.bearing_block_weight_lb = round(0.4 * spec.stage_count * 2, 2)  # 2 sets per stage (top + bottom)

    belt_length_ft = spec.belt_length_in / 12
    spec.belt_pulley_weight_lb = round(
        belt_length_ft * belt["weight_per_foot_lb"] +
        4 * pulley["weight_lb"],  # drive + 3 idlers
        2
    )

    spec.motor_gearbox_weight_lb = round(
        motor_count * motor["weight_lb"] + 1.0,  # +1 lb for gearbox housing/plate
        2
    )

    spec.spring_weight_lb = round(0.3 * spec.stage_count, 2)  # ~0.3 lb per spring
    spec.carriage_weight_lb = 0.8

    spec.total_weight_lb = round(
        spec.tube_weight_lb +
        spec.bearing_block_weight_lb +
        spec.belt_pulley_weight_lb +
        spec.motor_gearbox_weight_lb +
        spec.spring_weight_lb +
        spec.carriage_weight_lb +
        spec.hardware_weight_lb,
        2
    )
    spec.weight_ok = spec.total_weight_lb <= 15.0

    # ── Software constants (feedforward gains derived from physics) ──
    dc_motor = MOTOR_DB[motor_type]
    spool_radius_m = (pulley["circumference_in"] * rigging["speed_multiplier"] / math.pi / 2) * IN_TO_M
    # kG: voltage to hold against gravity = (m·g·r) / (kT·G·N·η) · R
    gravity_force_n = total_gravity_load * LB_TO_N
    kg_voltage = (gravity_force_n * spool_radius_m) / (dc_motor.kT * spec.gear_ratio * motor_count * efficiency) * dc_motor.R
    # kV: voltage per unit velocity = 1 / (kV · r · G) in V·s/in
    kv_volts_per_in_s = 1.0 / (dc_motor.kV * spool_radius_m * spec.gear_ratio / IN_TO_M)

    spec.software_constants = {
        "GEAR_RATIO": spec.gear_ratio,
        "MOTOR_COUNT": motor_count,
        "CURRENT_LIMIT_A": current_limit_a,
        "EFFICIENCY": efficiency,
        "PULLEY_CIRCUMFERENCE_IN": round(pulley["circumference_in"], 4),
        "CONTINUOUS_RATIO": rigging["speed_multiplier"],
        "INCHES_PER_MOTOR_ROTATION": round(
            pulley["circumference_in"] * rigging["speed_multiplier"] / spec.gear_ratio, 4
        ),
        "MIN_HEIGHT_IN": 0.0,
        "MAX_HEIGHT_IN": travel_height_in,
        "MAX_VELOCITY_IN_PER_SEC": round(spec.max_speed_in_per_sec * 0.9, 1),
        "MAX_ACCELERATION_IN_PER_SEC2": round(spec.max_acceleration_in_per_sec2 * 0.8, 1),
        "kS": 0.12,  # static friction — tune on hardware
        "kG": round(kg_voltage, 3),  # gravity feedforward (V) — from motor model
        "kV": round(kv_volts_per_in_s, 5),  # velocity feedforward (V·s/in) — from motor model
        "kA": 0.02,  # acceleration feedforward — tune on hardware
        "POSITION_TOLERANCE_IN": 0.5,
    }

    # ── Parts list ──
    spec.parts_list = [
        {"item": f"2x1x{tube_wall_in}\" 6061-T6 aluminum tube",
         "quantity": total_tubes, "length_in": spec.tube_length_in,
         "notes": "Cut to length, deburr all edges"},
        {"item": f"Thrifty Elevator bearing block set",
         "quantity": spec.stage_count * 2, "notes": "2 per stage (top + bottom)"},
        {"item": belt["name"], "quantity": 1,
         "length_in": spec.belt_length_in, "notes": "Order nearest standard length"},
        {"item": f"18T HTD3 drive pulley (1/2\" hex bore)",
         "quantity": 1, "notes": "Drive pulley on motor shaft"},
        {"item": "HTD3 idler pulley (flanged bearing)",
         "quantity": 3, "notes": "Direction changes in belt path"},
        {"item": f"{motor['name']} motor",
         "quantity": motor_count, "notes": f"With {motor['controller']}"},
        {"item": "Gearbox (single stage planetary)",
         "quantity": 1, "notes": f"{spec.gear_ratio}:1 ratio"},
        {"item": spec.spring_type,
         "quantity": 2, "notes": f"Target force: {spec.spring_force_lb} lb total"},
        {"item": "Hall effect sensor + magnet",
         "quantity": 1, "notes": "Bottom of travel zero reference"},
        {"item": "1/2\" hex shaft, 12\"",
         "quantity": 1, "notes": "Drive shaft"},
        {"item": "1/4\" aluminum carriage plate",
         "quantity": 1, "notes": "Drill for end effector on kickoff day"},
        {"item": "#10-32 hardware assortment",
         "quantity": 50, "notes": "Bolts, nuts, washers"},
    ]

    return spec


# ═══════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════

PRESETS = {
    "low": {
        "description": "Single-stage, low scoring (< 24\" travel)",
        "travel_height_in": 20.0,
        "end_effector_weight_lb": 5.0,
        "motor_type": "neo",
        "motor_count": 1,
        "rigging_type": "continuous",
    },
    "mid": {
        "description": "Two-stage, medium scoring (36\" travel)",
        "travel_height_in": 36.0,
        "end_effector_weight_lb": 8.0,
        "motor_type": "neo",
        "motor_count": 2,
        "rigging_type": "continuous",
    },
    "competition": {
        "description": "Two-stage, 254-style (48\" travel, Krakens)",
        "travel_height_in": 48.0,
        "end_effector_weight_lb": 8.0,
        "motor_type": "kraken_x60",
        "motor_count": 2,
        "rigging_type": "continuous",
    },
    "tall": {
        "description": "Two-stage, max reach (55\" travel)",
        "travel_height_in": 55.0,
        "end_effector_weight_lb": 10.0,
        "motor_type": "kraken_x60",
        "motor_count": 2,
        "rigging_type": "continuous",
    },
    "cascade": {
        "description": "Cascade rigging, simpler but slower",
        "travel_height_in": 48.0,
        "end_effector_weight_lb": 8.0,
        "motor_type": "neo",
        "motor_count": 2,
        "rigging_type": "cascade",
    },
}


# ═══════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════

def print_summary(spec: ElevatorSpec):
    motor = MOTORS[MotorType(spec.motor_type)]
    rigging = RIGGING[RiggingType(spec.rigging_type)]

    print(f"\n{'═' * 60}")
    print(f"  {spec.name}")
    print(f"  Generated by {spec.generator}")
    print(f"{'═' * 60}")

    print(f"\n  CONFIGURATION")
    print(f"    Travel height:     {spec.travel_height_in}\"")
    print(f"    Stages:            {spec.stage_count} ({rigging['name']})")
    print(f"    Tube length:       {spec.tube_length_in}\" per stage")
    print(f"    Tube wall:         {spec.tube_wall_in}\" ({TUBE_WALL[spec.tube_wall_in]['name']})")
    print(f"    End effector:      {spec.end_effector_weight_lb} lb")

    print(f"\n  DRIVE SYSTEM")
    print(f"    Motors:            {spec.motor_count}x {motor['name']}")
    print(f"    Controller:        {motor['controller']}")
    print(f"    Gear ratio:        {spec.gear_ratio}:1")
    print(f"    Belt:              {BELT_SPECS[spec.belt_type]['name']} ({spec.belt_length_in}\")")
    print(f"    Drive pulley:      {PULLEY_SPECS[spec.pulley_type]['name']}")

    print(f"\n  PERFORMANCE (simulated with {spec.current_limit_a}A limit, {int(spec.efficiency*100)}% efficiency)")
    status = "PASS" if spec.travel_time_ok else "SLOW"
    print(f"    Max speed:         {spec.max_speed_in_per_sec} in/s")
    print(f"    Max acceleration:  {spec.max_acceleration_in_per_sec2} in/s²")
    print(f"    Full travel time:  {spec.full_travel_time_sec}s [{status}] (target: < 0.5s)")
    print(f"    Peak current:      {spec.peak_current_a}A per motor")
    print(f"    Stall load:        {spec.stall_load_lb} lb (at {spec.current_limit_a}A limit)")

    print(f"\n  SPRING ASSIST")
    print(f"    Gravity load:      {spec.spring_force_lb} lb")
    print(f"    Springs:           2x {spec.spring_type}")

    print(f"\n  WEIGHT BUDGET")
    print(f"    Tubes:             {spec.tube_weight_lb} lb")
    print(f"    Bearing blocks:    {spec.bearing_block_weight_lb} lb")
    print(f"    Belt + pulleys:    {spec.belt_pulley_weight_lb} lb")
    print(f"    Motors + gearbox:  {spec.motor_gearbox_weight_lb} lb")
    print(f"    Springs:           {spec.spring_weight_lb} lb")
    print(f"    Carriage plate:    {spec.carriage_weight_lb} lb")
    print(f"    Hardware:          {spec.hardware_weight_lb} lb")
    print(f"    ─────────────────────────")
    weight_status = "PASS" if spec.weight_ok else "HEAVY"
    print(f"    ELEVATOR TOTAL:    {spec.total_weight_lb} lb [{weight_status}] (target: < 15 lb)")
    print(f"    With end effector: {round(spec.total_weight_lb + spec.end_effector_weight_lb, 2)} lb")
    print(f"    254 target:        < 20 lb (elevator + end effector)")

    print(f"\n  SOFTWARE CONSTANTS (paste into Java)")
    print(f"    ```java")
    for key, val in spec.software_constants.items():
        print(f"    public static final double {key} = {val};")
    print(f"    ```")

    print(f"\n  PARTS LIST")
    for part in spec.parts_list:
        qty = part["quantity"]
        item = part["item"]
        length = f" @ {part['length_in']}\"" if "length_in" in part else ""
        notes = f" — {part['notes']}" if part.get("notes") else ""
        print(f"    {qty}x  {item}{length}{notes}")

    print(f"\n{'═' * 60}\n")


def save_spec(spec: ElevatorSpec, output_path: Optional[str] = None) -> str:
    if output_path is None:
        safe_name = spec.name.lower().replace(" ", "_")
        output_path = str(BASE_DIR / f"{safe_name}_spec.json")
    with open(output_path, "w") as f:
        json.dump(asdict(spec), f, indent=2)
    return output_path


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("The Blueprint — Elevator Generator (B.3)")
        print()
        print("Usage:")
        print("  python3 elevator_generator.py generate --height 48")
        print("  python3 elevator_generator.py generate --height 72 --motor kraken_x60 --effector-weight 8")
        print("  python3 elevator_generator.py generate --preset competition")
        print("  python3 elevator_generator.py presets")
        print("  python3 elevator_generator.py ratio-calc --height 48 --weight 8")
        print()
        print("Presets:", ", ".join(PRESETS.keys()))
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "presets":
        print("\nAvailable presets:")
        for name, preset in PRESETS.items():
            print(f"  {name:<14} {preset['description']}")
        print()

    elif cmd == "generate":
        args = sys.argv[2:]
        if "--preset" in args:
            idx = args.index("--preset")
            preset_name = args[idx + 1]
            if preset_name not in PRESETS:
                print(f"Unknown preset: {preset_name}")
                sys.exit(1)
            params = {k: v for k, v in PRESETS[preset_name].items() if k != "description"}
            params["name"] = f"2950 {preset_name.title()} Elevator"
            spec = generate_elevator(**params)
        else:
            params = {}
            for i in range(0, len(args) - 1, 2):
                key = args[i].lstrip("-")
                val = args[i + 1]
                if key in ("height", "travel_height_in"):
                    params["travel_height_in"] = float(val)
                elif key in ("weight", "effector-weight", "end_effector_weight_lb"):
                    params["end_effector_weight_lb"] = float(val)
                elif key in ("motor", "motor_type"):
                    params["motor_type"] = val
                elif key in ("motors", "motor_count"):
                    params["motor_count"] = int(val)
                elif key in ("rigging", "rigging_type"):
                    params["rigging_type"] = val
                elif key in ("wall", "tube_wall_in"):
                    params["tube_wall_in"] = float(val)
                elif key in ("current-limit", "current_limit_a"):
                    params["current_limit_a"] = float(val)
                elif key in ("efficiency",):
                    params["efficiency"] = float(val)
            spec = generate_elevator(**params)

        print_summary(spec)
        path = save_spec(spec)
        print(f"Spec saved to: {path}")

    elif cmd == "ratio-calc":
        args = sys.argv[2:]
        height = 48.0
        weight = 8.0
        motor = "kraken_x60"
        motors = 2
        for i in range(0, len(args) - 1, 2):
            key = args[i].lstrip("-")
            val = args[i + 1]
            if key == "height":
                height = float(val)
            elif key == "weight":
                weight = float(val)
            elif key == "motor":
                motor = val
            elif key == "motors":
                motors = int(val)

        result = recommend_gear_ratio(weight, motor, motors, height)
        print(f"\nGear Ratio Calculator")
        print(f"  Travel: {height}\" | Load: {weight} lb | Motor: {motor} x{motors}")
        print(f"  Recommended ratio: {result['recommended_ratio']}:1")
        print(f"  Carriage speed: {result['actual_speed_in_per_sec']} in/s")
        print(f"  Full travel time: {result['travel_time_sec']}s")
        print(f"  Torque margin: {result['torque_margin']}x")
        print(f"  Holding current/motor: {result['holding_current_per_motor_a']}A (without springs)")
        print(f"  Notes: {result['notes']}")
        print()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
