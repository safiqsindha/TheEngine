#!/usr/bin/env python3
"""
THE ENGINE — Configuration Generator
tools/generate_configs.py

Reads hardware_config.ini and regenerates:
  - src/main/deploy/swerve/swervedrive.json
  - src/main/deploy/swerve/modules/frontleft.json
  - src/main/deploy/swerve/modules/frontright.json
  - src/main/deploy/swerve/modules/backleft.json
  - src/main/deploy/swerve/modules/backright.json
  - src/main/deploy/swerve/modules/physicalproperties.json
  - src/main/deploy/swerve/modules/pidfproperties.json
  - CAN_ID_REFERENCE.md

Usage:
    python tools/generate_configs.py [path/to/hardware_config.ini]
    Default: reads hardware_config.ini from project root
"""

import configparser
import json
import os
import sys

def load_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path)

    # Check for TODO values
    todos = []
    for section in config.sections():
        for key, value in config.items(section):
            if value.strip().upper() == "TODO":
                todos.append(f"  {section}.{key}")

    if todos:
        print("⚠️  WARNING: The following values are still TODO:")
        for t in todos:
            print(t)
        print("\nGenerating configs with placeholder values for simulation.")
        print("Fill in hardware_config.ini and re-run to get real values.\n")

    return config


def get_or_default(config, section, key, default):
    val = config.get(section, key, fallback="TODO")
    if val.strip().upper() == "TODO":
        return default
    return val


def get_float(config, section, key, default):
    val = get_or_default(config, section, key, str(default))
    try:
        return float(val)
    except ValueError:
        return default


def get_int(config, section, key, default):
    val = get_or_default(config, section, key, str(default))
    try:
        return int(val)
    except ValueError:
        return default


def get_bool(config, section, key, default):
    val = get_or_default(config, section, key, str(default))
    return val.lower() in ("true", "yes", "1")


def generate_module_json(config, module_name, drive_id_key, steer_id_key,
                         encoder_port_key, front_sign, left_sign):
    half_wb = get_float(config, "chassis", "wheelbase_inches", 21.73) / 2
    half_tw = get_float(config, "chassis", "trackwidth_inches", 21.73) / 2
    canbus = get_or_default(config, "can_bus", "canbus_name", "rio")
    canbus_str = "" if canbus == "rio" else canbus

    # Determine encoder type based on connection method
    enc_connection = get_or_default(config, "swerve_module", "encoder_connection", "thrifty")
    encoder_type = "attached" if enc_connection == "attached" else "thrifty"

    return {
        "drive": {
            "type": "sparkmax",
            "id": get_int(config, "can_bus", drive_id_key, 0),
            "canbus": canbus_str
        },
        "angle": {
            "type": "sparkmax",
            "id": get_int(config, "can_bus", steer_id_key, 0),
            "canbus": canbus_str
        },
        "encoder": {
            "type": encoder_type,
            "id": get_int(config, "encoders", encoder_port_key, 0),
            "canbus": ""
        },
        "inverted": {
            "drive": get_bool(config, "inversions", f"{module_name}_drive_inverted", False),
            "angle": get_bool(config, "inversions", f"{module_name}_steer_inverted", False)
        },
        "absoluteEncoderInverted": get_bool(config, "inversions",
                                            f"{module_name}_encoder_inverted", False),
        "absoluteEncoderOffset": get_float(config, "encoder_offsets",
                                           f"{module_name}_offset", 0.0),
        "location": {
            "front": round(front_sign * half_wb, 3),
            "left": round(left_sign * half_tw, 3)
        }
    }


def generate_swervedrive_json(config):
    gyro_type = get_or_default(config, "gyroscope", "gyro_type", "pigeon2")
    gyro_id = get_int(config, "gyroscope", "gyro_id", 13)
    canbus = get_or_default(config, "can_bus", "canbus_name", "rio")
    canbus_str = "" if canbus == "rio" else canbus

    # Map user-friendly names to YAGSL type strings
    gyro_type_map = {
        "pigeon2": "pigeon2",
        "navx_mxp": "navx_spi",
        "navx_usb": "navx_usb",
        "navx_micro": "navx_usb",
        "adis16470": "adis16470",
    }
    yagsl_gyro = gyro_type_map.get(gyro_type, gyro_type)

    return {
        "imu": {
            "type": yagsl_gyro,
            "id": gyro_id,
            "canbus": canbus_str
        },
        "invertedIMU": False,
        "modules": [
            "modules/frontleft.json",
            "modules/frontright.json",
            "modules/backleft.json",
            "modules/backright.json"
        ],
        "currentLimit": {
            "drive": get_int(config, "current_limits", "drive_current_limit", 40),
            "angle": get_int(config, "current_limits", "steer_current_limit", 20)
        },
        "rampRate": {
            "drive": 0.25,
            "angle": 0.25
        },
        "physicalCharacteristics": {
            "conversionFactor": {"drive": 0, "angle": 0},
            "wheelGripCoefficientOfFriction": 1.19,
            "optimalVoltage": 12
        },
        "maxSpeed": 4.5
    }


def generate_physical_properties(config):
    return {
        "conversionFactor": {
            "drive": {
                "gearRatio": get_float(config, "swerve_module", "drive_gear_ratio", 6.75),
                "diameter": get_float(config, "swerve_module", "wheel_diameter_inches", 4),
                "factor": 0
            },
            "angle": {
                "gearRatio": get_float(config, "swerve_module", "steer_gear_ratio", 21.43),
                "factor": 0
            }
        },
        "currentLimit": {
            "drive": get_int(config, "current_limits", "drive_current_limit", 40),
            "angle": get_int(config, "current_limits", "steer_current_limit", 20)
        },
        "rampRate": {"drive": 0.25, "angle": 0.25},
        "wheelGripCoefficientOfFriction": 1.19,
        "optimalVoltage": 12
    }


def generate_pidf_properties(config):
    return {
        "drive": {
            "p": get_float(config, "pid", "drive_p", 0.0020645),
            "i": get_float(config, "pid", "drive_i", 0.0),
            "d": get_float(config, "pid", "drive_d", 0.0),
            "f": get_float(config, "pid", "drive_f", 0.0),
            "iz": 0
        },
        "angle": {
            "p": get_float(config, "pid", "steer_p", 0.01),
            "i": get_float(config, "pid", "steer_i", 0.0),
            "d": get_float(config, "pid", "steer_d", 0.0),
            "f": get_float(config, "pid", "steer_f", 0.0),
            "iz": 0
        }
    }


def generate_can_reference(config):
    lines = [
        "# THE ENGINE — CAN ID Reference",
        "## Auto-generated from hardware_config.ini",
        "",
        "| Device | Type | CAN ID / Port |",
        "|--------|------|---------------|",
    ]

    modules = [
        ("Front Left", "front_left"),
        ("Front Right", "front_right"),
        ("Back Left", "back_left"),
        ("Back Right", "back_right"),
    ]

    for name, key in modules:
        drive_id = get_or_default(config, "can_bus", f"{key}_drive_id", "TODO")
        steer_id = get_or_default(config, "can_bus", f"{key}_steer_id", "TODO")
        enc_port = get_or_default(config, "encoders", f"{key}_encoder_port", "TODO")
        lines.append(f"| {name} Drive | TalonFX (Kraken X60) | CAN {drive_id} |")
        lines.append(f"| {name} Steer | TalonFX (Kraken X60) | CAN {steer_id} |")
        lines.append(f"| {name} Encoder | Thrifty Absolute Magnetic | Analog {enc_port} |")

    gyro_type = get_or_default(config, "gyroscope", "gyro_type", "TODO")
    gyro_id = get_or_default(config, "gyroscope", "gyro_id", "TODO")
    lines.append(f"| Gyroscope | {gyro_type} | {gyro_id} |")

    lines.extend([
        "",
        "## Hardware Summary",
        f"- Module: Thrifty Swerve",
        f"- Drive gear ratio: {get_or_default(config, 'swerve_module', 'drive_gear_ratio', 'TODO')}",
        f"- Steer gear ratio: {get_or_default(config, 'swerve_module', 'steer_gear_ratio', 'TODO')}",
        f"- Wheel diameter: {get_or_default(config, 'swerve_module', 'wheel_diameter_inches', 'TODO')} inches",
        f"- Trackwidth: {get_or_default(config, 'chassis', 'trackwidth_inches', 'TODO')} inches",
        f"- Wheelbase: {get_or_default(config, 'chassis', 'wheelbase_inches', 'TODO')} inches",
        f"- Limelight: {get_or_default(config, 'other_hardware', 'limelight_count', 'TODO')}x {get_or_default(config, 'other_hardware', 'limelight_version', 'TODO')}",
    ])

    return "\n".join(lines)


def write_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✓ {filepath}")


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "hardware_config.ini"

    if not os.path.exists(config_path):
        print(f"ERROR: {config_path} not found.")
        print("Run from the project root directory.")
        sys.exit(1)

    print(f"Reading {config_path}...")
    config = load_config(config_path)

    print("\nGenerating YAGSL configs...")
    deploy = "src/main/deploy/swerve"

    write_json(generate_swervedrive_json(config), f"{deploy}/swervedrive.json")

    modules = [
        ("front_left", "front_left_drive_id", "front_left_steer_id",
         "front_left_encoder_port", 1, 1),
        ("front_right", "front_right_drive_id", "front_right_steer_id",
         "front_right_encoder_port", 1, -1),
        ("back_left", "back_left_drive_id", "back_left_steer_id",
         "back_left_encoder_port", -1, 1),
        ("back_right", "back_right_drive_id", "back_right_steer_id",
         "back_right_encoder_port", -1, -1),
    ]

    for name, drive_key, steer_key, enc_key, front_sign, left_sign in modules:
        data = generate_module_json(config, name, drive_key, steer_key,
                                    enc_key, front_sign, left_sign)
        filename = name.replace("_", "") + ".json"
        write_json(data, f"{deploy}/modules/{filename}")

    write_json(generate_physical_properties(config), f"{deploy}/modules/physicalproperties.json")
    write_json(generate_pidf_properties(config), f"{deploy}/modules/pidfproperties.json")

    print("\nGenerating CAN ID reference...")
    can_ref = generate_can_reference(config)
    with open("CAN_ID_REFERENCE.md", "w") as f:
        f.write(can_ref)
    print("  ✓ CAN_ID_REFERENCE.md")

    print("\n✅ All configs generated. Review the files and run ./gradlew build.")
    print("\nTo update configs later: edit hardware_config.ini and re-run this script.")


if __name__ == "__main__":
    main()
