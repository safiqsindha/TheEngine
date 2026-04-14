"""
tests/blueprint/test_elevator_rev2_gated.py
Team 2950 — The Devastators

2 Onshape-gated tests for elevator_rev2.py.
These tests are automatically SKIPPED when ONSHAPE_ACCESS_KEY is not set.
Run with a live Onshape MCP connection to exercise the full pipeline.

Requirements:
  - ONSHAPE_ACCESS_KEY env var set
  - An existing Onshape document ID in ELEVATOR_TEST_DOC_ID env var
    (required because free accounts have a 5-document limit)
  - MCP server running (or mcp__onshape module available on sys.path)

Usage:
  ONSHAPE_ACCESS_KEY=... ELEVATOR_TEST_DOC_ID=<doc_id> \\
      pytest tests/blueprint/test_elevator_rev2_gated.py -v
"""

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BLUEPRINT    = _PROJECT_ROOT / "blueprint"
if str(_BLUEPRINT) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT))

from generators.elevator_rev2 import (
    generate_elevator_assembly,
    ORACLE_2026_REBUILT,
)

# ---------------------------------------------------------------------------
# Skip condition — gate on ONSHAPE_ACCESS_KEY
# ---------------------------------------------------------------------------
_HAS_ONSHAPE = bool(os.environ.get("ONSHAPE_ACCESS_KEY"))
_skip_reason = (
    "Onshape-gated test — set ONSHAPE_ACCESS_KEY and ELEVATOR_TEST_DOC_ID "
    "env vars to run"
)


@pytest.fixture(scope="module")
def onshape_doc_id():
    """Return the test document ID from env var."""
    doc_id = os.environ.get("ELEVATOR_TEST_DOC_ID")
    if not doc_id:
        pytest.skip("ELEVATOR_TEST_DOC_ID not set")
    return doc_id


# ---------------------------------------------------------------------------
# Gated test 1: end-to-end assembly creation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_ONSHAPE, reason=_skip_reason)
def test_end_to_end_creates_assembly_with_instances(onshape_doc_id):
    """
    Run full pipeline for a minimal 1-stage, kraken, 36" stroke spec.
    Assert instance_count > 0 and document_url is a valid cad.onshape.com URL.
    """
    oracle = {
        "scorer": {
            "type": "elevator",
            "elevator_stages": 1,
            "target_height_in": 36.0,
            "game_piece_mass_lb": 1.0,
            "motor_preference": "kraken_x60",
            "rigging": "cascade",
        },
        "weight_budget": {"scorer_lb": 15.0},
        "endgame": {"type": "none"},
    }

    result = generate_elevator_assembly(
        oracle_json=oracle,
        doc_id=onshape_doc_id,
        dry_run=False,
    )

    assert result.instance_count > 0, (
        f"Expected instances > 0, got {result.instance_count}. "
        f"Missing parts: {result.missing_parts}"
    )
    assert result.document_url.startswith("https://cad.onshape.com/documents/"), (
        f"Expected cad.onshape.com URL, got: {result.document_url}"
    )
    print(f"\nGated test 1 passed — URL: {result.document_url}")
    print(f"  Instances: {result.instance_count}")
    print(f"  Wall time: {result.wall_time_sec:.1f}s")
    if result.missing_parts:
        print(f"  Missing parts (non-fatal): {result.missing_parts}")


# ---------------------------------------------------------------------------
# Gated test 2: slider mate count matches stage count
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_ONSHAPE, reason=_skip_reason)
def test_end_to_end_slider_mate_count_matches_stage_count(onshape_doc_id):
    """
    Run full pipeline for the 2026_rebuilt oracle (2-stage, 48" stroke).
    Assert slider_count == stage_count (2 sliders for 2-stage).
    """
    result = generate_elevator_assembly(
        oracle_json=ORACLE_2026_REBUILT,
        doc_id=onshape_doc_id,
        dry_run=False,
    )

    # 2026_rebuilt → 2-stage elevator → should produce 2 slider mates
    assert result.slider_count == 2, (
        f"Expected 2 slider mates for 2-stage elevator, got {result.slider_count}. "
        f"Check Phase E in build_elevator_assembly()."
    )
    assert result.document_url.startswith("https://cad.onshape.com/documents/")
    print(f"\nGated test 2 passed — URL: {result.document_url}")
    print(f"  Slider mates: {result.slider_count}")
    print(f"  Wall time: {result.wall_time_sec:.1f}s")
