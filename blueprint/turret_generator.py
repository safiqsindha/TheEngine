"""
The Blueprint — Parametric Turret Generator (B.5)
Team 2950 — The Devastators

Generates a turret specification from parameters:
  - Turret diameter (bearing OD)
  - Payload weight (everything above the turret)
  - Angular range (continuous 360° or limited arc)
  - Motor type + gear ratio
  - Current limit + efficiency

Physics: DC motor torque vs friction torque + payload inertia,
Euler-integrated motion profile for slew time.
Based on 254 (2020 turret), 1678 (2022 turret), 2056 (2020 turret).

Usage:
  python3 turret_generator.py generate --preset shooter_turret
  python3 turret_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from motor_model import DCMotor, MOTOR_DB, V_NOMINAL, LB_TO_N, IN_TO_M, GRAVITY_MPS2, RPM_TO_RADS

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# TURRET BEARINGS
# ═══════════════════════════════════════════════════════════════════

TURRET_BEARINGS = {
    "lazy_susan_12": {
        "name": "12\" Lazy Susan Bearing",
        "od_in": 12.0,
        "id_in": 9.0,
        "height_in": 0.375,
        "max_load_lb": 1000,
        "weight_lb": 1.2,
        "friction_coeff": 0.01,
    },
    "lazy_susan_6": {
        "name": "6\" Lazy Susan Bearing",
        "od_in": 6.0,
        "id_in": 4.0,
        "height_in": 0.3,
        "max_load_lb": 500,
        "weight_lb": 0.6,
        "friction_coeff": 0.012,
    },
    "custom_ring": {
        "name": "Custom Ring Bearing (Thrifty)",
        "od_in": 10.0,
        "id_in": 7.5,
        "height_in": 0.5,
        "max_load_lb": 800,
        "weight_lb": 0.9,
        "friction_coeff": 0.008,
    },
}

# ═══════════════════════════════════════════════════════════════════
# DRIVE TYPES
# ═══════════════════════════════════════════════════════════════════

TURRET_DRIVES = {
    "gear": {
        "name": "Ring Gear Drive",
        "description": "Pinion meshes with ring gear on bearing OD. Most common FRC turret drive.",
        "efficiency": 0.90,
        "backlash_deg": 0.5,
        "weight_lb": 0.8,
    },
    "belt": {
        "name": "Belt Drive",
        "description": "Timing belt wraps around turret ring. Lower backlash, quieter.",
        "efficiency": 0.95,
        "backlash_deg": 0.1,
        "weight_lb": 0.5,
    },
    "chain": {
        "name": "Chain Drive",
        "description": "#25 chain wraps around turret sprocket. High strength, more backlash.",
        "efficiency": 0.88,
        "backlash_deg": 1.0,
        "weight_lb": 0.7,
    },
}


# ═══════════════════════════════════════════════════════════════════
# TURRET SPEC
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TurretSpec:
    """Complete parametric turret specification."""
    # Inputs
    bearing_type: str = "lazy_susan_12"
    drive_type: str = "gear"
    payload_weight_lb: float = 15.0
    motor_type: str = "neo_550"
    motor_count: int = 1
    gear_ratio: float = 100.0
    current_limit_a: float = 20.0
    efficiency: float = 0.90
    min_angle_deg: float = -180.0
    max_angle_deg: float = 180.0
    continuous_rotation: bool = False

    # Computed — geometry
    turret_od_in: float = 0.0
    turret_id_in: float = 0.0
    pinion_teeth: int = 16
    ring_teeth: int = 0
    ring_gear_ratio: float = 0.0
    total_ratio: float = 0.0

    # Computed — performance
    slew_time_180_sec: float = 0.0
    max_slew_rate_deg_s: float = 0.0
    peak_current_a: float = 0.0
    holding_current_a: float = 0.0
    friction_torque_nm: float = 0.0
    payload_moi_kg_m2: float = 0.0

    # Weight
    bearing_weight_lb: float = 0.0
    drive_weight_lb: float = 0.0
    motor_weight_lb: float = 0.0
    platform_weight_lb: float = 1.5
    total_weight_lb: float = 0.0

    # Output
    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    preset_name: str = ""


# ═══════════════════════════════════════════════════════════════════
# TURRET MOTION SIMULATION
# ═══════════════════════════════════════════════════════════════════

def simulate_turret_slew(
    motor: DCMotor,
    motor_count: int,
    total_ratio: float,
    payload_moi_kg_m2: float,
    friction_torque_nm: float,
    slew_angle_deg: float = 180.0,
    current_limit_a: float = 20.0,
    efficiency: float = 0.90,
    dt: float = 0.0005,
) -> dict:
    """Simulate turret slew from 0 to slew_angle using Euler integration."""
    theta = 0.0
    omega = 0.0
    t = 0.0
    target_theta = math.radians(slew_angle_deg)

    # Reflected MOI at motor shaft
    j_reflected = payload_moi_kg_m2 / (total_ratio ** 2)
    j_rotor = 0.00005822569  # motor rotor inertia
    j_total = j_reflected + j_rotor * motor_count

    max_omega = 0.0
    peak_current = 0.0

    max_steps = int(5.0 / dt)
    for _ in range(max_steps):
        # Motor speed from turret speed
        motor_speed_rads = abs(omega) * total_ratio

        # Current at this speed
        current = motor.current_at_speed(motor_speed_rads)
        effective_current = min(max(current, 0), current_limit_a)
        if effective_current > peak_current:
            peak_current = effective_current

        # Motor torque at motor shaft (current-limited)
        motor_torque = motor.kT * effective_current * motor_count * efficiency

        # Friction torque reflected to motor shaft
        friction_at_motor = friction_torque_nm / total_ratio

        # Net torque at motor shaft
        net_torque = motor_torque - friction_at_motor

        # Angular acceleration (at motor shaft)
        alpha_motor = net_torque / j_total if j_total > 0 else 0

        # Convert to turret shaft
        alpha_turret = alpha_motor / total_ratio

        # Euler integration (turret coordinates)
        omega += alpha_turret * dt
        theta += omega * dt
        t += dt

        if abs(omega) > max_omega:
            max_omega = abs(omega)

        if theta >= target_theta:
            break

    return {
        "slew_time_sec": round(t, 3),
        "max_slew_rate_deg_s": round(max_omega * 180 / math.pi, 1),
        "peak_current_a": round(peak_current, 1),
    }


# ═══════════════════════════════════════════════════════════════════
# TURRET GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_turret(
    bearing_type: str = "lazy_susan_12",
    drive_type: str = "gear",
    payload_weight_lb: float = 15.0,
    motor_type: str = "neo_550",
    motor_count: int = 1,
    gear_ratio: float = 100.0,
    current_limit_a: float = 20.0,
    efficiency: float = 0.90,
    min_angle_deg: float = -180.0,
    max_angle_deg: float = 180.0,
    continuous_rotation: bool = False,
    preset_name: str = "",
) -> TurretSpec:
    """Generate a complete turret specification."""
    if motor_type not in MOTOR_DB:
        raise ValueError(f"Unknown motor: {motor_type}. Options: {list(MOTOR_DB.keys())}")
    if bearing_type not in TURRET_BEARINGS:
        raise ValueError(f"Unknown bearing: {bearing_type}. Options: {list(TURRET_BEARINGS.keys())}")
    if drive_type not in TURRET_DRIVES:
        raise ValueError(f"Unknown drive: {drive_type}. Options: {list(TURRET_DRIVES.keys())}")

    dc_motor = MOTOR_DB[motor_type]
    bearing = TURRET_BEARINGS[bearing_type]
    drive = TURRET_DRIVES[drive_type]

    spec = TurretSpec(
        bearing_type=bearing_type, drive_type=drive_type,
        payload_weight_lb=payload_weight_lb,
        motor_type=motor_type, motor_count=motor_count,
        gear_ratio=gear_ratio, current_limit_a=current_limit_a,
        efficiency=efficiency * drive["efficiency"],
        min_angle_deg=min_angle_deg, max_angle_deg=max_angle_deg,
        continuous_rotation=continuous_rotation, preset_name=preset_name,
    )

    # Geometry
    spec.turret_od_in = bearing["od_in"]
    spec.turret_id_in = bearing["id_in"]

    # Ring gear ratio: ring_teeth / pinion_teeth
    # For a 12" OD bearing with 20DP gear: ring_teeth ≈ OD * DP
    # Standard FRC: 20 DP (diametral pitch)
    dp = 20  # diametral pitch
    spec.ring_teeth = int(spec.turret_od_in * dp)
    spec.pinion_teeth = 16  # standard small pinion
    spec.ring_gear_ratio = spec.ring_teeth / spec.pinion_teeth
    spec.total_ratio = gear_ratio * spec.ring_gear_ratio

    # Payload MOI: approximate as uniform disk
    payload_mass_kg = payload_weight_lb * LB_TO_N / GRAVITY_MPS2
    turret_radius_m = (spec.turret_od_in / 2) * IN_TO_M
    spec.payload_moi_kg_m2 = round(0.5 * payload_mass_kg * turret_radius_m ** 2, 6)

    # Friction torque at turret shaft
    friction_force_n = payload_weight_lb * LB_TO_N * bearing["friction_coeff"]
    spec.friction_torque_nm = round(friction_force_n * turret_radius_m, 4)

    # Holding current (to overcome friction)
    holding_torque_per_motor = spec.friction_torque_nm / (spec.total_ratio * motor_count * spec.efficiency)
    spec.holding_current_a = round(holding_torque_per_motor / dc_motor.kT, 2)

    # Simulate 180° slew
    sim = simulate_turret_slew(
        dc_motor, motor_count, spec.total_ratio,
        spec.payload_moi_kg_m2, spec.friction_torque_nm,
        slew_angle_deg=180.0, current_limit_a=current_limit_a,
        efficiency=spec.efficiency, dt=0.0005,
    )
    spec.slew_time_180_sec = sim["slew_time_sec"]
    spec.max_slew_rate_deg_s = sim["max_slew_rate_deg_s"]
    spec.peak_current_a = sim["peak_current_a"]

    # Weight
    spec.bearing_weight_lb = bearing["weight_lb"]
    spec.drive_weight_lb = drive["weight_lb"]
    spec.motor_weight_lb = round(dc_motor.weight_lb * motor_count + 0.5, 2)  # +0.5 for gearbox
    spec.platform_weight_lb = 1.5  # turret platform plate
    spec.total_weight_lb = round(
        spec.bearing_weight_lb + spec.drive_weight_lb +
        spec.motor_weight_lb + spec.platform_weight_lb + 0.3,  # +0.3 hardware
        2
    )

    # Software constants
    angular_range = abs(max_angle_deg - min_angle_deg)
    spec.software_constants = {
        "TURRET_GEAR_RATIO": spec.total_ratio,
        "TURRET_MOTOR_COUNT": motor_count,
        "MIN_ANGLE_DEG": min_angle_deg,
        "MAX_ANGLE_DEG": max_angle_deg,
        "CONTINUOUS_ROTATION": continuous_rotation,
        "CURRENT_LIMIT_A": current_limit_a,
        "kS": 0.08,
        "kV": round(V_NOMINAL / (dc_motor.free_speed_rads / spec.total_ratio * 180 / math.pi), 5),
        "kA": 0.005,
        "POSITION_TOLERANCE_DEG": 1.0,
        "MAX_SLEW_RATE_DEG_S": spec.max_slew_rate_deg_s,
        "BACKLASH_DEG": drive["backlash_deg"],
    }

    # Parts list
    spec.parts_list = [
        {"qty": 1, "item": bearing["name"], "notes": f"Max load {bearing['max_load_lb']} lb"},
        {"qty": motor_count, "item": f"{dc_motor.name} motor", "notes": f"With {dc_motor.controller}"},
        {"qty": 1, "item": f"Gearbox ({gear_ratio}:1)", "notes": "MAXPlanetary or belt reduction"},
    ]

    if drive_type == "gear":
        spec.parts_list.extend([
            {"qty": 1, "item": f"Ring gear ({spec.ring_teeth}T, 20DP)", "notes": f"Mounts to bearing OD ({spec.turret_od_in}\")"},
            {"qty": 1, "item": f"Pinion gear ({spec.pinion_teeth}T, 20DP)", "notes": "On gearbox output shaft"},
        ])
    elif drive_type == "belt":
        belt_length = round(math.pi * spec.turret_od_in + 6, 1)  # belt around ring + tensioner
        spec.parts_list.extend([
            {"qty": 1, "item": f"HTD5 timing belt ({belt_length}\")", "notes": "Wraps around turret ring"},
            {"qty": 1, "item": "Drive pulley (HTD5, 18T)", "notes": "On gearbox output shaft"},
            {"qty": 1, "item": "Belt tensioner", "notes": "Spring-loaded idler"},
        ])
    elif drive_type == "chain":
        spec.parts_list.extend([
            {"qty": 1, "item": f"#25 chain sprocket ({spec.ring_teeth}T)", "notes": f"Bolts to bearing OD"},
            {"qty": 1, "item": f"#25 chain sprocket ({spec.pinion_teeth}T)", "notes": "On gearbox output"},
            {"qty": 1, "item": "#25 roller chain", "notes": "Wraps turret + tensioner"},
        ])

    spec.parts_list.extend([
        {"qty": 1, "item": "Turret platform plate (1/4\" aluminum)", "notes": f"{spec.turret_od_in}\" dia or square"},
        {"qty": 1, "item": "Absolute encoder (through-bore)", "notes": "REV Through Bore or equivalent"},
        {"qty": 1, "item": "Slip ring (6 circuit)", "notes": "Power + CAN through rotation"},
        {"qty": 1, "item": "Hardware assortment", "notes": "Bolts, standoffs, spacers"},
    ])

    # Notes
    spec.notes = []
    if spec.slew_time_180_sec > 0.5:
        spec.notes.append(f"180° slew > 0.5s ({spec.slew_time_180_sec}s) — consider higher ratio or more motors")
    if spec.slew_time_180_sec <= 0.3:
        spec.notes.append(f"180° slew {spec.slew_time_180_sec}s — very fast, verify mechanical limits")
    if payload_weight_lb > bearing["max_load_lb"] * 0.8:
        spec.notes.append(f"Payload near bearing limit ({bearing['max_load_lb']} lb) — upgrade bearing")
    if continuous_rotation:
        spec.notes.append("Continuous rotation — slip ring required for power/CAN")
    else:
        spec.notes.append(f"Limited rotation ({min_angle_deg}° to {max_angle_deg}°) — hard stops recommended")
    if drive["backlash_deg"] > 0.5:
        spec.notes.append(f"Drive backlash {drive['backlash_deg']}° — use vision feedback for fine aiming")

    return spec


# ═══════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════

PRESETS = {
    "shooter_turret": {
        "description": "Standard shooter turret (270° range, 12\" bearing, gear drive)",
        "params": {
            "bearing_type": "lazy_susan_12",
            "drive_type": "gear",
            "payload_weight_lb": 15.0,
            "motor_type": "neo_550",
            "motor_count": 1,
            "gear_ratio": 10.0,  # × 15:1 ring = 150:1 total
            "min_angle_deg": -135.0,
            "max_angle_deg": 135.0,
            "continuous_rotation": False,
        },
    },
    "continuous_turret": {
        "description": "Full-rotation turret with slip ring (360°+ continuous)",
        "params": {
            "bearing_type": "lazy_susan_12",
            "drive_type": "belt",
            "payload_weight_lb": 12.0,
            "motor_type": "neo_550",
            "motor_count": 1,
            "gear_ratio": 8.0,  # × 15:1 ring = 120:1 total
            "min_angle_deg": -180.0,
            "max_angle_deg": 180.0,
            "continuous_rotation": True,
        },
    },
    "light_turret": {
        "description": "Lightweight turret for small payloads (6\" bearing)",
        "params": {
            "bearing_type": "lazy_susan_6",
            "drive_type": "belt",
            "payload_weight_lb": 6.0,
            "motor_type": "neo_550",
            "motor_count": 1,
            "gear_ratio": 5.0,  # × 7.5:1 ring = 37.5:1 total
            "min_angle_deg": -90.0,
            "max_angle_deg": 90.0,
            "continuous_rotation": False,
        },
    },
    "heavy_turret": {
        "description": "Heavy-duty turret for arm + end effector (NEO motor)",
        "params": {
            "bearing_type": "custom_ring",
            "drive_type": "gear",
            "payload_weight_lb": 25.0,
            "motor_type": "neo",
            "motor_count": 1,
            "gear_ratio": 8.0,  # × 12.5:1 ring = 100:1 total
            "min_angle_deg": -135.0,
            "max_angle_deg": 135.0,
            "continuous_rotation": False,
        },
    },
}


def display_spec(spec: TurretSpec):
    motor = MOTOR_DB[spec.motor_type]
    bearing = TURRET_BEARINGS[spec.bearing_type]
    drive = TURRET_DRIVES[spec.drive_type]
    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Turret" if spec.preset_name else "2950 Custom Turret"

    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.5")
    print(f"{'═' * 60}")
    print(f"\n  CONFIGURATION")
    print(f"    Bearing:           {bearing['name']} (OD {spec.turret_od_in}\")")
    print(f"    Drive:             {drive['name']}")
    print(f"    Payload:           {spec.payload_weight_lb} lb")
    print(f"    Motors:            {spec.motor_count}x {motor.name}")
    print(f"    Motor ratio:       {spec.gear_ratio}:1")
    print(f"    Ring ratio:        {spec.ring_gear_ratio:.1f}:1 ({spec.ring_teeth}T / {spec.pinion_teeth}T)")
    print(f"    Total ratio:       {spec.total_ratio:.1f}:1")
    range_str = "Continuous" if spec.continuous_rotation else f"{spec.min_angle_deg}° to {spec.max_angle_deg}°"
    print(f"    Range:             {range_str}")

    print(f"\n  PERFORMANCE (simulated with {spec.current_limit_a}A limit)")
    print(f"    180° slew time:    {spec.slew_time_180_sec}s")
    print(f"    Max slew rate:     {spec.max_slew_rate_deg_s}°/s")
    print(f"    Peak current:      {spec.peak_current_a}A")
    print(f"    Holding current:   {spec.holding_current_a}A")
    print(f"    Payload MOI:       {spec.payload_moi_kg_m2} kg·m²")
    print(f"    Backlash:          {drive['backlash_deg']}°")

    print(f"\n  WEIGHT: {spec.total_weight_lb} lb (turret only, not payload)")

    print(f"\n  SOFTWARE CONSTANTS")
    print(f"    ```java")
    for k, v in spec.software_constants.items():
        if isinstance(v, bool):
            print(f"    public static final boolean {k} = {str(v).lower()};")
        else:
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
        print("Usage: python3 turret_generator.py generate --preset shooter_turret")
        print("       python3 turret_generator.py presets")
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
            spec = generate_turret(**PRESETS[preset_name]["params"], preset_name=preset_name)
        else:
            spec = generate_turret()
        display_spec(spec)
        filepath = BASE_DIR / f"2950_{spec.preset_name or 'custom'}_turret_spec.json"
        with open(filepath, "w") as f:
            json.dump(asdict(spec), f, indent=2)
        print(f"Spec saved to: {filepath}")


if __name__ == "__main__":
    main()
