#!/usr/bin/env python3
"""
The Engine — Full Robot Assembly Builder
Team 2950 — The Devastators

Phase 0 stub (Blueprint Rev-2 MCP pivot):
  The previous implementation used cad_builder.py, assembly_builder.py,
  and insert_cots.py — all three have been deleted in the MCP pivot.
  This orchestrator is scheduled for a full rewrite in Phase 1 (B-MCP.2)
  using the new MCP-backed elevator_rev2.py generator as the pattern.

  See BLUEPRINT_REV2_COPY_PARAMETRIZE.md for the Phase 1 spec.
  See BLUEPRINT_REV2_DECISION.md for the fate table.

Usage (Phase 1+):
  python3 build_full_robot.py <blueprint_spec.json>
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def build_full_robot(spec_path: str = None):
    """
    Phase 1 rewrite pending — see BLUEPRINT_REV2_COPY_PARAMETRIZE.md.

    The previous implementation called cad_builder.generate_full_featurescript,
    assembly_builder.plan_assembly, and insert_cots.insert_part — all three
    source modules were deleted in the Blueprint Rev-2 MCP pivot (Phase 0).

    Phase 1 will wire this orchestrator to:
      - blueprint/generators/elevator_rev2.py (the first MCP generator)
      - Additional mechanism generators as they are authored in Phase 2+
    """
    raise NotImplementedError(
        "build_full_robot: Phase 1 rewrite required. "
        "See BLUEPRINT_REV2_COPY_PARAMETRIZE.md for the implementation spec. "
        "The previous cad_builder/assembly_builder/insert_cots pipeline was "
        "deleted in the Rev-2 MCP pivot."
    )


if __name__ == "__main__":
    spec = sys.argv[1] if len(sys.argv) > 1 else None
    build_full_robot(spec)
