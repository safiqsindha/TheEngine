"""
The Blueprint — Parametric Conveyor/Indexer Generator (B.7)
Team 2950 — The Devastators

Generates a conveyor/indexer specification from parameters:
  - Conveyor length (intake to scoring mechanism)
  - Game piece geometry
  - Staging count (how many pieces can be held)
  - Belt/roller type
  - Motor type + gear ratio
  - Sensor configuration (beam breaks, proximity)

Physics: belt surface speed from motor model,
transit time = path_length / surface_speed.
Based on 254/1678 championship indexer architectures.

Usage:
  python3 conveyor_generator.py generate --preset single_stage
  python3 conveyor_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from motor_model import DCMotor, MOTOR_DB, RPM_TO_RADS

BASE_DIR = Path(__file__).parent


@dataclass
class ConveyorSpec:
    """Complete parametric conveyor/indexer specification."""
    # Inputs
    path_length_in: float = 18.0
    game_piece_diameter_in: float = 4.5
    staging_count: int = 1
    belt_type: str = "belt"
    motor_type: str = "neo_550"
    motor_count: int = 1
    gear_ratio: float = 5.0
    roller_diameter_in: float = 2.0
    current_limit_a: float = 20.0
    efficiency: float = 0.85

    # Sensor config
    sensor_type: str = "beam_break"
    sensor_count: int = 2

    # Computed
    belt_speed_fps: float = 0.0
    transit_time_sec: float = 0.0
    belt_length_in: float = 0.0
    roller_rpm: float = 0.0
    holding_current_a: float = 0.0

    # Weight
    motor_weight_lb: float = 0.0
    mechanism_weight_lb: float = 0.0
    total_weight_lb: float = 0.0

    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    preset_name: str = ""


BELT_TYPES = {
    "belt": {
        "name": "Flat Belt (polyurethane)",
        "grip": "high",
        "weight_per_in": 0.005,
        "notes": "Best for cylinders and flat game pieces",
    },
    "roller": {
        "name": "Roller Conveyor (Colson wheels)",
        "grip": "medium",
        "weight_per_in": 0.01,
        "notes": "Simple, easy to replace individual rollers",
    },
    "polycord": {
        "name": "Polycord Round Belt",
        "grip": "medium",
        "weight_per_in": 0.003,
        "notes": "Lightweight, good for round game pieces",
    },
}

SENSOR_TYPES = {
    "beam_break": {
        "name": "IR Beam Break",
        "weight_lb": 0.02,
        "notes": "Most reliable, detects any game piece crossing the beam",
    },
    "proximity": {
        "name": "Proximity Sensor (REV Color Sensor V3)",
        "weight_lb": 0.03,
        "notes": "Can detect color + distance, useful for sorting",
    },
    "limit_switch": {
        "name": "Mechanical Limit Switch",
        "weight_lb": 0.01,
        "notes": "Cheapest, but only works for hard game pieces",
    },
}


def generate_conveyor(
    path_length_in: float = 18.0,
    game_piece_diameter_in: float = 4.5,
    staging_count: int = 1,
    belt_type: str = "belt",
    motor_type: str = "neo_550",
    motor_count: int = 1,
    gear_ratio: float = 5.0,
    roller_diameter_in: float = 2.0,
    current_limit_a: float = 20.0,
    efficiency: float = 0.85,
    sensor_type: str = "beam_break",
    sensor_count: int = 2,
    preset_name: str = "",
) -> ConveyorSpec:
    """Generate a complete conveyor/indexer specification."""
    if motor_type not in MOTOR_DB:
        raise ValueError(f"Unknown motor: {motor_type}. Options: {list(MOTOR_DB.keys())}")
    if belt_type not in BELT_TYPES:
        raise ValueError(f"Unknown belt type: {belt_type}. Options: {list(BELT_TYPES.keys())}")

    dc_motor = MOTOR_DB[motor_type]
    belt_info = BELT_TYPES[belt_type]

    spec = ConveyorSpec(
        path_length_in=path_length_in, game_piece_diameter_in=game_piece_diameter_in,
        staging_count=staging_count, belt_type=belt_type,
        motor_type=motor_type, motor_count=motor_count,
        gear_ratio=gear_ratio, roller_diameter_in=roller_diameter_in,
        current_limit_a=current_limit_a, efficiency=efficiency,
        sensor_type=sensor_type, sensor_count=sensor_count,
        preset_name=preset_name,
    )

    # Roller RPM at output
    operating_rpm = dc_motor.free_speed_rpm * 0.80 / gear_ratio
    spec.roller_rpm = round(operating_rpm, 0)

    # Belt/surface speed
    roller_circumference_ft = (math.pi * roller_diameter_in) / 12.0
    spec.belt_speed_fps = round(operating_rpm * roller_circumference_ft / 60.0, 1)

    # Transit time: piece travels full path length
    if spec.belt_speed_fps > 0:
        spec.transit_time_sec = round((path_length_in / 12.0) / spec.belt_speed_fps, 3)
    else:
        spec.transit_time_sec = float('inf')

    # Belt length: loop around two rollers
    # Belt loop = 2 × path_length + π × roller_diameter
    spec.belt_length_in = round(2 * path_length_in + math.pi * roller_diameter_in, 1)

    # Holding current (very low — conveyor has no gravity load to hold)
    # Just friction: b × ω at motor shaft
    motor_omega = operating_rpm * RPM_TO_RADS
    friction_torque = dc_motor.b * motor_omega
    spec.holding_current_a = round(friction_torque / dc_motor.kT + dc_motor.free_current_a, 1)

    # Weight
    spec.motor_weight_lb = round(dc_motor.weight_lb * motor_count, 2)
    belt_weight = belt_info["weight_per_in"] * spec.belt_length_in
    roller_weight = 0.15 * 2  # two end rollers
    sensor_weight = SENSOR_TYPES[sensor_type]["weight_lb"] * sensor_count
    frame_weight = path_length_in * 0.02 * 2  # two side rails
    spec.mechanism_weight_lb = round(belt_weight + roller_weight + sensor_weight + frame_weight, 2)
    spec.total_weight_lb = round(spec.motor_weight_lb + spec.mechanism_weight_lb + 0.3, 2)  # +0.3 hardware

    # Software constants
    spec.software_constants = {
        "CONVEYOR_GEAR_RATIO": gear_ratio,
        "CONVEYOR_SPEED": 0.8,
        "CONVEYOR_REVERSE_SPEED": -0.5,
        "CONVEYOR_SLOW_SPEED": 0.3,
        "SENSOR_COUNT": sensor_count,
        "STAGING_COUNT": staging_count,
        "TRANSIT_TIME_SEC": spec.transit_time_sec,
    }

    # Notes
    spec.notes = []
    if staging_count > 1:
        spec.notes.append(f"Multi-stage indexer: {sensor_count} sensors for {staging_count} staging positions")
    if spec.belt_speed_fps < 5.0:
        spec.notes.append("Belt speed < 5 fps — may be too slow for fast cycles")
    if spec.belt_speed_fps > 25.0:
        spec.notes.append("Belt speed > 25 fps — risk of game piece bouncing/ejection")
    spec.notes.append(f"Sensor placement: entry at 0\", exit at {path_length_in}\"" +
                       (f", staging at {path_length_in/2:.0f}\"" if staging_count > 1 else ""))

    # Parts list
    spec.parts_list = [
        {"qty": motor_count, "item": f"{dc_motor.name} motor", "notes": f"With {dc_motor.controller}"},
        {"qty": 1, "item": f"Gearbox ({gear_ratio}:1)", "notes": "MAXPlanetary or belt reduction"},
    ]
    if belt_type == "belt":
        spec.parts_list.append(
            {"qty": 1, "item": f"Polyurethane belt ({spec.belt_length_in}\")", "notes": f"1\" or 2\" wide"}
        )
    elif belt_type == "polycord":
        spec.parts_list.append(
            {"qty": 2, "item": f"Polycord ({spec.belt_length_in}\" each)", "notes": "Round belt, welded loop"}
        )
    else:
        num_rollers = max(2, math.ceil(path_length_in / 3.0))
        spec.parts_list.append(
            {"qty": num_rollers, "item": "Colson wheels (2\" dia)", "notes": "On hex shaft"}
        )
    spec.parts_list.extend([
        {"qty": 2, "item": f"Drive rollers ({roller_diameter_in}\" dia)", "notes": "One driven, one idler"},
        {"qty": sensor_count, "item": SENSOR_TYPES[sensor_type]["name"], "notes": SENSOR_TYPES[sensor_type]["notes"]},
        {"qty": 2, "item": "Side rails (1x1 aluminum or polycarb)", "notes": f"{path_length_in}\" long"},
        {"qty": 1, "item": "Hardware assortment", "notes": "Bolts, spacers, belt tensioner"},
    ])

    return spec


def display_spec(spec: ConveyorSpec):
    motor = MOTOR_DB[spec.motor_type]
    belt = BELT_TYPES[spec.belt_type]
    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Conveyor" if spec.preset_name else "2950 Custom Conveyor"
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.7")
    print(f"{'═' * 60}")
    print(f"\n  CONFIGURATION")
    print(f"    Path length:       {spec.path_length_in}\"")
    print(f"    Belt type:         {belt['name']}")
    print(f"    Game piece:        {spec.game_piece_diameter_in}\" dia")
    print(f"    Staging:           {spec.staging_count} position(s)")
    print(f"    Motor:             {spec.motor_count}x {motor.name}")
    print(f"    Gear ratio:        {spec.gear_ratio}:1")
    print(f"    Sensors:           {spec.sensor_count}x {SENSOR_TYPES[spec.sensor_type]['name']}")
    print(f"\n  PERFORMANCE")
    print(f"    Belt speed:        {spec.belt_speed_fps} fps")
    print(f"    Roller RPM:        {spec.roller_rpm}")
    print(f"    Transit time:      {spec.transit_time_sec}s (end to end)")
    print(f"    Belt length:       {spec.belt_length_in}\"")
    print(f"    Holding current:   {spec.holding_current_a}A")
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
    "single_stage": {
        "description": "Single game piece indexer (intake → shooter)",
        "params": {
            "path_length_in": 18.0, "game_piece_diameter_in": 4.5,
            "staging_count": 1, "belt_type": "belt",
            "motor_type": "neo_550", "gear_ratio": 5.0,
            "sensor_count": 2,
        },
    },
    "dual_stage": {
        "description": "Two-piece staging indexer with mid sensor",
        "params": {
            "path_length_in": 24.0, "game_piece_diameter_in": 4.5,
            "staging_count": 2, "belt_type": "belt",
            "motor_type": "neo_550", "gear_ratio": 4.0,
            "sensor_count": 3,
        },
    },
    "short_feed": {
        "description": "Short direct feed (intake to mechanism, no staging)",
        "params": {
            "path_length_in": 10.0, "game_piece_diameter_in": 4.5,
            "staging_count": 1, "belt_type": "polycord",
            "motor_type": "neo_550", "gear_ratio": 3.0,
            "sensor_count": 1,
        },
    },
    "ball_indexer": {
        "description": "Ball indexer for spherical game pieces",
        "params": {
            "path_length_in": 20.0, "game_piece_diameter_in": 9.5,
            "staging_count": 2, "belt_type": "roller",
            "motor_type": "neo", "gear_ratio": 8.0,
            "roller_diameter_in": 3.0, "sensor_count": 3,
        },
    },
}


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 conveyor_generator.py generate --preset single_stage")
        print("       python3 conveyor_generator.py presets")
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
            spec = generate_conveyor(**PRESETS[preset_name]["params"], preset_name=preset_name)
        else:
            spec = generate_conveyor()
        display_spec(spec)
        filepath = BASE_DIR / f"2950_{spec.preset_name or 'custom'}_conveyor_spec.json"
        with open(filepath, "w") as f:
            json.dump(asdict(spec), f, indent=2)
        print(f"Spec saved to: {filepath}")


if __name__ == "__main__":
    main()
