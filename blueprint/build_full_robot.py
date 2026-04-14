#!/usr/bin/env python3
"""
The Engine — Full Robot Assembly Builder
Team 2950 — The Devastators

Phase 1 (Blueprint Rev-2 MCP pivot): wires oracle output to MCP generators.
Phase 2 (B-MCP.3): adds swerve frame dispatcher → swerve_rev2.generate_swerve_assembly.
Phase 3 (B-MCP.4): normalise_oracle_output() merges the oracle→generator shape
    adapter (previously only in demo_full_pipeline.py) into production dispatch.

See BLUEPRINT_REV2_COPY_PARAMETRIZE.md for the implementation spec.

Usage:
  python3 build_full_robot.py <blueprint_spec.json>
  python3 build_full_robot.py <blueprint_spec.json> --dry-run
  python3 build_full_robot.py <blueprint_spec.json> --doc-id <onshape_doc_id>

Oracle shape bridge (normalised here, not in generators):
  Oracle emits:  scorer.method, scorer.height_in, scorer.stages
  Generators expect: scorer.type, scorer.target_height_in, scorer.elevator_stages
  normalise_oracle_output() translates between the two so generators always
  receive the shape they expect, regardless of whether the input came from
  oracle.predict_game() (raw oracle shape) or a hand-crafted spec JSON
  (generator shape).  If scorer.type is already set, the input passes through.
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Oracle → generator normalisation (merged from demo_full_pipeline.py)
# ---------------------------------------------------------------------------

def normalise_oracle_output(oracle_json: dict) -> dict:
    """
    Translate oracle.predict_game() output into the shape expected by
    elevator_rev2 / swerve_rev2 generators.

    Oracle emits:
      scorer.method        = "elevator" | "flywheel" | …
      scorer.height_in     = int
      scorer.stages        = int

    Generators expect:
      scorer.type               = "elevator" | "swerve"
      scorer.elevator_stages    = int
      scorer.target_height_in   = float
      scorer.game_piece_mass_lb = float
      scorer.motor_preference   = str
      scorer.rigging            = str

    Pass-through rule: if scorer.type is already set (hand-crafted spec),
    the dict is returned unchanged.
    """
    scorer = oracle_json.get("scorer", {})

    # Already in generator format — pass through
    if scorer.get("type"):
        return oracle_json

    method = scorer.get("method", "")
    wb = oracle_json.get("weight_budget", {})
    dt = oracle_json.get("drivetrain", {})

    if method == "elevator":
        return {
            "scorer": {
                "type": "elevator",
                "elevator_stages":    scorer.get("stages", 2),
                "target_height_in":   float(scorer.get("height_in", 48)),
                "game_piece_mass_lb": float(scorer.get("game_piece_mass_lb", 1.0)),
                "motor_preference":   "kraken_x60",
                "rigging":            "cascade",
            },
            "weight_budget": {
                "scorer_lb": float(wb.get("scorer_lb", 18.0)),
            },
            "endgame": oracle_json.get("endgame", {}),
        }

    if method == "swerve" or dt.get("type") == "swerve":
        return {
            "scorer": {
                "type":         "swerve",
                "wheelbase_in":  float(dt.get("frame_length", 27.0)),
                "trackwidth_in": float(dt.get("frame_width",  27.0)),
                "module_type":   dt.get("module", "sds_mk4i"),
                "module_count":  4,
            },
            "weight_budget": {
                "scorer_lb": float(wb.get("drivetrain_lb", 30.0)),
            },
            "endgame": {"type": "none"},
        }

    # Unknown method — return unchanged and let generator raise
    return oracle_json


def build_full_robot(
    spec_path: str = None,
    dry_run: bool = False,
    doc_id: str = None,
):
    """
    Dispatch oracle output to the appropriate MCP generator.

    Input may be raw oracle.predict_game() output OR a hand-crafted spec JSON.
    normalise_oracle_output() bridges any shape mismatch before dispatch.

    Supported scorers (after normalisation):
      "elevator" → blueprint/generators/elevator_rev2.py  (B-MCP.2)
      "swerve"   → blueprint/generators/swerve_rev2.py   (B-MCP.3)
    """
    if spec_path is None:
        print("Usage: build_full_robot.py <blueprint_spec.json>", file=sys.stderr)
        sys.exit(1)

    spec_file = Path(spec_path)
    if not spec_file.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    raw_json    = json.loads(spec_file.read_text())
    oracle_json = normalise_oracle_output(raw_json)
    scorer_type = oracle_json.get("scorer", {}).get("type", "")

    if scorer_type == "elevator":
        from generators.elevator_rev2 import generate_elevator_assembly
        result = generate_elevator_assembly(
            oracle_json=oracle_json,
            doc_id=doc_id,
            dry_run=dry_run,
        )
        print(result)
        return result

    # Phase 2 — swerve frame (B-MCP.3)
    if scorer_type == "swerve":
        from generators.swerve_rev2 import generate_swerve_assembly
        result = generate_swerve_assembly(
            oracle_json=oracle_json,
            doc_id=doc_id,
            dry_run=dry_run,
        )
        print(result)
        return result

    raise ValueError(
        f"build_full_robot: unknown scorer type '{scorer_type}' "
        f"(after normalisation). "
        f"Supported: 'elevator', 'swerve'. "
        f"Oracle keys: {list(raw_json.keys())}"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Team 2950 Full Robot Assembly Builder"
    )
    parser.add_argument("spec", help="Path to oracle/blueprint spec JSON")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--doc-id", default=None,
                        help="Existing Onshape document ID (required on free accounts)")
    args = parser.parse_args()
    build_full_robot(args.spec, dry_run=args.dry_run, doc_id=args.doc_id)
