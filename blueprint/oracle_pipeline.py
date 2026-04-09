"""
The Blueprint — Oracle → Full Blueprint Pipeline (B.9)
Team 2950 — The Devastators

Takes an Oracle prediction output (from prediction_bridge.py) and
automatically generates ALL mechanism specs + BOM rollup in one shot.

This is the kickoff-day workflow:
  1. Oracle predicts game → OracleOutput JSON
  2. This pipeline maps predictions → generator presets/params
  3. Runs all generators → individual specs
  4. Runs BOM rollup → full robot spec
  5. Outputs complete Blueprint package

Usage:
  python3 oracle_pipeline.py run <oracle_output.json>
  python3 oracle_pipeline.py run --example
  python3 oracle_pipeline.py dry-run <oracle_output.json>
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from prediction_bridge import (
    OracleOutput, parse_oracle_output,
    DrivetrainSpec, IntakeSpec as OracleIntakeSpec, ScorerSpec, EndgameSpec,
)
from motor_model import MOTOR_DB

# Mechanism generators
from elevator_generator import generate_elevator, ElevatorSpec
from intake_generator import generate_intake, IntakeSpec as MechIntakeSpec
from flywheel_generator import generate_flywheel, FlywheelSpec
from arm_generator import generate_arm, ArmSpec
from climber_generator import generate_climber, ClimberSpec
from conveyor_generator import generate_conveyor, ConveyorSpec
from bom_rollup import rollup_robot, display_rollup, BOMRollup

BASE_DIR = Path(__file__).parent


@dataclass
class PipelineResult:
    """Complete output of the Oracle → Blueprint pipeline."""
    oracle: dict = field(default_factory=dict)
    specs: dict = field(default_factory=dict)
    bom: dict = field(default_factory=dict)
    generation_log: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# MAPPING — Oracle predictions → generator parameters
# ═══════════════════════════════════════════════════════════════════

def map_scorer_to_generators(scorer: ScorerSpec, drivetrain_speed_fps: float) -> dict:
    """Map Oracle scorer prediction to elevator/flywheel/arm generator params."""
    result = {}

    if scorer.method == "elevator":
        # Map height to elevator params
        height = scorer.height_in
        if height <= 0:
            height = 48.0  # default mid-height

        # Motor selection based on Oracle motor count
        motor = "kraken_x60" if scorer.motors >= 2 else "neo"
        motor_count = max(1, scorer.motors)

        result["elevator"] = {
            "travel_height_in": height,
            "end_effector_weight_lb": 8.0,
            "motor_type": motor,
            "motor_count": motor_count,
            "current_limit_a": 40.0,
        }

        # If scorer has wrist, add arm for end effector
        if scorer.has_wrist:
            result["arm"] = {
                "arm_length_in": 8.0,
                "com_distance_in": 4.0,
                "arm_mass_lb": 1.5,
                "end_effector_weight_lb": 2.0,
                "motor_type": "neo_550",
                "motor_count": 1,
                "gear_ratio": 50.0,
                "start_angle_deg": -45.0,
                "end_angle_deg": 90.0,
            }

    elif scorer.method == "flywheel":
        # Flywheel shooter
        motor = "neo_vortex"
        motor_count = max(2, scorer.motors)

        result["flywheel"] = {
            "wheel_diameter_in": 4.0,
            "wheel_count": 2,
            "motor_type": motor,
            "motor_count": motor_count,
            "gear_ratio": 1.0,
            "target_rpm": 3000.0,
            "piece_mass_lb": 0.5,
            "piece_diameter_in": 4.5,
        }

    elif scorer.method == "gravity_drop":
        # Simple elevator to height, no shooter needed
        height = scorer.height_in if scorer.height_in > 0 else 36.0
        result["elevator"] = {
            "travel_height_in": height,
            "end_effector_weight_lb": 5.0,
            "motor_type": "neo",
            "motor_count": 1,
            "current_limit_a": 40.0,
        }

    return result


def map_intake_to_generator(intake: OracleIntakeSpec, drivetrain_speed_fps: float) -> dict:
    """Map Oracle intake prediction to intake generator params."""
    # Map roller material
    material_map = {
        "flex_wheels": "flex_wheels",
        "compliant_wheels": "compliant_wheels",
        "silicone_foam": "compliant_wheels",
        "mecanum": "flex_wheels",
        "green_wheels": "green_wheels",
    }
    roller_material = material_map.get(intake.roller_material, "flex_wheels")

    # Map intake type
    intake_type = intake.type if intake.type in ("over_bumper", "under_bumper", "fixed_full_width") else "over_bumper"

    # Motor type: use NEO for most, Kraken for competition
    motor_type = "neo"

    return {
        "intake_type": intake_type,
        "game_piece_diameter_in": 4.5,  # default, override from game rules
        "roller_material": roller_material,
        "roller_motor_type": motor_type,
        "drivetrain_speed_fps": drivetrain_speed_fps,
    }


def map_endgame_to_generator(endgame: EndgameSpec) -> Optional[dict]:
    """Map Oracle endgame prediction to climber generator params."""
    if endgame.type in ("none", "park_only"):
        return None

    style_map = {
        "hook_winch": "winch",
        "telescope": "telescope",
    }
    climb_style = style_map.get(endgame.type, "winch")

    motor_count = max(1, endgame.motors)
    height = endgame.height_in if endgame.height_in > 0 else 26.0

    return {
        "climb_height_in": height,
        "robot_weight_lb": 125.0,
        "climb_style": climb_style,
        "motor_type": "neo",
        "motor_count": motor_count,
        "gear_ratio": 50.0,
        "spool_diameter_in": 1.0,
    }


# ═══════════════════════════════════════════════════════════════════
# PIPELINE — Oracle → All Specs → BOM
# ═══════════════════════════════════════════════════════════════════

def run_pipeline(oracle_output: OracleOutput) -> PipelineResult:
    """Run the full Oracle → Blueprint pipeline."""
    result = PipelineResult()
    result.oracle = asdict(oracle_output)
    log = result.generation_log

    drivetrain_speed = oracle_output.drivetrain.speed_fps

    # ── Intake ──
    try:
        intake_params = map_intake_to_generator(oracle_output.intake, drivetrain_speed)
        intake_spec = generate_intake(**intake_params, preset_name="oracle_generated")
        result.specs["intake"] = asdict(intake_spec)
        log.append(f"[OK] Intake: {intake_spec.intake_type}, {intake_spec.surface_speed_fps} fps, {intake_spec.total_weight_lb} lb")
    except Exception as e:
        log.append(f"[FAIL] Intake: {e}")

    # ── Scorer (elevator/flywheel/arm) ──
    scorer_params = map_scorer_to_generators(oracle_output.scorer, drivetrain_speed)

    if "elevator" in scorer_params:
        try:
            elev_spec = generate_elevator(**scorer_params["elevator"], name="2950 Oracle Elevator")
            result.specs["elevator"] = asdict(elev_spec)
            log.append(f"[OK] Elevator: {elev_spec.travel_height_in}\" travel, {elev_spec.full_travel_time_sec}s, {elev_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Elevator: {e}")

    if "flywheel" in scorer_params:
        try:
            fw_spec = generate_flywheel(**scorer_params["flywheel"], preset_name="oracle_generated")
            result.specs["flywheel"] = asdict(fw_spec)
            log.append(f"[OK] Flywheel: {fw_spec.target_rpm} RPM, {fw_spec.exit_velocity_fps} fps, {fw_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Flywheel: {e}")

    if "arm" in scorer_params:
        try:
            arm_spec = generate_arm(**scorer_params["arm"], preset_name="oracle_wrist")
            result.specs["arm"] = asdict(arm_spec)
            log.append(f"[OK] Arm (wrist): {arm_spec.travel_time_sec}s, {arm_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Arm: {e}")

    # ── Conveyor (always include if there's an intake + scorer) ──
    if "intake" in result.specs and ("elevator" in result.specs or "flywheel" in result.specs):
        try:
            conv_spec = generate_conveyor(
                path_length_in=18.0, game_piece_diameter_in=4.5,
                staging_count=1, preset_name="oracle_generated",
            )
            result.specs["conveyor"] = asdict(conv_spec)
            log.append(f"[OK] Conveyor: {conv_spec.transit_time_sec}s transit, {conv_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Conveyor: {e}")

    # ── Endgame (climber) ──
    climber_params = map_endgame_to_generator(oracle_output.endgame)
    if climber_params:
        try:
            climb_spec = generate_climber(**climber_params, preset_name="oracle_generated")
            result.specs["climber"] = asdict(climb_spec)
            log.append(f"[OK] Climber: {climb_spec.climb_time_sec}s, safety {climb_spec.safety_factor}x, {climb_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Climber: {e}")

    # ── Weight check ──
    total_mechanism_weight = sum(
        spec.get("total_weight_lb", 0) for spec in result.specs.values()
    )
    drivetrain_weight = oracle_output.weight_budget.get("drivetrain_lb", 45)
    bumper_weight = oracle_output.weight_budget.get("bumpers_lb", 10)
    battery_weight = 13.0
    electronics_weight = oracle_output.weight_budget.get("electronics_lb", 15)
    total = total_mechanism_weight + drivetrain_weight + bumper_weight + battery_weight + electronics_weight
    margin = 125.0 - total

    result.bom = {
        "mechanism_weight_lb": round(total_mechanism_weight, 2),
        "drivetrain_weight_lb": drivetrain_weight,
        "bumper_weight_lb": bumper_weight,
        "battery_weight_lb": battery_weight,
        "electronics_weight_lb": electronics_weight,
        "total_weight_lb": round(total, 2),
        "margin_lb": round(margin, 2),
        "weight_ok": margin >= 0,
    }

    if margin < 0:
        log.append(f"[WARN] OVERWEIGHT by {abs(margin):.1f} lb")
    elif margin < 5:
        log.append(f"[WARN] Tight weight margin: {margin:.1f} lb")
    else:
        log.append(f"[OK] Weight: {total:.1f} lb, margin {margin:.1f} lb")

    return result


def display_pipeline_result(result: PipelineResult):
    """Display the pipeline result in a readable format."""
    oracle = result.oracle
    print(f"\n{'═' * 65}")
    print(f"  2950 ORACLE → BLUEPRINT PIPELINE")
    print(f"  {oracle.get('game_name', 'Unknown Game')} ({oracle.get('season_year', '???')})")
    print(f"  Confidence: {oracle.get('confidence_overall', 0)*100:.0f}%")
    print(f"  Generated by The Blueprint B.9")
    print(f"{'═' * 65}")

    print(f"\n  GENERATION LOG")
    for entry in result.generation_log:
        print(f"    {entry}")

    print(f"\n  MECHANISMS GENERATED: {len(result.specs)}")
    for name, spec in result.specs.items():
        weight = spec.get("total_weight_lb", "?")
        print(f"    {name.capitalize():20s} {weight} lb")

    bom = result.bom
    weight_status = "[PASS]" if bom.get("weight_ok", False) else "[OVERWEIGHT]"
    print(f"\n  WEIGHT SUMMARY")
    print(f"    Mechanisms:        {bom['mechanism_weight_lb']} lb")
    print(f"    Drivetrain:        {bom['drivetrain_weight_lb']} lb")
    print(f"    Bumpers:           {bom['bumper_weight_lb']} lb")
    print(f"    Battery:           {bom['battery_weight_lb']} lb")
    print(f"    Electronics:       {bom['electronics_weight_lb']} lb")
    print(f"    {'─' * 35}")
    print(f"    TOTAL:             {bom['total_weight_lb']} lb {weight_status}")
    print(f"    MARGIN:            {bom['margin_lb']} lb")

    print(f"\n{'═' * 65}\n")


# ═══════════════════════════════════════════════════════════════════
# EXAMPLE — 2026 REBUILT game prediction
# ═══════════════════════════════════════════════════════════════════

EXAMPLE_ORACLE = {
    "game_name": "REEFSCAPE",
    "season_year": 2025,
    "confidence_overall": 0.92,
    "drivetrain": {
        "type": "swerve",
        "module": "thrifty",
        "speed_fps": 14.5,
        "gear_for": "acceleration",
        "frame_length_in": 28.0,
        "frame_width_in": 28.0,
        "reasoning": "R1: Swerve is mandatory. Thrifty module for cost-effectiveness.",
    },
    "intake": {
        "type": "over_bumper",
        "width": "full",
        "roller_material": "flex_wheels",
        "deploy": True,
        "motors": 2,
        "game_piece": "coral (4.5\" cylindrical tube)",
        "reasoning": "R2: Full-width bumper-to-bumper. R3: Flex wheels for cylindrical game piece.",
    },
    "scorer": {
        "method": "elevator",
        "height_in": 72.0,
        "stages": 2,
        "motors": 2,
        "has_wrist": True,
        "turret": "none",
        "reasoning": "R4: Elevator for multi-height scoring. R5: 2 stages for 72\". R6: No turret (fixed targets).",
    },
    "endgame": {
        "type": "hook_winch",
        "height_in": 26.0,
        "motors": 2,
        "reasoning": "R7: Climb is high-value. Winch for reliability.",
    },
    "autonomous": {
        "priority_actions": ["score_preload", "intake_nearby", "score_second", "intake_far", "score_third"],
        "cycle_time_target_s": 4.5,
        "preload_score": True,
        "estimated_pieces": 3,
        "reasoning": "R8: 3-piece auto minimum for Einstein. R11: 4.5s cycle for competitive advantage.",
    },
    "weight_budget": {
        "drivetrain_lb": 42,
        "intake_lb": 10,
        "scorer_lb": 22,
        "endgame_lb": 8,
        "electronics_lb": 15,
        "bumpers_lb": 10,
        "margin_lb": 18,
        "total_limit_lb": 125,
    },
    "build_order": ["drivetrain", "intake", "scorer", "autonomous", "endgame"],
    "notes": "Prioritize cycle speed. Elevator + wrist for L1-L4 scoring flexibility.",
}


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python3 oracle_pipeline.py run --example")
        print("  python3 oracle_pipeline.py run <oracle_output.json>")
        print("  python3 oracle_pipeline.py dry-run <oracle_output.json>")
        return

    if args[0] in ("run", "dry-run"):
        # Load oracle output
        if len(args) > 1 and args[1] == "--example":
            oracle_data = EXAMPLE_ORACLE
        elif len(args) > 1:
            filepath = Path(args[1])
            if not filepath.exists():
                print(f"File not found: {filepath}")
                return
            with open(filepath) as f:
                oracle_data = json.load(f)
        else:
            oracle_data = EXAMPLE_ORACLE

        oracle = parse_oracle_output(oracle_data)

        if args[0] == "dry-run":
            print("DRY RUN — showing what would be generated:")
            print(f"  Game: {oracle.game_name} ({oracle.season_year})")
            print(f"  Scorer: {oracle.scorer.method}" +
                  (f" ({oracle.scorer.height_in}\")" if oracle.scorer.height_in else ""))
            print(f"  Intake: {oracle.intake.type}, {oracle.intake.roller_material}")
            print(f"  Endgame: {oracle.endgame.type}" +
                  (f" ({oracle.endgame.height_in}\")" if oracle.endgame.height_in else ""))
            return

        result = run_pipeline(oracle)
        display_pipeline_result(result)

        # Save
        filepath = BASE_DIR / "2950_oracle_pipeline_output.json"
        with open(filepath, "w") as f:
            json.dump({
                "oracle_input": result.oracle,
                "specs": result.specs,
                "bom": result.bom,
                "log": result.generation_log,
            }, f, indent=2)
        print(f"Pipeline output saved to: {filepath}")


if __name__ == "__main__":
    main()
