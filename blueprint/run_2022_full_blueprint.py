#!/usr/bin/env python3
"""
Full Blueprint Output — 2022 Rapid React
Oracle prediction → every generator → complete robot spec + BOM

This is what Team 2950 would get on kickoff day 2022 if they had The Engine.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add blueprint dir to path
sys.path.insert(0, str(Path(__file__).parent))

from frame_generator import generate_frame, print_summary as print_frame
from intake_generator import generate_intake, display_spec as display_intake
from flywheel_generator import generate_flywheel, display_spec as display_flywheel
from conveyor_generator import generate_conveyor, display_spec as display_conveyor
from climber_generator import generate_climber, display_spec as display_climber
from bom_rollup import BOMRollup, MotorAllocation, display_rollup, MAX_ROBOT_WEIGHT_LB, MOTOR_DB


def main():
    print("=" * 70)
    print("  THE ENGINE — FULL BLUEPRINT OUTPUT")
    print("  FRC 2022: RAPID REACT")
    print("  Generated from Oracle prediction using ONLY the game manual")
    print("  Rules applied: CROSS_SEASON_PATTERNS R1-R19")
    print("=" * 70)

    # ══════════════════════════════════════════════════════════════
    # B.2 — FRAME (Swerve Drivebase)
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.2 — SWERVE DRIVEBASE")
    print("  R1: Swerve is mandatory (2022 is deep swerve era)")
    print("  SDS MK4i L2, 16 fps top speed")
    print("▓" * 70)

    frame = generate_frame(
        frame_length_in=27.0,
        frame_width_in=27.0,
        perimeter_tube="2x1",
        cross_tube="1x1",
        module_type="sds_mk4i",
        module_inset_in=2.75,
        bellypan=True,
        name="2950 Rapid React Frame",
    )
    print_frame(frame)

    # ══════════════════════════════════════════════════════════════
    # B.3 — INTAKE (Over-Bumper for 9.5" CARGO)
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.3 — INTAKE")
    print("  R5: 9.5\" inflated ball (0.59 lb), fuzzy surface")
    print("  R10: Full-width over-bumper, compliant wheels for grip")
    print("  R2: Bumper-to-bumper capture zone")
    print("▓" * 70)

    intake = generate_intake(
        intake_type="over_bumper",
        game_piece_diameter_in=9.5,
        game_piece_shape="sphere",
        frame_width_in=27.0,  # match frame
        roller_material="compliant_wheels",
        roller_motor_type="neo",
        drivetrain_speed_fps=16.0,  # match swerve speed
        preset_name="2022_cargo",
    )
    display_intake(intake)

    # ══════════════════════════════════════════════════════════════
    # B.4 — FLYWHEEL SHOOTER (Upper Hub at 8'8")
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.4 — FLYWHEEL SHOOTER")
    print("  R4+R19: Cargo scoring is UNCAPPED — primary differentiator")
    print("  R6: Upper Hub at 8'8\" with 4' opening, 360° reflective tape")
    print("  Target: variable-distance shooting (fender to midfield)")
    print("▓" * 70)

    # 2022 CARGO: 9.5" diameter, 9.5 oz (0.59 lb), inflated fuzzy ball
    # Upper Hub at 8'8" (264 cm) — need ~35-50 fps exit velocity
    # Bigger wheels (6") for better contact with 9.5" ball
    # Higher RPM for the height needed
    flywheel = generate_flywheel(
        wheel_diameter_in=6.0,      # larger wheels for 9.5" ball
        wheel_count=2,
        motor_type="neo_vortex",
        motor_count=2,
        gear_ratio=1.0,             # direct drive for max RPM
        target_rpm=4000.0,          # higher RPM for 8'8" target
        current_limit_a=40.0,
        efficiency=0.90,
        piece_mass_lb=0.59,         # 9.5 oz CARGO
        piece_diameter_in=9.5,      # actual CARGO diameter
        preset_name="2022_upper_hub",
    )
    display_flywheel(flywheel)

    # ══════════════════════════════════════════════════════════════
    # B.7 — CONVEYOR/INDEXER (2-ball capacity)
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.7 — CONVEYOR / INDEXER")
    print("  R12: 2 ball capacity (intake → staging → shooter)")
    print("  Beam break sensors for ball detection and indexing")
    print("▓" * 70)

    # Path from intake to shooter — through belly of robot
    # 9.5" balls need wider path, ~24" total path length
    conveyor = generate_conveyor(
        path_length_in=24.0,        # intake to shooter
        game_piece_diameter_in=9.5,  # CARGO
        staging_count=2,             # hold 2 balls
        belt_type="belt",
        motor_type="neo_550",
        motor_count=1,
        gear_ratio=5.0,
        roller_diameter_in=2.0,
        sensor_type="beam_break",
        sensor_count=3,              # intake, staging, shooter feed
        preset_name="2022_cargo_indexer",
    )
    display_conveyor(conveyor)

    # ══════════════════════════════════════════════════════════════
    # B.6 — CLIMBER (Telescope to Traversal at 7'7")
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.6 — CLIMBER")
    print("  R8: Traversal rung at 7'7\" = 15 pts (highest value)")
    print("  R19: Hangar RP easily achievable, but traversal")
    print("        still worth 15 match points per robot")
    print("  Telescope design: mid rung → high → traversal")
    print("▓" * 70)

    # Traversal is at 7'7" (91") above carpet
    # Robot is ~27" frame + ~4" swerve = ~12" to top of frame
    # Need to reach from ~12" up to 91" = ~79" of reach
    # But hook engages mid rung first at ~60" height
    # Effective climb height from mid to traversal = ~60"
    climber = generate_climber(
        climb_height_in=60.0,       # mid rung to traversal
        robot_weight_lb=125.0,
        climb_style="telescope",
        motor_type="neo",
        motor_count=2,
        gear_ratio=60.0,            # high reduction for heavy lift
        spool_diameter_in=1.25,     # slightly larger spool for speed
        current_limit_a=60.0,       # allow higher current for climb
        efficiency=0.80,
        preset_name="2022_traversal",
    )
    display_climber(climber)

    # ══════════════════════════════════════════════════════════════
    # B.8 — BOM ROLLUP
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  B.8 — FULL ROBOT BOM ROLLUP")
    print("▓" * 70)

    # Build BOM rollup manually from generated specs
    rollup = BOMRollup(
        drivetrain_weight_lb=41.81,  # from frame generator
        bumper_weight_lb=8.0,
    )

    # Register mechanisms
    rollup.mechanisms = {
        "intake": {
            "preset": "2022_cargo",
            "weight_lb": intake.total_weight_lb,
            "motor_type": intake.roller_motor_type,
            "motor_count": intake.roller_motor_count,
            "deploy_motor": intake.deploy_motor_type if intake.deploy_type != "none" else None,
            "current_limit_a": 40.0,
            "peak_current_a": 40.0,
            "holding_current_a": 5.0,
            "parts": intake.parts_list,
            "software_constants": intake.software_constants,
        },
        "flywheel": {
            "preset": "2022_upper_hub",
            "weight_lb": flywheel.total_weight_lb,
            "motor_type": flywheel.motor_type,
            "motor_count": flywheel.motor_count,
            "current_limit_a": flywheel.current_limit_a,
            "peak_current_a": flywheel.spinup_peak_current_a,
            "holding_current_a": flywheel.holding_current_a,
            "parts": flywheel.parts_list,
            "software_constants": flywheel.software_constants,
        },
        "conveyor": {
            "preset": "2022_cargo_indexer",
            "weight_lb": conveyor.total_weight_lb,
            "motor_type": conveyor.motor_type,
            "motor_count": conveyor.motor_count,
            "current_limit_a": conveyor.current_limit_a,
            "peak_current_a": conveyor.current_limit_a,
            "holding_current_a": conveyor.holding_current_a,
            "parts": conveyor.parts_list,
            "software_constants": conveyor.software_constants,
        },
        "climber": {
            "preset": "2022_traversal",
            "weight_lb": climber.total_weight_lb,
            "motor_type": climber.motor_type,
            "motor_count": climber.motor_count,
            "current_limit_a": climber.current_limit_a,
            "peak_current_a": climber.peak_current_a,
            "holding_current_a": climber.holding_current_a,
            "parts": climber.parts_list,
            "software_constants": climber.software_constants,
        },
    }

    # Aggregate weight
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

    # Motor budget — drivetrain + all mechanisms
    rollup.motors = [
        MotorAllocation("drivetrain_drive", "kraken_x60", "Kraken X60", 4, 40.0, 40.0, 5.0),
        MotorAllocation("drivetrain_steer", "neo_550", "NEO 550", 4, 20.0, 20.0, 2.0),
    ]
    for mech_name, mech in rollup.mechanisms.items():
        motor_name = MOTOR_DB[mech["motor_type"]].name if mech["motor_type"] in MOTOR_DB else mech["motor_type"]
        rollup.motors.append(MotorAllocation(
            mechanism=mech_name,
            motor_type=mech["motor_type"],
            motor_name=motor_name,
            count=mech["motor_count"],
            current_limit_a=mech.get("current_limit_a", 40.0),
            peak_current_a=mech.get("peak_current_a", 40.0),
            holding_current_a=mech.get("holding_current_a", 5.0),
        ))
        if mech.get("deploy_motor") and mech["deploy_motor"] != "none":
            dm_name = MOTOR_DB[mech["deploy_motor"]].name if mech["deploy_motor"] in MOTOR_DB else mech["deploy_motor"]
            rollup.motors.append(MotorAllocation(
                mechanism=f"{mech_name}_deploy",
                motor_type=mech["deploy_motor"],
                motor_name=dm_name,
                count=1, current_limit_a=20.0, peak_current_a=20.0, holding_current_a=2.0,
            ))

    rollup.total_motor_count = sum(m.count for m in rollup.motors)
    rollup.total_can_devices = rollup.total_motor_count + 3
    rollup.peak_current_total_a = round(sum(m.peak_current_a * m.count for m in rollup.motors), 1)
    rollup.sustained_current_total_a = round(sum(m.holding_current_a * m.count for m in rollup.motors), 1)

    # Notes
    rollup.notes = []
    if not rollup.weight_ok:
        rollup.notes.append(f"OVERWEIGHT by {abs(rollup.weight_margin_lb)} lb")
    elif rollup.weight_margin_lb < 5:
        rollup.notes.append(f"Tight weight margin ({rollup.weight_margin_lb} lb)")
    else:
        rollup.notes.append(f"Weight margin: {rollup.weight_margin_lb} lb — healthy")

    if rollup.peak_current_total_a > 400:
        rollup.notes.append(f"Peak current ({rollup.peak_current_total_a}A) — battery sag likely under full load")

    display_rollup(rollup)

    # ══════════════════════════════════════════════════════════════
    # AUTONOMOUS STRATEGY
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "▓" * 70)
    print("  AUTONOMOUS STRATEGY")
    print("  R7: Auto scoring doubled (4 pts/upper vs 2 teleop)")
    print("  R18: 2-ball reliable, stretch to 5-ball")
    print("▓" * 70)

    print("""
  PRIMARY AUTO — 2-ball (consistent 10 pts)
    1. Taxi forward from tarmac                          2 pts
    2. Shoot preloaded CARGO into Upper Hub              4 pts
    3. Drive to nearest staged CARGO, intake             —
    4. Return to shooting position, shoot Upper Hub      4 pts
    ─────────────────────────────────────────────────────
    TOTAL:                                               10 pts
    Time budget: ~5s shoot + 3s drive + 2s intake + 5s shoot = 15s ✓

  STRETCH AUTO — 5-ball (22 pts, requires vision + pathing)
    1. Taxi + shoot preload (Upper Hub)                  6 pts
    2. Intake 2 staged CARGO → shoot both Upper Hub      8 pts
    3. Drive to terminal, intake 1 CARGO                 —
    4. Drive back, intake 1 staged CARGO en route        —
    5. Shoot 2 Upper Hub                                 8 pts
    ─────────────────────────────────────────────────────
    TOTAL:                                               22 pts
    Requires: vision tracking, path planning, <3s cycles
""")

    # ══════════════════════════════════════════════════════════════
    # R19 SCORING ANALYSIS
    # ══════════════════════════════════════════════════════════════
    print("▓" * 70)
    print("  R19 — CAPPED vs UNCAPPED SCORING ANALYSIS")
    print("▓" * 70)

    print("""
  ┌─────────────────────┬───────────┬──────────┬──────────┐
  │ Method              │ Type      │ Pts/unit │ Cap      │
  ├─────────────────────┼───────────┼──────────┼──────────┤
  │ Upper Hub (teleop)  │ UNCAPPED  │ 2        │ none     │
  │ Upper Hub (auto)    │ UNCAPPED  │ 4        │ none     │
  │ Lower Hub (teleop)  │ UNCAPPED  │ 1        │ none     │
  │ Hangar (Traversal)  │ SEMI-CAP  │ 15/robot │ 3 robots │
  │ Cargo RP            │ CAPPED    │ binary   │ 20 cargo │
  │ Hangar RP           │ CAPPED    │ binary   │ 16 pts   │
  └─────────────────────┴───────────┴──────────┴──────────┘

  ALLIANCE SATURATION TEST:
    Hangar: 2 robots on High (20) + 1 Traversal (15) = 35 pts
            → Exceeds 16 pt RP threshold with just 2 robots
            → SATURATES — extra climb height has diminishing returns

    Cargo:  UNCAPPED — more balls always means more points
            → 3 robots × 8 cargo/match × 2 pts = 48 pts achievable
            → This is where Einstein alliances separate

  VERDICT: Build a shooter-first robot. Cargo throughput is
           the primary differentiator. Traversal climb is important
           (15 pts) but secondary to shooting capability.
""")

    # ══════════════════════════════════════════════════════════════
    # BUILD ORDER
    # ══════════════════════════════════════════════════════════════
    print("▓" * 70)
    print("  BUILD ORDER (R14 complexity budget)")
    print("▓" * 70)

    print("""
  Week 1:  Swerve drivebase — drive day 1, iterate controls
  Week 2:  Flywheel shooter — accuracy is king, start tuning early
  Week 3:  Intake + conveyor — integrate with shooter for full cycle
  Week 4:  Climber — telescope to traversal, test extensively
  Week 5:  Autonomous — 2-ball first, then stretch to 5-ball
  Week 6:  Integration, driver practice, spare parts
""")

    # ══════════════════════════════════════════════════════════════
    # SAVE COMPLETE OUTPUT
    # ══════════════════════════════════════════════════════════════
    output = {
        "game": "Rapid React",
        "year": 2022,
        "generated_by": "The Engine — Full Blueprint Pipeline",
        "rules_applied": "CROSS_SEASON_PATTERNS R1-R19",
        "frame": asdict(frame),
        "intake": asdict(intake),
        "flywheel": asdict(flywheel),
        "conveyor": asdict(conveyor),
        "climber": asdict(climber),
        "bom_rollup": asdict(rollup),
        "scoring_analysis": {
            "primary_method": "Upper Hub cargo throughput (UNCAPPED)",
            "secondary_method": "Traversal climb (15 pts, SEMI-CAPPED)",
            "rp_strategy": "Cargo RP via alliance shooting, Hangar RP via 2+ climbers",
        },
        "auto_strategy": {
            "primary": "2-ball (10 pts)",
            "stretch": "5-ball (22 pts)",
        },
        "build_order": [
            "Week 1: Swerve drivebase",
            "Week 2: Flywheel shooter",
            "Week 3: Intake + conveyor",
            "Week 4: Climber",
            "Week 5: Autonomous",
            "Week 6: Integration",
        ],
    }

    out_path = Path(__file__).parent / "2022_rapid_react_full_blueprint.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'═' * 70}")
    print(f"  COMPLETE BLUEPRINT SAVED: {out_path.name}")
    print(f"  Total specs generated: 5 (frame + intake + shooter + conveyor + climber)")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
