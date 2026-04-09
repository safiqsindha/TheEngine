"""
The Blueprint — Parametric Flywheel/Shooter Generator (B.4)
Team 2950 — The Devastators

Generates a complete flywheel/shooter specification from parameters:
  - Wheel diameter + MOI
  - Target RPM / exit velocity
  - Game piece mass + diameter
  - Motor type + count
  - Current limit + efficiency

Physics model from ReCalc (reca.lc):
  - Analytical spinup time from DC motor first-order ODE
  - Energy transfer model (inelastic collision with rolling sphere)
  - Recovery time after shot
  - Exit velocity from energy conservation

Usage:
  python3 flywheel_generator.py generate --target-rpm 3000
  python3 flywheel_generator.py generate --preset coral_2026
  python3 flywheel_generator.py presets
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from motor_model import DCMotor, MOTOR_DB, V_NOMINAL, RPM_TO_RADS, LB_TO_N, IN_TO_M

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# FLYWHEEL SPEC
# ═══════════════════════════════════════════════════════════════════

@dataclass
class FlywheelSpec:
    """Complete parametric flywheel/shooter specification."""
    # Inputs
    wheel_diameter_in: float = 4.0
    wheel_count: int = 2
    motor_type: str = "neo_vortex"
    motor_count: int = 2
    gear_ratio: float = 1.0
    target_rpm: float = 3000.0
    current_limit_a: float = 40.0
    efficiency: float = 0.90

    # Game piece
    piece_mass_lb: float = 0.5
    piece_diameter_in: float = 4.5

    # Computed — flywheel properties
    wheel_moi_kg_m2: float = 0.0  # moment of inertia
    stored_energy_j: float = 0.0

    # Computed — performance
    spinup_time_sec: float = 0.0
    surface_speed_fps: float = 0.0
    exit_velocity_fps: float = 0.0
    energy_transfer_pct: float = 0.0
    speed_drop_after_shot_rpm: float = 0.0
    recovery_time_sec: float = 0.0

    # Computed — current
    spinup_peak_current_a: float = 0.0
    holding_current_a: float = 0.0

    # Weight
    wheel_weight_lb: float = 0.0
    motor_weight_lb: float = 0.0
    total_weight_lb: float = 0.0

    # Software constants
    software_constants: dict = field(default_factory=dict)
    parts_list: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    preset_name: str = ""


# ═══════════════════════════════════════════════════════════════════
# FLYWHEEL MOI ESTIMATOR
# ═══════════════════════════════════════════════════════════════════

def estimate_wheel_moi(diameter_in: float, wheel_count: int) -> float:
    """
    Estimate moment of inertia for FRC shooter wheels.
    Typical FRC shooter wheels: solid polycarb or Colson with steel hub.
    MOI ≈ 0.5 * m * r² for a solid disk.
    """
    radius_m = (diameter_in / 2) * IN_TO_M
    # Typical FRC shooter wheel: ~0.3 lb each
    mass_per_wheel_kg = 0.3 * LB_TO_N / 9.81
    moi_per_wheel = 0.5 * mass_per_wheel_kg * radius_m**2
    return moi_per_wheel * wheel_count


# ═══════════════════════════════════════════════════════════════════
# PHYSICS — From ReCalc flywheel calculator
# ═══════════════════════════════════════════════════════════════════

def calculate_spinup_time(
    motor: DCMotor,
    motor_count: int,
    gear_ratio: float,
    target_rpm: float,
    moi_kg_m2: float,
    current_limit_a: float = 40.0,
    efficiency: float = 0.90,
) -> dict:
    """
    Calculate time to reach target RPM from rest.

    Uses analytical solution of the DC motor first-order ODE:
      J · dω/dt = τ_stall · (1 - ω/ω_free) · N
    Solution: ω(t) = ω_free · (1 - e^(-t/τ_m))
    where τ_m = J · ω_free / (τ_stall · N)

    With current limiting:
      τ_limited = kT · min(I_limit, I_stall) · efficiency
      ω_free_output = ω_free / gear_ratio
    """
    # Current-limited stall torque per motor
    effective_stall_current = min(current_limit_a, motor.stall_current_a)
    tau_limited = motor.kT * effective_stall_current * efficiency

    # Free speed at output shaft
    omega_free_output = motor.free_speed_rads / gear_ratio
    target_omega = target_rpm * RPM_TO_RADS

    if target_omega >= omega_free_output:
        return {"spinup_time_sec": float('inf'), "achievable": False}

    # Motor time constant: τ_m = J · ω_free / (τ · N)
    tau_m = moi_kg_m2 * omega_free_output / (tau_limited * motor_count)

    # Time to reach target: t = -τ_m · ln((ω_free - ω_target) / ω_free)
    spinup_time = -tau_m * math.log((omega_free_output - target_omega) / omega_free_output)

    return {
        "spinup_time_sec": round(spinup_time, 3),
        "achievable": True,
        "tau_m": round(tau_m, 4),
        "omega_free_output_rpm": round(omega_free_output / RPM_TO_RADS, 0),
    }


def calculate_shot_physics(
    target_rpm: float,
    wheel_diameter_in: float,
    moi_kg_m2: float,
    piece_mass_lb: float,
    piece_diameter_in: float,
) -> dict:
    """
    Calculate energy transfer and exit velocity for a shot.

    ReCalc model: inelastic collision between spinning wheel and game piece.
    For a rolling sphere: I = 2/5 · m · r²
    Transfer % = MOI / (7/20 · m · d² + 2 · MOI)
    KE_projectile = 0.7 · m · v²  (translational + rotational)
    """
    omega = target_rpm * RPM_TO_RADS
    wheel_radius_m = (wheel_diameter_in / 2) * IN_TO_M
    piece_mass_kg = piece_mass_lb * LB_TO_N / 9.81
    piece_diameter_m = piece_diameter_in * IN_TO_M

    # Surface speed
    surface_speed_mps = omega * wheel_radius_m
    surface_speed_fps = surface_speed_mps / 0.3048

    # Flywheel stored energy
    ke_flywheel = 0.5 * moi_kg_m2 * omega**2

    # Energy transfer percentage (ReCalc formula)
    transfer = moi_kg_m2 / (0.35 * piece_mass_kg * piece_diameter_m**2 + 2 * moi_kg_m2)

    # Exit velocity
    exit_velocity_mps = surface_speed_mps * transfer
    exit_velocity_fps = exit_velocity_mps / 0.3048

    # Projectile kinetic energy (translational + rotational for rolling sphere)
    ke_projectile = 0.7 * piece_mass_kg * exit_velocity_mps**2

    # Speed after shot (energy conservation)
    ke_remaining = ke_flywheel - ke_projectile
    if ke_remaining > 0:
        omega_after = math.sqrt(2 * ke_remaining / moi_kg_m2)
    else:
        omega_after = 0
    rpm_after = omega_after / RPM_TO_RADS
    speed_drop = target_rpm - rpm_after

    return {
        "surface_speed_fps": round(surface_speed_fps, 1),
        "exit_velocity_fps": round(exit_velocity_fps, 1),
        "energy_transfer_pct": round(transfer * 100, 1),
        "ke_flywheel_j": round(ke_flywheel, 2),
        "ke_projectile_j": round(ke_projectile, 2),
        "rpm_after_shot": round(rpm_after, 0),
        "speed_drop_rpm": round(speed_drop, 0),
    }


def calculate_recovery_time(
    motor: DCMotor,
    motor_count: int,
    gear_ratio: float,
    target_rpm: float,
    rpm_after_shot: float,
    moi_kg_m2: float,
    current_limit_a: float = 40.0,
    efficiency: float = 0.90,
    recovery_pct: float = 0.95,
) -> float:
    """
    Time to recover from post-shot RPM back to recovery_pct of target RPM.
    Same analytical model as spinup, but starting from rpm_after_shot.
    """
    effective_stall_current = min(current_limit_a, motor.stall_current_a)
    tau_limited = motor.kT * effective_stall_current * efficiency
    omega_free_output = motor.free_speed_rads / gear_ratio

    target_omega = target_rpm * recovery_pct * RPM_TO_RADS
    omega_after = rpm_after_shot * RPM_TO_RADS

    if omega_free_output <= target_omega or omega_free_output <= omega_after:
        return float('inf')

    tau_m = moi_kg_m2 * omega_free_output / (tau_limited * motor_count)

    recovery_time = -tau_m * math.log(
        (omega_free_output - target_omega) / (omega_free_output - omega_after)
    )
    return round(max(0, recovery_time), 3)


# ═══════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_flywheel(
    wheel_diameter_in: float = 4.0,
    wheel_count: int = 2,
    motor_type: str = "neo_vortex",
    motor_count: int = 2,
    gear_ratio: float = 1.0,
    target_rpm: float = 3000.0,
    current_limit_a: float = 40.0,
    efficiency: float = 0.90,
    piece_mass_lb: float = 0.5,
    piece_diameter_in: float = 4.5,
    moi_override: Optional[float] = None,
    preset_name: str = "",
) -> FlywheelSpec:
    """Generate a complete flywheel/shooter specification."""
    if motor_type not in MOTOR_DB:
        raise ValueError(f"Unknown motor: {motor_type}. Options: {list(MOTOR_DB.keys())}")

    dc_motor = MOTOR_DB[motor_type]
    motor_info = {"name": dc_motor.name, "controller": dc_motor.controller, "weight_lb": dc_motor.weight_lb}

    spec = FlywheelSpec(
        wheel_diameter_in=wheel_diameter_in,
        wheel_count=wheel_count,
        motor_type=motor_type,
        motor_count=motor_count,
        gear_ratio=gear_ratio,
        target_rpm=target_rpm,
        current_limit_a=current_limit_a,
        efficiency=efficiency,
        piece_mass_lb=piece_mass_lb,
        piece_diameter_in=piece_diameter_in,
        preset_name=preset_name,
    )

    # MOI
    spec.wheel_moi_kg_m2 = moi_override if moi_override else estimate_wheel_moi(wheel_diameter_in, wheel_count)

    # Spinup
    spinup = calculate_spinup_time(
        dc_motor, motor_count, gear_ratio, target_rpm, spec.wheel_moi_kg_m2,
        current_limit_a, efficiency,
    )
    spec.spinup_time_sec = spinup["spinup_time_sec"]

    # Shot physics
    shot = calculate_shot_physics(
        target_rpm, wheel_diameter_in, spec.wheel_moi_kg_m2,
        piece_mass_lb, piece_diameter_in,
    )
    spec.surface_speed_fps = shot["surface_speed_fps"]
    spec.exit_velocity_fps = shot["exit_velocity_fps"]
    spec.energy_transfer_pct = shot["energy_transfer_pct"]
    spec.stored_energy_j = shot["ke_flywheel_j"]
    spec.speed_drop_after_shot_rpm = shot["speed_drop_rpm"]

    # Recovery
    spec.recovery_time_sec = calculate_recovery_time(
        dc_motor, motor_count, gear_ratio, target_rpm, shot["rpm_after_shot"],
        spec.wheel_moi_kg_m2, current_limit_a, efficiency,
    )

    # Current
    spec.spinup_peak_current_a = min(current_limit_a, dc_motor.stall_current_a)
    # Holding current: at target speed, flywheel only needs to overcome friction (b·ω)
    # This is approximately the free current scaled by speed ratio
    target_omega_motor = target_rpm * RPM_TO_RADS / gear_ratio
    friction_torque = dc_motor.b * target_omega_motor
    spec.holding_current_a = round(friction_torque / dc_motor.kT + dc_motor.free_current_a, 1)

    # Weight
    spec.wheel_weight_lb = round(0.3 * wheel_count, 2)  # ~0.3 lb per wheel
    spec.motor_weight_lb = round(dc_motor.weight_lb * motor_count, 2)
    spec.total_weight_lb = round(spec.wheel_weight_lb + spec.motor_weight_lb + 1.5, 2)  # +1.5 for housing/shaft/bearings

    # Software constants
    spec.software_constants = {
        "FLYWHEEL_GEAR_RATIO": gear_ratio,
        "FLYWHEEL_MOTOR_COUNT": motor_count,
        "TARGET_RPM": target_rpm,
        "WHEEL_DIAMETER_IN": wheel_diameter_in,
        "CURRENT_LIMIT_A": current_limit_a,
        "kS": 0.1,  # static friction — tune on hardware
        "kV": round(V_NOMINAL / (dc_motor.free_speed_rads / gear_ratio / RPM_TO_RADS), 5),
        "kA": 0.01,
        "RPM_TOLERANCE": round(target_rpm * 0.03, 0),  # 3% tolerance
        "RECOVERY_TIME_SEC": spec.recovery_time_sec,
    }

    # Notes
    spec.notes = []
    if spec.spinup_time_sec > 2.0:
        spec.notes.append("WARNING: Spinup > 2s — consider higher gear ratio or more motors")
    if spec.recovery_time_sec > 0.5:
        spec.notes.append("WARNING: Recovery > 0.5s — may limit rapid-fire cycles")
    if spec.energy_transfer_pct < 30:
        spec.notes.append("Low energy transfer — increase flywheel MOI (heavier wheels)")
    if spec.energy_transfer_pct > 70:
        spec.notes.append("High energy transfer — good for consistent shots")

    # Parts list
    spec.parts_list = [
        {"qty": wheel_count, "item": f"{wheel_diameter_in}\" shooter wheel", "notes": "Colson or polycarb, balanced"},
        {"qty": motor_count, "item": f"{dc_motor.name} motor", "notes": f"With {dc_motor.controller}"},
        {"qty": 1, "item": "Flywheel shaft (1/2\" hex)", "notes": f"Length = wheel stack + bearings"},
        {"qty": 2, "item": "Flanged bearing (1/2\" hex bore)", "notes": "One per shaft end"},
        {"qty": 1, "item": "Flywheel housing plates (2x)", "notes": "1/4\" aluminum or polycarb"},
        {"qty": 1, "item": "Hardware assortment (#10-32)", "notes": "Bolts, nuts, spacers"},
    ]
    if gear_ratio != 1.0:
        spec.parts_list.insert(2, {
            "qty": 1, "item": f"Belt/gear reduction ({gear_ratio}:1)",
            "notes": "HTD5 belt or gear mesh",
        })

    return spec


# ═══════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════

PRESETS = {
    "coral_2026": {
        "description": "Dual Vortex shooter for 2026 Coral game piece",
        "params": {
            "wheel_diameter_in": 4.0,
            "wheel_count": 2,
            "motor_type": "neo_vortex",
            "motor_count": 2,
            "gear_ratio": 1.0,
            "target_rpm": 3000.0,
            "piece_mass_lb": 0.5,
            "piece_diameter_in": 4.5,
        },
    },
    "close_range": {
        "description": "Low-RPM close-range shooter",
        "params": {
            "wheel_diameter_in": 4.0,
            "wheel_count": 2,
            "motor_type": "neo",
            "motor_count": 2,
            "gear_ratio": 1.5,
            "target_rpm": 2000.0,
            "piece_mass_lb": 0.5,
            "piece_diameter_in": 4.5,
        },
    },
    "long_range": {
        "description": "High-RPM long-range shooter with Krakens",
        "params": {
            "wheel_diameter_in": 4.0,
            "wheel_count": 2,
            "motor_type": "kraken_x60",
            "motor_count": 2,
            "gear_ratio": 0.75,
            "target_rpm": 4500.0,
            "piece_mass_lb": 0.5,
            "piece_diameter_in": 4.5,
        },
    },
    "ball_shooter": {
        "description": "Cargo-style ball shooter (9.5\" sphere)",
        "params": {
            "wheel_diameter_in": 6.0,
            "wheel_count": 2,
            "motor_type": "neo_vortex",
            "motor_count": 2,
            "gear_ratio": 1.0,
            "target_rpm": 3500.0,
            "piece_mass_lb": 0.6,
            "piece_diameter_in": 9.5,
        },
    },
}


# ═══════════════════════════════════════════════════════════════════
# DISPLAY + CLI
# ═══════════════════════════════════════════════════════════════════

def display_spec(spec: FlywheelSpec):
    motor = MOTOR_DB[spec.motor_type]
    title = f"2950 {spec.preset_name.replace('_', ' ').title()} Flywheel" if spec.preset_name else "2950 Custom Flywheel"
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"  Generated by The Blueprint B.4")
    print(f"{'═' * 60}")

    print(f"\n  CONFIGURATION")
    print(f"    Wheels:            {spec.wheel_count}x {spec.wheel_diameter_in}\" shooter wheel")
    print(f"    Motors:            {spec.motor_count}x {motor.name}")
    print(f"    Gear ratio:        {spec.gear_ratio}:1")
    print(f"    Target RPM:        {spec.target_rpm}")
    print(f"    Game piece:        {spec.piece_mass_lb} lb, {spec.piece_diameter_in}\" dia")

    print(f"\n  PERFORMANCE (simulated with {spec.current_limit_a}A limit, {int(spec.efficiency*100)}% efficiency)")
    print(f"    Spinup time:       {spec.spinup_time_sec}s (0 → {spec.target_rpm} RPM)")
    print(f"    Surface speed:     {spec.surface_speed_fps} fps")
    print(f"    Exit velocity:     {spec.exit_velocity_fps} fps")
    print(f"    Energy transfer:   {spec.energy_transfer_pct}%")
    print(f"    Stored energy:     {spec.stored_energy_j} J")
    print(f"    Speed drop/shot:   {spec.speed_drop_after_shot_rpm} RPM")
    print(f"    Recovery time:     {spec.recovery_time_sec}s (to 95% of target)")

    print(f"\n  CURRENT DRAW")
    print(f"    Peak (spinup):     {spec.spinup_peak_current_a}A per motor")
    print(f"    Holding (at RPM):  {spec.holding_current_a}A per motor")

    print(f"\n  WEIGHT")
    print(f"    Wheels:            {spec.wheel_weight_lb} lb")
    print(f"    Motors:            {spec.motor_weight_lb} lb")
    print(f"    Housing + shaft:   1.5 lb")
    print(f"    TOTAL:             {spec.total_weight_lb} lb")

    print(f"\n  SOFTWARE CONSTANTS (paste into Java)")
    print(f"    ```java")
    for key, val in spec.software_constants.items():
        if isinstance(val, float):
            print(f"    public static final double {key} = {val};")
        else:
            print(f"    public static final int {key} = {val};")
    print(f"    ```")

    if spec.notes:
        print(f"\n  NOTES")
        for n in spec.notes:
            print(f"    • {n}")

    print(f"\n  PARTS LIST")
    for p in spec.parts_list:
        print(f"    {p['qty']}x  {p['item']} — {p['notes']}")
    print(f"\n{'═' * 60}\n")


def save_spec(spec: FlywheelSpec, filename=None):
    if filename is None:
        name = spec.preset_name or "custom"
        filename = f"2950_{name}_flywheel_spec.json"
    filepath = BASE_DIR / filename
    with open(filepath, "w") as f:
        json.dump(asdict(spec), f, indent=2)
    print(f"Spec saved to: {filepath}")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  python3 flywheel_generator.py generate --preset coral_2026")
        print("  python3 flywheel_generator.py generate --target-rpm 3000 --motor neo_vortex")
        print("  python3 flywheel_generator.py presets")
        return

    if args[0] == "presets":
        print("Available presets:")
        for name, p in PRESETS.items():
            print(f"  {name:20s} {p['description']}")
        return

    if args[0] == "generate":
        preset_name = None
        params = {}
        i = 1
        while i < len(args):
            if args[i] == "--preset" and i + 1 < len(args):
                preset_name = args[i + 1]; i += 2
            elif args[i] == "--target-rpm" and i + 1 < len(args):
                params["target_rpm"] = float(args[i + 1]); i += 2
            elif args[i] == "--motor" and i + 1 < len(args):
                params["motor_type"] = args[i + 1]; i += 2
            elif args[i] == "--motors" and i + 1 < len(args):
                params["motor_count"] = int(args[i + 1]); i += 2
            elif args[i] == "--ratio" and i + 1 < len(args):
                params["gear_ratio"] = float(args[i + 1]); i += 2
            elif args[i] == "--wheel-diameter" and i + 1 < len(args):
                params["wheel_diameter_in"] = float(args[i + 1]); i += 2
            elif args[i] == "--current-limit" and i + 1 < len(args):
                params["current_limit_a"] = float(args[i + 1]); i += 2
            else:
                print(f"Unknown arg: {args[i]}"); return

        if preset_name:
            if preset_name not in PRESETS:
                print(f"Unknown preset: {preset_name}"); return
            p = PRESETS[preset_name]["params"].copy()
            p.update(params)
            spec = generate_flywheel(**p, preset_name=preset_name)
        else:
            spec = generate_flywheel(**params)

        display_spec(spec)
        save_spec(spec)


if __name__ == "__main__":
    main()
