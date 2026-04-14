#!/usr/bin/env python3
"""
The Engine — Full Robot Assembly Builder
Team 2950 — The Devastators

Phase 1 (Blueprint Rev-2 MCP pivot): wires oracle output to MCP generators.
Currently dispatches scorer == "elevator" to elevator_rev2.generate_elevator_assembly.
Phase 2 will add swerve frame dispatcher.

See BLUEPRINT_REV2_COPY_PARAMETRIZE.md for the implementation spec.

Usage:
  python3 build_full_robot.py <blueprint_spec.json>
  python3 build_full_robot.py <blueprint_spec.json> --dry-run
  python3 build_full_robot.py <blueprint_spec.json> --doc-id <onshape_doc_id>
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def build_full_robot(
    spec_path: str = None,
    dry_run: bool = False,
    doc_id: str = None,
):
    """
    Dispatch oracle output to the appropriate MCP generator.

    Currently supported scorers:
      "elevator" → blueprint/generators/elevator_rev2.py

    Phase 2 will add:
      "swerve"   → blueprint/generators/swerve_rev2.py  (B-MCP.3)
    """
    if spec_path is None:
        print("Usage: build_full_robot.py <blueprint_spec.json>", file=sys.stderr)
        sys.exit(1)

    spec_file = Path(spec_path)
    if not spec_file.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    oracle_json = json.loads(spec_file.read_text())
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

    # Phase 2 hook — swerve frame (B-MCP.3)
    if scorer_type == "swerve":
        raise NotImplementedError(
            "build_full_robot: swerve generator is Phase 2 (B-MCP.3). "
            "See BLUEPRINT_REV2_COPY_PARAMETRIZE.md."
        )

    raise ValueError(
        f"build_full_robot: unknown scorer type '{scorer_type}'. "
        f"Supported: 'elevator'. Got oracle keys: {list(oracle_json.keys())}"
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
