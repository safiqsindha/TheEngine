"""
The Blueprint — Parametric Intake Generator (B.3)
Team 2950 — The Devastators

Generates a complete intake specification from parameters:
  - Intake type (over-bumper, under-bumper, fixed full-width)
  - Game piece geometry (diameter, shape)
  - Robot frame width (determines intake width)
  - Roller configuration (material, count, spacing)
  - Deploy mechanism (pivot, linear, none)

Output is an IntakeSpec JSON with:
  - Roller layout, spacing, and compression
  - Motor selection + gear ratio
  - Deployment mechanism spec
  - Weight budget
  - Software constants ready to paste into Java
  - Parts list

Based on: CROSS_SEASON_PATTERNS.md Rules R2 (full-width intake), R3 (roller material),
254/1678 championship intake architectures.

Usage:
  python3 intake_generator.py generate --type over_bumper --piece-diameter 4.5
  python3 intake_generator.py generate --preset coral_2026
  python3 intake_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from motor_model import DCMotor, MOTOR_DB, recommend_intake_ratio, RPM_TO_RADS

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# MOTOR DEFINITIONS (from shared motor_model.py)
# ═══════════════════════════════════════════════════════════════════

MOTORS = {}
for _key, _m in MOTOR_DB.items():
    MOTORS[_key] = {
        "name": _m.name,
        "free_speed_rpm": _m.free_speed_rpm,
        "stall_torque_nm": _m.stall_torque_nm,
        "stall_current_a": _m.stall_current_a,
        "weight_lb": _m.weight_lb,
        "controller": _m.controller,
    }


# ═══════════════════════════════════════════════════════════════════
# ROLLER MATERIALS (Rule R3)
# ═══════════════════════════════════════════════════════════════════

ROLLER_MATERIALS = {
    "flex_wheels": {
        "name": "Flex Wheels (WCP/TTB)",
        "od_in": 4.0,
        "compression_pct": 15,  # % compression into game piece
        "grip": "high",
        "durability": "medium",
        "weight_per_wheel_lb": 0.12,
        "notes": "Best for round game pieces, 254/1678 standard",
    },
    "compliant_wheels": {
        "name": "Compliant Wheels (AndyMark)",
        "od_in": 4.0,
        "compression_pct": 20,
        "grip": "very_high",
        "durability": "low",
        "weight_per_wheel_lb": 0.15,
        "notes": "Maximum grip, wears faster",
    },
    "green_wheels": {
        "name": "Stealth Wheels (Brecoflex green)",
        "od_in": 2.0,
        "compression_pct": 5,
        "grip": "medium",
        "durability": "high",
        "weight_per_wheel_lb": 0.08,
        "notes": "Low compression, good for hard game pieces",
    },
    "surgical_tubing": {
        "name": "Surgical Tubing on Hex Shaft",
        "od_in": 1.5,
        "compression_pct": 25,
        "grip": "high",
        "durability": "low",
        "weight_per_wheel_lb": 0.05,
        "notes": "Cheapest option, replace between events",
    },
}


# ═══════════════════════════════════════════════════════════════════
# INTAKE TYPES
# ═══════════════════════════════════════════════════════════════════

INTAKE_TYPES = {
    "over_bumper": {
        "name": "Over-Bumper Intake",
        "deploy_required": True,
        "ground_pickup": True,
        "bumper_clearance_in": 5.0,
        "complexity": "medium",
        "description": "Pivots over bumper to contact ground game pieces. Most common in modern FRC.",
    },
    "under_bumper": {
        "name": "Under-Bumper Intake",
        "deploy_required": False,
        "ground_pickup": True,
        "bumper_clearance_in": 0,
        "complexity": "low",
        "description": "Rollers under bumper line. Simpler but limits bumper design.",
    },
    "fixed_full_width": {
        "name": "Fixed Full-Width Intake",
        "deploy_required": False,
        "ground_pickup": True,
        "bumper_clearance_in": 0,
        "complexity": "low",
        "description": "Full frame-width roller, always deployed. Simplest but takes frame space.",
    },
}


# ═══════════════════════════════════════════════════════════════════
# DEPLOY MECHANISMS
# ═══════════════════════════════════════════════════════════════════

DEPLOY_TYPES = {
    "pivot": {
        "name": "Pivot Deploy (pneumatic or motor)",
        "weight_lb": 1.5,
        "motor_required": True,
        "travel_deg": 110,
        "deploy_time_sec": 0.3,
    },
    "linear": {
        "name": "Linear Slide Deploy",
        "weight_lb": 2.0,
        "motor_required": True,
        "travel_deg": 0,
        "deploy_time_sec": 0.5,
    },
    "none": {
        "name": "No Deploy (fixed position)",
        "weight_lb": 0,
        "motor_required": False,
        "travel_deg": 0,
        "deploy_time_sec": 0,
    },
}


# ═══════════════════════════════════════════════════════════════════
# INTAKE SPEC DATACLASS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class IntakeSpec:
    """Complete parametric intake specification."""
    # Input parameters
    intake_type: str = "over_bumper"
    game_piece_diameter_in: float = 4.5
    game_piece_shape: str = "cylinder"  # cylinder, sphere, irregular
    frame_width_in: float = 26.0
    roller_material: str = "flex_wheels"
    deploy_type: str = "pivot"
    drivetrain_speed_fps: float = 14.5  # robot max speed (intake targets 2x this)

    # Roller configuration (computed)
    intake_width_in: float = 0.0
    roller_count: int = 0
    roller_spacing_in: float = 0.0
    roller_speed_rpm: float = 0.0
    compression_in: float = 0.0
    roller_od_in: float = 0.0

    # Motor configuration
    roller_motor_type: str = "neo"
    roller_motor_count: int = 1
    roller_gear_ratio: float = 3.0
    deploy_motor_type: str = "neo_550"
    deploy_gear_ratio: float = 50.0

    # Performance
    surface_speed_fps: float = 0.0
    acquire_time_sec: float = 0.0
    cycle_contribution_sec: float = 0.0

    # Weight budget
    roller_weight_lb: float = 0.0
    frame_weight_lb: float = 0.0
    motor_weight_lb: float = 0.0
    deploy_weight_lb: float = 0.0
    hardware_weight_lb: float = 0.5
    total_weight_lb: float = 0.0
    weight_ok: bool = True

    # Output
    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    preset_name: str = ""
    notes: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# ROLLER CONFIGURATION CALCULATOR
# ═══════════════════════════════════════════════════════════════════

def calculate_roller_config(
    game_piece_diameter_in: float,
    frame_width_in: float,
    roller_material: str,
    intake_type: str,
) -> dict:
    """Calculate roller count, spacing, and compression for a game piece."""
    material = ROLLER_MATERIALS[roller_material]
    roller_od = material["od_in"]
    compression_pct = material["compression_pct"]

    # Intake width: Rule R2 says full-width (bumper-to-bumper)
    # Leave 1" per side for structure
    intake_width = frame_width_in - 2.0

    # Compression into game piece
    compression = game_piece_diameter_in * (compression_pct / 100.0)

    # Roller spacing: center-to-center distance
    # For cylinders: spacing = roller_od + game_piece_diameter - compression
    # This ensures the game piece contacts both rollers
    if game_piece_diameter_in <= roller_od:
        # Small piece: rollers close together
        spacing = roller_od + game_piece_diameter_in * 0.3
    else:
        # Standard: rollers spaced to grip the piece
        spacing = roller_od + game_piece_diameter_in - compression

    # Number of roller sets along the intake path
    # Over-bumper needs at least 2 (grab + funnel), ideally 3
    # Under-bumper needs 1-2
    # Full-width needs 1
    type_config = INTAKE_TYPES[intake_type]
    if intake_type == "over_bumper":
        roller_count = max(2, min(4, math.ceil(type_config["bumper_clearance_in"] / spacing) + 1))
    elif intake_type == "under_bumper":
        roller_count = 2
    else:  # fixed_full_width
        roller_count = 1

    return {
        "intake_width_in": round(intake_width, 1),
        "roller_count": roller_count,
        "roller_spacing_in": round(spacing, 2),
        "compression_in": round(compression, 2),
        "roller_od_in": roller_od,
    }


# ═══════════════════════════════════════════════════════════════════
# GEAR RATIO CALCULATOR
# ═══════════════════════════════════════════════════════════════════

def recommend_roller_ratio(
    game_piece_diameter_in: float,
    roller_od_in: float,
    motor_type: str = "neo",
    target_surface_speed_fps: float = 15.0,
    drivetrain_speed_fps: float = 0.0,
) -> dict:
    """
    Calculate gear ratio for intake rollers.

    If drivetrain_speed_fps is provided (> 0), uses the ReCalc/254 principle:
    intake surface speed = 2x drivetrain speed. This ensures the robot can
    drive into game pieces and reliably acquire them.

    Otherwise falls back to the explicit target_surface_speed_fps.
    """
    dc_motor = MOTOR_DB[motor_type]

    if drivetrain_speed_fps > 0:
        # ReCalc method: ratio = (roller_radius * motor_free_speed) / (drivetrain_speed * 2)
        result = recommend_intake_ratio(
            dc_motor, roller_od_in, drivetrain_speed_fps, speed_multiplier=2.0,
        )
        return {
            "gear_ratio": result["gear_ratio"],
            "roller_rpm": result["roller_rpm"],
            "surface_speed_fps": result["surface_speed_fps"],
            "target_speed_fps": result["target_speed_fps"],
            "motor_type": motor_type,
        }

    # Fallback: target a specific surface speed
    roller_circumference_ft = (math.pi * roller_od_in) / 12.0
    target_roller_rpm = (target_surface_speed_fps * 60.0) / roller_circumference_ft

    operating_rpm = dc_motor.free_speed_rpm * 0.80
    ratio = operating_rpm / target_roller_rpm

    ratio = round(ratio * 2) / 2
    ratio = max(1.0, min(100.0, ratio))

    actual_roller_rpm = operating_rpm / ratio
    actual_surface_speed = actual_roller_rpm * roller_circumference_ft / 60.0

    return {
        "gear_ratio": ratio,
        "roller_rpm": round(actual_roller_rpm, 0),
        "surface_speed_fps": round(actual_surface_speed, 1),
        "target_speed_fps": round(target_surface_speed_fps, 1),
        "motor_type": motor_type,
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_intake(
    intake_type: str = "over_bumper",
    game_piece_diameter_in: float = 4.5,
    game_piece_shape: str = "cylinder",
    frame_width_in: float = 26.0,
    roller_material: str = "flex_wheels",
    roller_motor_type: str = "neo",
    deploy_type: Optional[str] = None,
    drivetrain_speed_fps: float = 14.5,
    preset_name: str = "",
) -> IntakeSpec:
    """Generate a complete intake specification."""

    # Validate inputs
    if intake_type not in INTAKE_TYPES:
        raise ValueError(f"Unknown intake type: {intake_type}. Options: {list(INTAKE_TYPES.keys())}")
    if roller_material not in ROLLER_MATERIALS:
        raise ValueError(f"Unknown roller material: {roller_material}. Options: {list(ROLLER_MATERIALS.keys())}")
    if roller_motor_type not in MOTORS:
        raise ValueError(f"Unknown motor type: {roller_motor_type}. Options: {list(MOTORS.keys())}")

    # Auto-select deploy type if not specified
    type_config = INTAKE_TYPES[intake_type]
    if deploy_type is None:
        deploy_type = "pivot" if type_config["deploy_required"] else "none"
    if deploy_type not in DEPLOY_TYPES:
        raise ValueError(f"Unknown deploy type: {deploy_type}. Options: {list(DEPLOY_TYPES.keys())}")

    spec = IntakeSpec(
        intake_type=intake_type,
        game_piece_diameter_in=game_piece_diameter_in,
        game_piece_shape=game_piece_shape,
        frame_width_in=frame_width_in,
        roller_material=roller_material,
        deploy_type=deploy_type,
        roller_motor_type=roller_motor_type,
        preset_name=preset_name,
    )

    # ── Roller configuration ──
    roller_config = calculate_roller_config(
        game_piece_diameter_in, frame_width_in, roller_material, intake_type,
    )
    spec.intake_width_in = roller_config["intake_width_in"]
    spec.roller_count = roller_config["roller_count"]
    spec.roller_spacing_in = roller_config["roller_spacing_in"]
    spec.compression_in = roller_config["compression_in"]
    spec.roller_od_in = roller_config["roller_od_in"]

    # ── Motor count ──
    # 1 motor for ≤2 rollers, 2 motors for 3+
    spec.roller_motor_count = 1 if spec.roller_count <= 2 else 2

    # ── Gear ratio ──
    # ReCalc/254 principle: intake surface speed = 2x drivetrain speed
    # Fallback: 15 fps for most game pieces, 20 fps for small/fast pieces
    target_speed = 20.0 if game_piece_diameter_in < 3.0 else 15.0
    ratio_calc = recommend_roller_ratio(
        game_piece_diameter_in, spec.roller_od_in, roller_motor_type, target_speed,
        drivetrain_speed_fps=drivetrain_speed_fps,
    )
    spec.roller_gear_ratio = ratio_calc["gear_ratio"]
    spec.roller_speed_rpm = ratio_calc["roller_rpm"]
    spec.surface_speed_fps = ratio_calc["surface_speed_fps"]

    # ── Deploy gear ratio ──
    if deploy_type != "none":
        # Deploy motor: NEO 550 with high reduction for position control
        spec.deploy_motor_type = "neo_550"
        spec.deploy_gear_ratio = 50.0
    else:
        spec.deploy_motor_type = "none"
        spec.deploy_gear_ratio = 0

    # ── Performance estimates ──
    # Acquire time: how long from "piece touches roller" to "piece secured"
    # Depends on intake path length and surface speed
    path_length_in = spec.roller_count * spec.roller_spacing_in
    spec.acquire_time_sec = round(path_length_in / (spec.surface_speed_fps * 12), 2)
    deploy_config = DEPLOY_TYPES[deploy_type]
    spec.cycle_contribution_sec = round(
        spec.acquire_time_sec + deploy_config["deploy_time_sec"] * 2,  # deploy + retract
        2,
    )

    # ── Weight budget ──
    material = ROLLER_MATERIALS[roller_material]
    motor = MOTORS[roller_motor_type]

    # Rollers: wheels + hex shafts
    wheels_per_roller = max(2, math.ceil(spec.intake_width_in / 3.0))  # one wheel per 3"
    total_wheels = wheels_per_roller * spec.roller_count
    shaft_weight = 0.15 * spec.roller_count  # ~0.15 lb per hex shaft
    spec.roller_weight_lb = round(
        total_wheels * material["weight_per_wheel_lb"] + shaft_weight, 2,
    )

    # Frame: side plates (2x polycarb or aluminum) + cross bars
    plate_weight = 2 * (spec.intake_width_in * 0.002)  # polycarb plates
    crossbar_weight = spec.roller_count * 0.1  # small crossbars
    spec.frame_weight_lb = round(plate_weight + crossbar_weight, 2)

    # Motors
    deploy_motor_weight = 0
    if deploy_type != "none":
        deploy_motor = MOTORS.get(spec.deploy_motor_type, MOTORS["neo_550"])
        deploy_motor_weight = deploy_motor["weight_lb"]
    spec.motor_weight_lb = round(
        spec.roller_motor_count * motor["weight_lb"] + deploy_motor_weight, 2,
    )

    # Deploy mechanism
    spec.deploy_weight_lb = deploy_config["weight_lb"]

    # Total
    spec.total_weight_lb = round(
        spec.roller_weight_lb +
        spec.frame_weight_lb +
        spec.motor_weight_lb +
        spec.deploy_weight_lb +
        spec.hardware_weight_lb,
        2,
    )

    # Weight check: intake should be < 10 lb (championship standard)
    spec.weight_ok = spec.total_weight_lb <= 10.0

    # ── Software constants ──
    spec.software_constants = {
        "ROLLER_GEAR_RATIO": spec.roller_gear_ratio,
        "ROLLER_MOTOR_COUNT": spec.roller_motor_count,
        "ROLLER_DIAMETER_IN": spec.roller_od_in,
        "SURFACE_SPEED_FPS": spec.surface_speed_fps,
        "INTAKE_SPEED": 0.8,  # default motor output fraction
        "OUTTAKE_SPEED": -0.5,  # reverse for ejection
    }

    if deploy_type != "none":
        spec.software_constants.update({
            "DEPLOY_GEAR_RATIO": spec.deploy_gear_ratio,
            "DEPLOY_ANGLE_DEG": float(deploy_config["travel_deg"]),
            "DEPLOY_SPEED": 0.5,
            "RETRACT_SPEED": -0.3,
            "DEPLOY_POSITION_TOLERANCE_DEG": 5.0,
        })

    # ── Notes ──
    spec.notes = []
    if roller_material == "flex_wheels":
        spec.notes.append("R3: Flex wheels are the championship standard for round game pieces")
    if spec.intake_width_in >= frame_width_in - 4:
        spec.notes.append("R2: Full-width intake (bumper-to-bumper) for maximum capture zone")
    if spec.roller_count >= 3:
        spec.notes.append("3+ roller stages: first stage grabs, middle funnels, last feeds to conveyor")
    if drivetrain_speed_fps > 0:
        spec.notes.append(f"ReCalc: surface speed = 2x drivetrain speed ({drivetrain_speed_fps} fps → {spec.surface_speed_fps} fps)")
    spec.drivetrain_speed_fps = drivetrain_speed_fps
    if game_piece_shape == "irregular":
        spec.notes.append("Irregular game piece: consider compliant wheels for better grip conformance")

    # ── Parts list ──
    spec.parts_list = _build_parts_list(spec, deploy_type, total_wheels)

    return spec


# ═══════════════════════════════════════════════════════════════════
# PARTS LIST
# ═══════════════════════════════════════════════════════════════════

def _build_parts_list(spec: IntakeSpec, deploy_type: str, total_wheels: int) -> list:
    """Generate a complete parts list for the intake."""
    material = ROLLER_MATERIALS[spec.roller_material]
    motor = MOTORS[spec.roller_motor_type]
    parts = []

    parts.append({
        "qty": total_wheels,
        "item": f"{material['name']} ({material['od_in']}\" OD)",
        "notes": f"Roller wheels, {spec.roller_count} rollers x {total_wheels // spec.roller_count} per shaft",
    })

    parts.append({
        "qty": spec.roller_count,
        "item": "1/2\" hex shaft",
        "notes": f"Cut to {spec.intake_width_in + 2}\" (intake width + bearings)",
    })

    parts.append({
        "qty": spec.roller_count * 2,
        "item": "Flanged bearing (1/2\" hex bore)",
        "notes": "One per shaft end",
    })

    parts.append({
        "qty": spec.roller_motor_count,
        "item": f"{motor['name']} motor",
        "notes": f"With {motor['controller']}, {spec.roller_gear_ratio}:1 reduction",
    })

    if spec.roller_motor_count > 1:
        parts.append({
            "qty": 1,
            "item": "Roller belt/chain run",
            "notes": "Link rollers to single gear output or individual drive",
        })

    parts.append({
        "qty": 2,
        "item": "Side plates (1/4\" polycarb or 1/8\" aluminum)",
        "notes": f"Cut to intake profile, {spec.intake_width_in}\" apart",
    })

    if deploy_type != "none":
        deploy_motor = MOTORS.get(spec.deploy_motor_type, MOTORS["neo_550"])
        parts.append({
            "qty": 1,
            "item": f"{deploy_motor['name']} motor (deploy)",
            "notes": f"With {deploy_motor['controller']}, {spec.deploy_gear_ratio}:1 MAXPlanetary",
        })

        if deploy_type == "pivot":
            parts.append({
                "qty": 2,
                "item": "Pivot shaft + bearing blocks",
                "notes": "1/2\" hex, mounted on robot frame cross member",
            })
        elif deploy_type == "linear":
            parts.append({
                "qty": 2,
                "item": "Linear slide rails",
                "notes": "Drawer slides or custom aluminum track",
            })

    parts.append({
        "qty": 1,
        "item": "Hardware assortment (#10-32)",
        "notes": "Bolts, nuts, spacers for assembly",
    })

    return parts


# ═══════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════

PRESETS = {
    "coral_2026": {
        "description": "Over-bumper intake for 2026 Coral (cylindrical tube)",
        "params": {
            "intake_type": "over_bumper",
            "game_piece_diameter_in": 4.5,
            "game_piece_shape": "cylinder",
            "frame_width_in": 26.0,
            "roller_material": "flex_wheels",
            "roller_motor_type": "neo",
        },
    },
    "ball_generic": {
        "description": "Over-bumper intake for spherical game pieces (cargo-style)",
        "params": {
            "intake_type": "over_bumper",
            "game_piece_diameter_in": 9.5,
            "game_piece_shape": "sphere",
            "frame_width_in": 26.0,
            "roller_material": "compliant_wheels",
            "roller_motor_type": "neo",
        },
    },
    "small_piece": {
        "description": "Under-bumper for small game pieces (< 3\" diameter)",
        "params": {
            "intake_type": "under_bumper",
            "game_piece_diameter_in": 2.5,
            "game_piece_shape": "cylinder",
            "frame_width_in": 26.0,
            "roller_material": "green_wheels",
            "roller_motor_type": "neo_550",
        },
    },
    "full_width_simple": {
        "description": "Fixed full-width roller, simplest possible intake",
        "params": {
            "intake_type": "fixed_full_width",
            "game_piece_diameter_in": 4.5,
            "game_piece_shape": "cylinder",
            "frame_width_in": 26.0,
            "roller_material": "flex_wheels",
            "roller_motor_type": "neo_550",
        },
    },
    "competition": {
        "description": "Competition-tuned over-bumper with Kraken drive",
        "params": {
            "intake_type": "over_bumper",
            "game_piece_diameter_in": 4.5,
            "game_piece_shape": "cylinder",
            "frame_width_in": 28.0,
            "roller_material": "flex_wheels",
            "roller_motor_type": "kraken_x60",
        },
    },
}


# ═══════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════

def display_spec(spec: IntakeSpec):
    """Print a formatted intake specification."""
    type_config = INTAKE_TYPES[spec.intake_type]
    material = ROLLER_MATERIALS[spec.roller_material]
    motor = MOTORS[spec.roller_motor_type]
    deploy = DEPLOY_TYPES[spec.deploy_type]

    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Intake" if spec.preset_name else "2950 Custom Intake"
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.3")
    print(f"{'═' * 60}")

    print(f"\n  CONFIGURATION")
    print(f"    Type:              {type_config['name']}")
    print(f"    Game piece:        {spec.game_piece_diameter_in}\" {spec.game_piece_shape}")
    print(f"    Intake width:      {spec.intake_width_in}\" (frame: {spec.frame_width_in}\")")
    print(f"    Deploy:            {deploy['name']}")

    print(f"\n  ROLLERS")
    print(f"    Material:          {material['name']}")
    print(f"    Roller OD:         {spec.roller_od_in}\"")
    print(f"    Roller count:      {spec.roller_count} (along intake path)")
    print(f"    Spacing:           {spec.roller_spacing_in}\" center-to-center")
    print(f"    Compression:       {spec.compression_in}\" ({material['compression_pct']}%)")

    print(f"\n  DRIVE SYSTEM")
    print(f"    Roller motors:     {spec.roller_motor_count}x {motor['name']}")
    print(f"    Controller:        {motor['controller']}")
    print(f"    Gear ratio:        {spec.roller_gear_ratio}:1")
    print(f"    Roller speed:      {spec.roller_speed_rpm:.0f} RPM")
    if spec.drivetrain_speed_fps > 0:
        print(f"    Surface speed:     {spec.surface_speed_fps} fps (2x drivetrain @ {spec.drivetrain_speed_fps} fps)")
    else:
        print(f"    Surface speed:     {spec.surface_speed_fps} fps")

    if spec.deploy_type != "none":
        deploy_motor = MOTORS.get(spec.deploy_motor_type, MOTORS["neo_550"])
        print(f"\n  DEPLOY MECHANISM")
        print(f"    Motor:             {deploy_motor['name']}")
        print(f"    Gear ratio:        {spec.deploy_gear_ratio}:1")
        print(f"    Travel:            {deploy['travel_deg']}°")
        print(f"    Deploy time:       {deploy['deploy_time_sec']}s")

    print(f"\n  PERFORMANCE")
    print(f"    Acquire time:      {spec.acquire_time_sec}s (piece contact → secured)")
    print(f"    Cycle contribution: {spec.cycle_contribution_sec}s (deploy + acquire + retract)")

    weight_status = "[PASS]" if spec.weight_ok else "[HEAVY]"
    print(f"\n  WEIGHT BUDGET")
    print(f"    Rollers + shafts:  {spec.roller_weight_lb} lb")
    print(f"    Side plates:       {spec.frame_weight_lb} lb")
    print(f"    Motors:            {spec.motor_weight_lb} lb")
    print(f"    Deploy mechanism:  {spec.deploy_weight_lb} lb")
    print(f"    Hardware:          {spec.hardware_weight_lb} lb")
    print(f"    {'─' * 25}")
    print(f"    INTAKE TOTAL:      {spec.total_weight_lb} lb {weight_status} (target: < 10 lb)")

    print(f"\n  SOFTWARE CONSTANTS (paste into Java)")
    print(f"    ```java")
    for key, value in spec.software_constants.items():
        if isinstance(value, float):
            print(f"    public static final double {key} = {value};")
        else:
            print(f"    public static final int {key} = {value};")
    print(f"    ```")

    if spec.notes:
        print(f"\n  NOTES")
        for note in spec.notes:
            print(f"    • {note}")

    print(f"\n  PARTS LIST")
    for part in spec.parts_list:
        print(f"    {part['qty']}x  {part['item']} — {part['notes']}")

    print(f"\n{'═' * 60}\n")


# ═══════════════════════════════════════════════════════════════════
# JSON EXPORT
# ═══════════════════════════════════════════════════════════════════

def save_spec(spec: IntakeSpec, filename: Optional[str] = None):
    """Save intake spec to JSON."""
    if filename is None:
        name = spec.preset_name or "custom"
        filename = f"2950_{name}_intake_spec.json"
    filepath = BASE_DIR / filename
    with open(filepath, "w") as f:
        json.dump(asdict(spec), f, indent=2)
    print(f"Spec saved to: {filepath}")
    return filepath


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  python3 intake_generator.py generate --preset coral_2026")
        print("  python3 intake_generator.py generate --type over_bumper --piece-diameter 4.5")
        print("  python3 intake_generator.py presets")
        return

    command = args[0]

    if command == "presets":
        print("Available presets:")
        for name, preset in PRESETS.items():
            print(f"  {name:20s} {preset['description']}")
        return

    if command == "generate":
        # Check for preset
        preset_name = None
        params = {}

        i = 1
        while i < len(args):
            if args[i] == "--preset" and i + 1 < len(args):
                preset_name = args[i + 1]
                i += 2
            elif args[i] == "--type" and i + 1 < len(args):
                params["intake_type"] = args[i + 1]
                i += 2
            elif args[i] == "--piece-diameter" and i + 1 < len(args):
                params["game_piece_diameter_in"] = float(args[i + 1])
                i += 2
            elif args[i] == "--piece-shape" and i + 1 < len(args):
                params["game_piece_shape"] = args[i + 1]
                i += 2
            elif args[i] == "--frame-width" and i + 1 < len(args):
                params["frame_width_in"] = float(args[i + 1])
                i += 2
            elif args[i] == "--roller" and i + 1 < len(args):
                params["roller_material"] = args[i + 1]
                i += 2
            elif args[i] == "--motor" and i + 1 < len(args):
                params["roller_motor_type"] = args[i + 1]
                i += 2
            elif args[i] == "--deploy" and i + 1 < len(args):
                params["deploy_type"] = args[i + 1]
                i += 2
            else:
                print(f"Unknown argument: {args[i]}")
                return

        if preset_name:
            if preset_name not in PRESETS:
                print(f"Unknown preset: {preset_name}. Available: {list(PRESETS.keys())}")
                return
            preset_params = PRESETS[preset_name]["params"].copy()
            preset_params.update(params)  # CLI overrides preset defaults
            spec = generate_intake(**preset_params, preset_name=preset_name)
        else:
            spec = generate_intake(**params)

        display_spec(spec)
        save_spec(spec)
        return

    print(f"Unknown command: {command}. Use 'generate' or 'presets'.")


if __name__ == "__main__":
    main()
