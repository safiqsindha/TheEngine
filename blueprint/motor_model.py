"""
The Blueprint — DC Motor Physics Model
Team 2950 — The Devastators

Proper DC motor model derived from ReCalc (reca.lc) and 254's approach.
All motor constants are computed from 4 datasheet values:
  - Free speed (RPM at 12V, no load)
  - Stall torque (N·m at 12V, 0 RPM)
  - Stall current (A at 12V, 0 RPM)
  - Free current (A at 12V, free speed)

From these, we derive:
  R  = V_nom / I_stall          (armature resistance)
  kV = ω_free / (V_nom - R·I_free)  (back-EMF constant)
  kT = τ_stall / I_stall        (torque constant)
  b  = kT · I_free / ω_free     (viscous damping)

This enables current-limited torque calculations, efficiency modeling,
and motion profile simulation — matching ReCalc's accuracy.

Motor specs sourced from ReCalc's motor database (April 2026).
"""

import math
from dataclasses import dataclass
from typing import Optional

V_NOMINAL = 12.0  # FRC battery voltage
GRAVITY_MPS2 = 9.80665
LB_TO_N = 4.44822
IN_TO_M = 0.0254
RPM_TO_RADS = 2 * math.pi / 60.0


@dataclass
class DCMotor:
    """
    Physics-accurate DC motor model.
    All constants derived from 4 datasheet values.
    """
    name: str
    free_speed_rpm: float
    stall_torque_nm: float
    stall_current_a: float
    free_current_a: float
    weight_lb: float
    controller: str

    # Derived constants (computed in __post_init__)
    R: float = 0.0          # armature resistance (Ω)
    kV: float = 0.0         # speed constant (rad/s per V)
    kT: float = 0.0         # torque constant (N·m per A)
    b: float = 0.0          # viscous damping (N·m·s/rad)
    free_speed_rads: float = 0.0

    def __post_init__(self):
        self.free_speed_rads = self.free_speed_rpm * RPM_TO_RADS
        self.R = V_NOMINAL / self.stall_current_a
        self.kV = self.free_speed_rads / (V_NOMINAL - self.R * self.free_current_a)
        self.kT = self.stall_torque_nm / self.stall_current_a
        self.b = self.kT * self.free_current_a / self.free_speed_rads

    def torque_at_current(self, current_a: float) -> float:
        """Torque produced at a given current (N·m)."""
        return self.kT * current_a

    def current_at_speed(self, speed_rads: float, voltage: float = V_NOMINAL) -> float:
        """Current draw at a given speed and voltage (A)."""
        back_emf = speed_rads / self.kV
        return (voltage - back_emf) / self.R

    def torque_at_speed(self, speed_rads: float, voltage: float = V_NOMINAL) -> float:
        """Torque available at a given speed (N·m). Full motor curve."""
        current = self.current_at_speed(speed_rads, voltage)
        return self.kT * current - self.b * speed_rads

    def current_limited_torque(self, speed_rads: float, current_limit_a: float,
                                voltage: float = V_NOMINAL) -> float:
        """Torque at speed with current limit applied (N·m)."""
        current = self.current_at_speed(speed_rads, voltage)
        effective_current = min(current, current_limit_a)
        return self.kT * effective_current

    def speed_at_torque(self, torque_nm: float, voltage: float = V_NOMINAL) -> float:
        """Speed at a given torque output (rad/s)."""
        current = torque_nm / self.kT
        back_emf = voltage - current * self.R
        return back_emf * self.kV

    def stall_load_lb(self, gear_ratio: float, spool_radius_m: float,
                       motor_count: int = 1, current_limit_a: Optional[float] = None,
                       efficiency: float = 0.85) -> float:
        """Maximum load the motor(s) can hold at zero speed (lb)."""
        if current_limit_a is not None:
            effective_current = min(self.stall_current_a, current_limit_a)
        else:
            effective_current = self.stall_current_a
        torque_at_output = self.kT * effective_current * motor_count * gear_ratio * efficiency
        force_n = torque_at_output / spool_radius_m
        return force_n / LB_TO_N


# ═══════════════════════════════════════════════════════════════════
# MOTOR DATABASE — Specs from ReCalc (April 2026)
# ═══════════════════════════════════════════════════════════════════

MOTOR_DB = {
    "kraken_x60": DCMotor(
        name="Kraken X60",
        free_speed_rpm=6000,
        stall_torque_nm=7.09,
        stall_current_a=366,
        free_current_a=2.0,
        weight_lb=1.20,
        controller="TalonFX (integrated)",
    ),
    "kraken_x60_foc": DCMotor(
        name="Kraken X60 (FOC)",
        free_speed_rpm=5784,
        stall_torque_nm=9.37,
        stall_current_a=476,
        free_current_a=3.5,
        weight_lb=1.20,
        controller="TalonFX (integrated, FOC)",
    ),
    "neo": DCMotor(
        name="NEO Brushless",
        free_speed_rpm=5676,
        stall_torque_nm=2.6,
        stall_current_a=105,
        free_current_a=1.8,
        weight_lb=0.94,
        controller="SparkMax",
    ),
    "neo_vortex": DCMotor(
        name="NEO Vortex",
        free_speed_rpm=6784,
        stall_torque_nm=3.6,
        stall_current_a=211,
        free_current_a=5.4,
        weight_lb=0.88,
        controller="SparkFlex",
    ),
    "neo_550": DCMotor(
        name="NEO 550",
        free_speed_rpm=11000,
        stall_torque_nm=0.97,
        stall_current_a=100,
        free_current_a=1.1,
        weight_lb=0.49,
        controller="SparkMax",
    ),
    "falcon_500": DCMotor(
        name="Falcon 500",
        free_speed_rpm=6380,
        stall_torque_nm=4.69,
        stall_current_a=257,
        free_current_a=1.5,
        weight_lb=1.10,
        controller="TalonFX (integrated)",
    ),
    "falcon_500_foc": DCMotor(
        name="Falcon 500 (FOC)",
        free_speed_rpm=6080,
        stall_torque_nm=5.84,
        stall_current_a=304,
        free_current_a=1.5,
        weight_lb=1.10,
        controller="TalonFX (integrated, FOC)",
    ),
}


# ═══════════════════════════════════════════════════════════════════
# MOTION PROFILE SIMULATOR
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MotionProfileResult:
    """Result of a linear mechanism motion profile simulation."""
    travel_time_sec: float
    max_velocity_mps: float
    max_acceleration_mps2: float
    peak_current_a: float
    time_steps: list  # [(t, pos, vel, current), ...]
    stall_load_lb: float


def simulate_linear_motion(
    motor: DCMotor,
    motor_count: int,
    gear_ratio: float,
    spool_diameter_in: float,
    load_lb: float,
    travel_distance_in: float,
    current_limit_a: float = 40.0,
    efficiency: float = 0.85,
    angle_deg: float = 90.0,
    dt: float = 0.001,
) -> MotionProfileResult:
    """
    Simulate a linear mechanism (elevator/lift) with current limiting.

    Uses forward Euler integration of the DC motor + mechanism equations.
    Matches ReCalc's approach but simplified (no inductance modeling).

    The key equation at each timestep:
      1. Compute current from speed: I = (V - ω/kV) / R
      2. Apply current limit: I_eff = min(I, I_limit)
      3. Compute motor torque: τ = kT · I_eff · N · efficiency
      4. Subtract gravity: τ_net = τ - F_gravity · r_spool / ratio
      5. Compute acceleration: α = τ_net / J_total
      6. Integrate: ω += α·dt, θ += ω·dt

    Returns travel time, velocity profile, peak current.
    """
    spool_radius_m = (spool_diameter_in / 2) * IN_TO_M
    load_kg = load_lb * LB_TO_N / GRAVITY_MPS2
    gravity_force_n = load_kg * GRAVITY_MPS2 * math.sin(math.radians(angle_deg))

    # Gravity torque reflected to motor shaft
    gravity_torque_at_motor = gravity_force_n * spool_radius_m / gear_ratio

    # Load inertia reflected to motor shaft: J = m · r² / G²
    j_load = load_kg * spool_radius_m**2 / gear_ratio**2

    # Motor rotor inertia (from FRC 971, used by ReCalc)
    j_rotor = 0.00005822569  # kg·m²
    j_total = j_load + j_rotor * motor_count

    # Conversion: motor rad/s → linear in/s
    def motor_to_linear(omega_rads):
        return omega_rads * spool_radius_m * gear_ratio / IN_TO_M  # back to inches

    # Wait, let me think about the rigging. For continuous rigging with 2:1,
    # the spool diameter already accounts for it through the pulley size.
    # The caller passes the effective spool diameter (pulley circumference / pi).

    # State
    omega = 0.0  # motor angular velocity (rad/s)
    theta = 0.0  # motor angular position (rad)
    t = 0.0

    # Convert travel distance to motor radians
    linear_per_motor_rad = spool_radius_m  # meters per motor radian at output
    # But we need to account for gear ratio:
    # linear_distance = motor_rads * spool_radius / gear_ratio ... no
    # motor spins → gearbox reduces → spool turns
    # spool_rads = motor_rads / gear_ratio
    # linear_distance = spool_rads * spool_radius = motor_rads * spool_radius / gear_ratio
    travel_distance_m = travel_distance_in * IN_TO_M
    target_motor_rads = travel_distance_m / (spool_radius_m / gear_ratio)
    # Hmm, that gives target_motor_rads = travel_m * gear_ratio / spool_radius
    # which is correct: more gear ratio = more motor turns needed

    steps = []
    max_vel = 0.0
    max_accel = 0.0
    peak_current = 0.0
    prev_vel = 0.0

    max_steps = int(30.0 / dt)  # 30 second timeout

    for step_i in range(max_steps):
        # Linear position and velocity
        linear_pos_in = (theta / gear_ratio) * spool_radius_m / IN_TO_M
        linear_vel_in_s = (omega / gear_ratio) * spool_radius_m / IN_TO_M

        # Record
        current_draw = motor.current_at_speed(omega)
        effective_current = min(max(current_draw, 0), current_limit_a)

        if step_i % 10 == 0:  # sample every 10 steps
            steps.append((round(t, 4), round(linear_pos_in, 3), round(linear_vel_in_s, 2), round(effective_current, 1)))

        # Check completion
        if linear_pos_in >= travel_distance_in:
            break

        # Motor torque with current limit and efficiency
        motor_torque = motor.kT * effective_current * motor_count * efficiency

        # Net torque at motor shaft
        net_torque = motor_torque - gravity_torque_at_motor - motor.b * omega

        # Clamp: mechanism can't go backwards
        if net_torque < 0 and omega <= 0:
            net_torque = 0

        # Angular acceleration
        alpha = net_torque / j_total if j_total > 0 else 0

        # Track peaks
        linear_accel = abs(alpha / gear_ratio * spool_radius_m / IN_TO_M)
        if linear_accel > max_accel:
            max_accel = linear_accel
        if abs(linear_vel_in_s) > max_vel:
            max_vel = abs(linear_vel_in_s)
        if effective_current > peak_current:
            peak_current = effective_current

        # Euler integration
        omega = max(0, omega + alpha * dt)
        theta += omega * dt
        t += dt

    # Stall load
    stall = motor.stall_load_lb(gear_ratio, spool_radius_m, motor_count, current_limit_a, efficiency)

    return MotionProfileResult(
        travel_time_sec=round(t, 3),
        max_velocity_mps=round(max_vel * IN_TO_M, 3),
        max_acceleration_mps2=round(max_accel * IN_TO_M, 3),
        peak_current_a=round(peak_current, 1),
        time_steps=steps,
        stall_load_lb=round(stall, 1),
    )


# ═══════════════════════════════════════════════════════════════════
# INTAKE SURFACE SPEED CALCULATOR
# ═══════════════════════════════════════════════════════════════════

def recommend_intake_ratio(
    motor: DCMotor,
    roller_diameter_in: float,
    drivetrain_speed_fps: float,
    speed_multiplier: float = 2.0,
    efficiency: float = 0.85,
) -> dict:
    """
    Recommend intake gear ratio based on drivetrain speed.

    ReCalc/254 principle: intake surface speed should be ~2x robot speed
    so the robot can drive into game pieces and reliably acquire them.

    ratio = (roller_radius · motor_free_speed) / (target_surface_speed)
    target_surface_speed = drivetrain_speed × multiplier
    """
    target_speed_fps = drivetrain_speed_fps * speed_multiplier
    if target_speed_fps <= 0:
        return {"gear_ratio": 1.0, "surface_speed_fps": 0, "target_speed_fps": 0}

    roller_radius_ft = (roller_diameter_in / 2) / 12.0

    # target_surface_speed = roller_radius × motor_speed_at_output
    # motor_speed_at_output = free_speed_rads × efficiency_factor / gear_ratio
    # → gear_ratio = roller_radius × free_speed × efficiency / target_speed_rads
    target_speed_rads = target_speed_fps / roller_radius_ft  # rad/s at roller
    operating_speed = motor.free_speed_rads * 0.80  # 80% loaded operation

    ratio = operating_speed / target_speed_rads

    # Round to nearest 0.5
    ratio = round(ratio * 2) / 2
    ratio = max(1.0, min(100.0, ratio))

    actual_roller_rads = operating_speed / ratio
    actual_speed_fps = actual_roller_rads * roller_radius_ft

    return {
        "gear_ratio": ratio,
        "surface_speed_fps": round(actual_speed_fps, 1),
        "target_speed_fps": round(target_speed_fps, 1),
        "roller_rpm": round(actual_roller_rads / RPM_TO_RADS, 0),
    }
