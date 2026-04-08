"""
The Blueprint — Prediction Bridge (B.1 → B.2+)
Team 2950 — The Devastators

Bridges the Oracle (prediction engine) output to Blueprint input.

On kickoff day, the workflow is:
  1. Fill in KICKOFF_TEMPLATE.md with game rules
  2. Feed template + CROSS_SEASON_PATTERNS.md + TEAM_DATABASE.md to Claude
  3. Claude outputs mechanism recommendations (JSON)
  4. This bridge parses those recommendations into Blueprint parameters
  5. Blueprint generates: frame spec → subsystem assemblies → full robot → BOM

This module handles step 4: parsing Oracle output into structured specs
that the frame_generator and future subsystem generators consume.

Usage:
  python3 prediction_bridge.py parse <oracle_output.json>
  python3 prediction_bridge.py generate <oracle_output.json>
  python3 prediction_bridge.py example
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# ORACLE OUTPUT SCHEMA
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DrivetrainSpec:
    """Drivetrain recommendation from the Oracle."""
    type: str = "swerve"  # Always swerve (R1, 100% confidence)
    module: str = "thrifty"  # swerve module type
    speed_fps: float = 14.5  # target max speed
    gear_for: str = "acceleration"  # "acceleration" or "speed"
    frame_length_in: float = 28.0
    frame_width_in: float = 28.0
    reasoning: str = ""


@dataclass
class IntakeSpec:
    """Intake recommendation from the Oracle."""
    type: str = "over_bumper"  # "over_bumper", "under_bumper", "fixed_full_width"
    width: str = "full"  # "full" (bumper-to-bumper) or "narrow"
    roller_material: str = "flex_wheels"  # from R3
    deploy: bool = True
    motors: int = 2  # rollers + deploy
    game_piece: str = ""
    reasoning: str = ""


@dataclass
class ScorerSpec:
    """Scoring mechanism recommendation from the Oracle."""
    method: str = "elevator"  # "flywheel", "elevator", "gravity_drop" (from R4)
    height_in: float = 0  # for elevator: max height needed
    stages: int = 2  # for elevator: number of stages
    motors: int = 2
    has_wrist: bool = True
    turret: str = "none"  # "none", "continuous", "limited" (from R6)
    reasoning: str = ""


@dataclass
class EndgameSpec:
    """Endgame mechanism recommendation from the Oracle."""
    type: str = "hook_winch"  # "hook_winch", "telescope", "park_only", "none"
    height_in: float = 26.0  # climb height
    motors: int = 1
    reasoning: str = ""


@dataclass
class AutonomousSpec:
    """Autonomous strategy from the Oracle."""
    priority_actions: list = field(default_factory=list)  # ordered list of auto actions
    cycle_time_target_s: float = 5.0  # target cycle time (from R11)
    preload_score: bool = True
    estimated_pieces: int = 2  # realistic auto scoring count
    reasoning: str = ""


@dataclass
class OracleOutput:
    """Complete Oracle prediction for a game."""
    game_name: str = ""
    season_year: int = 2027
    confidence_overall: float = 0.0

    drivetrain: DrivetrainSpec = field(default_factory=DrivetrainSpec)
    intake: IntakeSpec = field(default_factory=IntakeSpec)
    scorer: ScorerSpec = field(default_factory=ScorerSpec)
    endgame: EndgameSpec = field(default_factory=EndgameSpec)
    autonomous: AutonomousSpec = field(default_factory=AutonomousSpec)

    # Weight budget allocation (from R15)
    weight_budget: dict = field(default_factory=lambda: {
        "drivetrain_lb": 45,
        "intake_lb": 12,
        "scorer_lb": 20,
        "endgame_lb": 8,
        "electronics_lb": 15,
        "bumpers_lb": 10,
        "margin_lb": 15,
        "total_limit_lb": 125,
    })

    # Build priority (from R14)
    build_order: list = field(default_factory=lambda: [
        "drivetrain",
        "intake",
        "scorer",
        "autonomous",
        "endgame",
    ])

    notes: str = ""


# ═══════════════════════════════════════════════════════════════════
# PARSING — Oracle JSON → OracleOutput
# ═══════════════════════════════════════════════════════════════════

def parse_oracle_output(data: dict) -> OracleOutput:
    """
    Parse Oracle output JSON into a structured OracleOutput.
    Handles both the structured JSON format and freeform Claude output.
    """
    output = OracleOutput()

    # Top-level metadata
    output.game_name = data.get("game_name", data.get("game", ""))
    output.season_year = data.get("season_year", data.get("year", 2027))
    output.confidence_overall = data.get("confidence", data.get("confidence_overall", 0))

    # Drivetrain
    dt = data.get("drivetrain", data.get("drive", {}))
    if isinstance(dt, dict):
        output.drivetrain = DrivetrainSpec(
            type=dt.get("type", "swerve"),
            module=_normalize_module(dt.get("module", dt.get("swerve_module", "thrifty"))),
            speed_fps=float(dt.get("speed_fps", dt.get("max_speed", 14.5))),
            gear_for=dt.get("gear_for", dt.get("optimize_for", "acceleration")),
            frame_length_in=float(dt.get("frame_length", dt.get("length", 28))),
            frame_width_in=float(dt.get("frame_width", dt.get("width", 28))),
            reasoning=dt.get("reasoning", dt.get("justification", "")),
        )

    # Intake
    intake = data.get("intake", {})
    if isinstance(intake, dict):
        output.intake = IntakeSpec(
            type=_normalize_intake_type(intake.get("type", "over_bumper")),
            width=intake.get("width", "full"),
            roller_material=intake.get("roller_material", intake.get("rollers", "flex_wheels")),
            deploy=intake.get("deploy", intake.get("deployable", True)),
            motors=int(intake.get("motors", intake.get("motor_count", 2))),
            game_piece=intake.get("game_piece", ""),
            reasoning=intake.get("reasoning", ""),
        )

    # Scorer
    scorer = data.get("scorer", data.get("scoring", {}))
    if isinstance(scorer, dict):
        output.scorer = ScorerSpec(
            method=_normalize_scorer_method(scorer.get("method", scorer.get("type", "elevator"))),
            height_in=float(scorer.get("height_in", scorer.get("height", scorer.get("max_height", 0)))),
            stages=int(scorer.get("stages", 2)),
            motors=int(scorer.get("motors", scorer.get("motor_count", 2))),
            has_wrist=scorer.get("has_wrist", scorer.get("wrist", True)),
            turret=scorer.get("turret", "none"),
            reasoning=scorer.get("reasoning", ""),
        )

    # Endgame
    endgame = data.get("endgame", data.get("climb", {}))
    if isinstance(endgame, dict):
        output.endgame = EndgameSpec(
            type=_normalize_endgame_type(endgame.get("type", "hook_winch")),
            height_in=float(endgame.get("height_in", endgame.get("height", 26))),
            motors=int(endgame.get("motors", 1)),
            reasoning=endgame.get("reasoning", ""),
        )

    # Autonomous
    auto = data.get("autonomous", data.get("auto", {}))
    if isinstance(auto, dict):
        output.autonomous = AutonomousSpec(
            priority_actions=auto.get("priority_actions", auto.get("actions", [])),
            cycle_time_target_s=float(auto.get("cycle_time_s", auto.get("cycle_time", 5.0))),
            preload_score=auto.get("preload_score", True),
            estimated_pieces=int(auto.get("estimated_pieces", auto.get("pieces", 2))),
            reasoning=auto.get("reasoning", ""),
        )

    # Weight budget
    if "weight_budget" in data:
        output.weight_budget.update(data["weight_budget"])

    # Build order
    if "build_order" in data:
        output.build_order = data["build_order"]

    output.notes = data.get("notes", "")

    return output


# ═══════════════════════════════════════════════════════════════════
# NORMALIZATION HELPERS
# ═══════════════════════════════════════════════════════════════════

def _normalize_module(raw: str) -> str:
    """Normalize swerve module name to enum value."""
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    mappings = {
        "thrifty": "thrifty",
        "thrifty_swerve": "thrifty",
        "mk4i": "sds_mk4i",
        "sds_mk4i": "sds_mk4i",
        "mk4n": "sds_mk4n",
        "sds_mk4n": "sds_mk4n",
        "maxswerve": "rev_maxswerve",
        "rev_maxswerve": "rev_maxswerve",
        "x2i": "wcp_x2i",
        "wcp_x2i": "wcp_x2i",
        "swervex": "wcp_x2i",
    }
    return mappings.get(raw_lower, "thrifty")


def _normalize_intake_type(raw: str) -> str:
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    mappings = {
        "over_bumper": "over_bumper",
        "over": "over_bumper",
        "ob": "over_bumper",
        "under_bumper": "under_bumper",
        "under": "under_bumper",
        "ub": "under_bumper",
        "full_width": "fixed_full_width",
        "fixed_full_width": "fixed_full_width",
        "fixed": "fixed_full_width",
    }
    return mappings.get(raw_lower, "over_bumper")


def _normalize_scorer_method(raw: str) -> str:
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    mappings = {
        "elevator": "elevator",
        "flywheel": "flywheel",
        "shooter": "flywheel",
        "gravity": "gravity_drop",
        "gravity_drop": "gravity_drop",
        "drop": "gravity_drop",
        "place": "elevator",
        "throw": "flywheel",
        "shoot": "flywheel",
    }
    return mappings.get(raw_lower, "elevator")


def _normalize_endgame_type(raw: str) -> str:
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    mappings = {
        "hook_winch": "hook_winch",
        "hook": "hook_winch",
        "winch": "hook_winch",
        "telescope": "telescope",
        "telescoping": "telescope",
        "park": "park_only",
        "park_only": "park_only",
        "none": "none",
    }
    return mappings.get(raw_lower, "hook_winch")


# ═══════════════════════════════════════════════════════════════════
# BRIDGE — Oracle Output → Blueprint Parameters
# ═══════════════════════════════════════════════════════════════════

def oracle_to_frame_params(oracle: OracleOutput) -> dict:
    """
    Convert Oracle drivetrain prediction into frame_generator parameters.
    This is the core bridge function.
    """
    dt = oracle.drivetrain

    # Speed-based module selection if Oracle didn't specify
    module = dt.module
    if dt.speed_fps > 16 and module == "thrifty":
        module = "sds_mk4i"  # Thrifty caps at 14.5, need faster module

    # Frame size adjustment based on mechanisms
    length = dt.frame_length_in
    width = dt.frame_width_in

    # If scorer is an elevator, may need slightly more internal height clearance
    if oracle.scorer.method == "elevator" and oracle.scorer.height_in > 48:
        # Tall elevator benefits from wider base for stability
        width = max(width, 28)

    # Inset based on module type
    inset = 2.5
    if module in ("sds_mk4i", "sds_mk4n", "wcp_x2i"):
        inset = 2.75  # slightly larger modules
    elif module == "rev_maxswerve":
        inset = 2.0  # compact module

    # Tube selection based on weight budget
    perimeter = "2x1"  # always 2x1 for competition
    cross = "1x1"
    if length > 30 or width > 30:
        cross = "2x1"  # stiffer cross members for larger frames

    return {
        "frame_length_in": length,
        "frame_width_in": width,
        "perimeter_tube": perimeter,
        "cross_tube": cross,
        "module_type": module,
        "module_inset_in": inset,
        "bellypan": True,
        "name": f"2950 {oracle.game_name} Frame" if oracle.game_name else "2950 Swerve Frame",
    }


def oracle_to_blueprint_spec(oracle: OracleOutput) -> dict:
    """
    Full conversion: Oracle predictions → complete Blueprint build spec.
    Returns a dict that describes every subsystem the Blueprint needs to generate.
    """
    frame_params = oracle_to_frame_params(oracle)

    spec = {
        "metadata": {
            "game": oracle.game_name,
            "year": oracle.season_year,
            "confidence": oracle.confidence_overall,
            "generated_by": "The Blueprint — Prediction Bridge",
        },
        "frame": frame_params,
        "subsystems": {
            "intake": {
                "template": oracle.intake.type,
                "width": oracle.intake.width,
                "roller_material": oracle.intake.roller_material,
                "deployable": oracle.intake.deploy,
                "motors": oracle.intake.motors,
                "game_piece": oracle.intake.game_piece,
            },
            "scorer": {
                "template": _scorer_to_template(oracle.scorer),
                "method": oracle.scorer.method,
                "height_in": oracle.scorer.height_in,
                "stages": oracle.scorer.stages,
                "motors": oracle.scorer.motors,
                "has_wrist": oracle.scorer.has_wrist,
                "turret": oracle.scorer.turret,
            },
            "endgame": {
                "template": oracle.endgame.type,
                "height_in": oracle.endgame.height_in,
                "motors": oracle.endgame.motors,
            },
        },
        "autonomous": {
            "cycle_time_target_s": oracle.autonomous.cycle_time_target_s,
            "preload_score": oracle.autonomous.preload_score,
            "estimated_pieces": oracle.autonomous.estimated_pieces,
            "priority_actions": oracle.autonomous.priority_actions,
        },
        "weight_budget": oracle.weight_budget,
        "build_order": oracle.build_order,
    }

    return spec


def _scorer_to_template(scorer: ScorerSpec) -> str:
    """Map scorer spec to Blueprint template name."""
    if scorer.method == "flywheel":
        return "shooter_dual_flywheel"
    elif scorer.method == "elevator":
        if scorer.stages >= 3:
            return "elevator_cascade"
        elif scorer.stages == 2:
            return "elevator_two_stage"
        else:
            return "elevator_single_stage"
    elif scorer.method == "gravity_drop":
        return "gravity_eject"
    return "elevator_two_stage"


# ═══════════════════════════════════════════════════════════════════
# EXAMPLE — 2026 REBUILT game prediction
# ═══════════════════════════════════════════════════════════════════

REBUILT_2026_EXAMPLE = {
    "game_name": "REBUILT",
    "season_year": 2026,
    "confidence": 0.95,
    "drivetrain": {
        "type": "swerve",
        "module": "thrifty",
        "speed_fps": 14.5,
        "gear_for": "acceleration",
        "frame_length": 28,
        "frame_width": 28,
        "reasoning": "R1: Swerve is mandatory post-2022. Small field with short cycles favors acceleration over top speed. Thrifty Swerve is team's existing module."
    },
    "intake": {
        "type": "over_bumper",
        "width": "full",
        "roller_material": "flex_wheels",
        "deploy": True,
        "motors": 2,
        "game_piece": "coral (cylindrical tube)",
        "reasoning": "R2: Full-width intake. R3: Flex wheels for cylindrical game piece (coral). Over-bumper deploy for ground pickup."
    },
    "scorer": {
        "method": "elevator",
        "height_in": 72,
        "stages": 2,
        "motors": 2,
        "has_wrist": True,
        "turret": "none",
        "reasoning": "R4: Placement scoring → elevator. Hub targets require precise vertical placement at multiple heights. R6: Fixed targets, no turret needed."
    },
    "endgame": {
        "type": "hook_winch",
        "height_in": 26,
        "motors": 1,
        "reasoning": "Shallow climb to low bar. Hook + winch is simplest reliable approach."
    },
    "autonomous": {
        "priority_actions": ["score_preload", "intake_nearby", "score_second", "intake_far", "score_third"],
        "cycle_time_s": 4.5,
        "preload_score": True,
        "estimated_pieces": 3,
        "reasoning": "R11: 4.5s cycle target. Short field distances enable 3-piece auto with vision-assisted alignment."
    },
    "weight_budget": {
        "drivetrain_lb": 42,
        "intake_lb": 10,
        "scorer_lb": 22,
        "endgame_lb": 6,
        "electronics_lb": 15,
        "bumpers_lb": 10,
        "margin_lb": 20,
        "total_limit_lb": 125
    },
    "build_order": [
        "drivetrain",
        "scorer",
        "intake",
        "autonomous",
        "endgame"
    ],
    "notes": "Scorer prioritized over intake because elevator determines robot architecture. Intake is adaptable and can be iterated."
}


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("The Blueprint — Prediction Bridge")
        print()
        print("Usage:")
        print("  python3 prediction_bridge.py example       Show example Oracle output + parsed spec")
        print("  python3 prediction_bridge.py parse <file>   Parse Oracle JSON into Blueprint spec")
        print("  python3 prediction_bridge.py generate <file> Parse + generate frame from Oracle output")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "example":
        print("═══ ORACLE OUTPUT (2026 REBUILT) ═══")
        print(json.dumps(REBUILT_2026_EXAMPLE, indent=2))

        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        spec = oracle_to_blueprint_spec(oracle)

        print("\n═══ BLUEPRINT SPEC (parsed) ═══")
        print(json.dumps(spec, indent=2))

        # Generate the frame
        from blueprint.frame_generator import generate_frame, print_summary
        frame_params = oracle_to_frame_params(oracle)
        frame = generate_frame(**frame_params)
        print_summary(frame)

    elif cmd == "parse":
        if len(sys.argv) < 3:
            print("Usage: python3 prediction_bridge.py parse <oracle_output.json>")
            sys.exit(1)
        with open(sys.argv[2]) as f:
            data = json.load(f)
        oracle = parse_oracle_output(data)
        spec = oracle_to_blueprint_spec(oracle)
        print(json.dumps(spec, indent=2))

    elif cmd == "generate":
        if len(sys.argv) < 3:
            print("Usage: python3 prediction_bridge.py generate <oracle_output.json>")
            sys.exit(1)
        with open(sys.argv[2]) as f:
            data = json.load(f)
        oracle = parse_oracle_output(data)
        frame_params = oracle_to_frame_params(oracle)

        from blueprint.frame_generator import generate_frame, print_summary, save_spec
        frame = generate_frame(**frame_params)
        print_summary(frame)
        path = save_spec(frame)
        print(f"Frame spec saved to: {path}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
