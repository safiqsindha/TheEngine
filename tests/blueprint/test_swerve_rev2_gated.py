"""
tests/blueprint/test_swerve_rev2_gated.py
Team 2950 — The Devastators

2 Onshape-gated tests for swerve_rev2.py.
These tests are automatically SKIPPED when ONSHAPE_ACCESS_KEY is not set.
Run with a live Onshape MCP connection to exercise the full pipeline.

Requirements:
  - ONSHAPE_ACCESS_KEY env var set
  - An existing Onshape document ID in SWERVE_TEST_DOC_ID env var
    (required because free accounts have a 5-document limit)
  - MCP server running (or mcp__onshape module available on sys.path)

Usage:
  ONSHAPE_ACCESS_KEY=... SWERVE_TEST_DOC_ID=<doc_id> \\
      pytest tests/blueprint/test_swerve_rev2_gated.py -v
"""

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BLUEPRINT    = _PROJECT_ROOT / "blueprint"
if str(_BLUEPRINT) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT))

from generators.swerve_rev2 import (
    generate_swerve_assembly,
    ORACLE_SWERVE_26x26,
    ORACLE_SWERVE_28x28,
)

# ---------------------------------------------------------------------------
# Skip condition — gate on ONSHAPE_ACCESS_KEY
# ---------------------------------------------------------------------------
_HAS_ONSHAPE = bool(os.environ.get("ONSHAPE_ACCESS_KEY"))
_skip_reason = (
    "Onshape-gated test — set ONSHAPE_ACCESS_KEY and SWERVE_TEST_DOC_ID "
    "env vars to run"
)


@pytest.fixture(scope="module")
def onshape_doc_id():
    """Return the test document ID from env var."""
    doc_id = os.environ.get("SWERVE_TEST_DOC_ID")
    if not doc_id:
        pytest.skip("SWERVE_TEST_DOC_ID not set")
    return doc_id


# ---------------------------------------------------------------------------
# Gated test 1: end-to-end assembly creation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_ONSHAPE, reason=_skip_reason)
def test_end_to_end_creates_assembly_with_instances(onshape_doc_id):
    """
    Run full pipeline for a 26×26 swerve frame.
    Assert instance_count > 0 and document_url is a valid cad.onshape.com URL.
    Expected minimum: 4 module + 4 gusset + 4 LS rails + 2 SS rails = 14 instances.
    """
    result = generate_swerve_assembly(
        oracle_json=ORACLE_SWERVE_26x26,
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
    print(f"  Instances : {result.instance_count}")
    print(f"  Wall time : {result.wall_time_sec:.1f}s")
    if result.missing_parts:
        print(f"  Missing parts (non-fatal): {result.missing_parts}")


# ---------------------------------------------------------------------------
# Gated test 2: fastened mate count >= 4 (module-to-frame mates at minimum)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_ONSHAPE, reason=_skip_reason)
def test_end_to_end_fastened_mate_count_at_least_four(onshape_doc_id):
    """
    Run full pipeline for a 28×28 swerve frame.
    Assert fastened_count >= 4 (4 module mounts at minimum; up to 8 with gussets).
    """
    result = generate_swerve_assembly(
        oracle_json=ORACLE_SWERVE_28x28,
        doc_id=onshape_doc_id,
        dry_run=False,
    )

    assert result.fastened_count >= 4, (
        f"Expected >= 4 fastened mates (module mounts), got {result.fastened_count}. "
        f"Check Phase E in build_swerve_assembly()."
    )
    assert result.document_url.startswith("https://cad.onshape.com/documents/")
    print(f"\nGated test 2 passed — URL: {result.document_url}")
    print(f"  Fastened mates: {result.fastened_count}")
    print(f"  Wall time     : {result.wall_time_sec:.1f}s")
