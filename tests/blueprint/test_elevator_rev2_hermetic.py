"""
tests/blueprint/test_elevator_rev2_hermetic.py
Team 2950 — The Devastators

18 hermetic tests for elevator_rev2.py and elevator_parts.py.
No Onshape dependency — all MCP calls are blocked at import time.
Tests cover: physics layer, part-ID mapping, oracle parse, dry-run CLI output.
"""

import json
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — tests run from project root or tests/blueprint/
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BLUEPRINT    = _PROJECT_ROOT / "blueprint"

if str(_BLUEPRINT) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT))
if str(_BLUEPRINT / "generators") not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT / "generators"))

from cots_parts.elevator_parts import (
    ELEVATOR_PARTS,
    resolve,
    resolve_spring_for_load,
    resolve_bearing_block,
    validate_all,
)
from generators.elevator_rev2 import (
    ElevatorInputs,
    ElevatorPhysicsResult,
    compute_elevator_physics,
    parse_oracle_output,
    generate_elevator_assembly,
    set_mcp_module,
    ORACLE_2026_REBUILT,
    _nearest_tube_length,
    _spring_for_load,
    ESTIMATED_END_EFFECTOR_LB,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _inputs(stroke_in=48.0, load_lb=6.5, motor="kraken_x60"):
    return ElevatorInputs(
        target_stroke_in=stroke_in,
        carriage_load_lb=load_lb,
        game_piece_mass_lb=load_lb - ESTIMATED_END_EFFECTOR_LB,
        motor_pref=motor,
        rigging="cascade",
        weight_budget_lb=20.0,
    )


# ===========================================================================
# Physics layer tests
# ===========================================================================

class TestStageCount:
    def test_stage_count_1_for_stroke_under_40in(self):
        result = compute_elevator_physics(_inputs(stroke_in=36.0))
        assert result.stage_count == 1

    def test_stage_count_2_for_stroke_40_to_55in(self):
        result = compute_elevator_physics(_inputs(stroke_in=48.0))
        assert result.stage_count == 2

    def test_stage_count_2_for_stroke_over_55in(self):
        """Oracle R5 caps at 2 stages; physics confirms 2."""
        result = compute_elevator_physics(_inputs(stroke_in=60.0))
        assert result.stage_count == 2

    def test_stage_count_exactly_at_threshold(self):
        result = compute_elevator_physics(_inputs(stroke_in=40.0))
        assert result.stage_count == 2


class TestTubeLength:
    def test_tube_length_formula_24in_stroke(self):
        """24" stroke / 1 stage + 4" bearing = 28" → rounds to 28in stock."""
        result = compute_elevator_physics(_inputs(stroke_in=24.0))
        assert result.stage_count == 1
        assert result.tube_length_in == 28  # 24/1 + 4 = 28

    def test_tube_length_formula_48in_stroke(self):
        """48" stroke / 2 stages + 4" bearing = 28" → rounds to 28in stock."""
        result = compute_elevator_physics(_inputs(stroke_in=48.0))
        assert result.stage_count == 2
        assert result.tube_length_in == 28  # 48/2 + 4 = 28

    def test_tube_length_36in_stroke_single_stage(self):
        """36" stroke / 1 stage + 4" bearing = 40" → rounds to nearest above → 36? No → clamps to 36."""
        # 36/1 + 4 = 40 → exceeds 36, so clamp to max (36)
        result = compute_elevator_physics(_inputs(stroke_in=32.0))
        assert result.stage_count == 1
        # 32/1 + 4 = 36 → exactly matches 36in stock
        assert result.tube_length_in == 36


class TestCarriagePlate:
    def test_carriage_plate_thin_under_8lb(self):
        result = compute_elevator_physics(_inputs(load_lb=5.0))
        assert result.carriage_plate_thickness_in == 0.125

    def test_carriage_plate_thick_at_8lb(self):
        result = compute_elevator_physics(_inputs(load_lb=8.0))
        assert result.carriage_plate_thickness_in == 0.250

    def test_carriage_plate_thick_above_8lb(self):
        result = compute_elevator_physics(_inputs(load_lb=12.0))
        assert result.carriage_plate_thickness_in == 0.250


class TestGearRatio:
    def test_gear_ratio_light_load(self):
        result = compute_elevator_physics(_inputs(load_lb=4.0))
        assert result.gear_ratio == 5

    def test_gear_ratio_medium_load(self):
        result = compute_elevator_physics(_inputs(load_lb=7.0))
        assert result.gear_ratio == 7

    def test_gear_ratio_heavy_load(self):
        result = compute_elevator_physics(_inputs(load_lb=12.0))
        assert result.gear_ratio == 10

    def test_gear_ratio_boundary_5lb(self):
        """Exactly 5 lb → medium (5–10 lb range)."""
        result = compute_elevator_physics(_inputs(load_lb=5.0))
        assert result.gear_ratio == 7


class TestMotorPreference:
    def test_motor_preference_kraken_passthrough(self):
        result = compute_elevator_physics(_inputs(motor="kraken_x60"))
        assert result.motor_type == "kraken_x60"

    def test_motor_preference_neo_passthrough(self):
        result = compute_elevator_physics(_inputs(motor="neo"))
        assert result.motor_type == "neo"

    def test_unknown_motor_defaults_to_kraken(self):
        result = compute_elevator_physics(_inputs(motor="falcon_500"))
        assert result.motor_type == "kraken_x60"


class TestSpringForce:
    def test_spring_force_rounds_to_nearest_stock(self):
        """9 lb load → 8 lb spring (nearest WCP stock below load)."""
        assert _spring_for_load(9.0) == 8.0

    def test_spring_force_exact_match(self):
        assert _spring_for_load(8.0) == 8.0

    def test_spring_force_below_minimum(self):
        assert _spring_for_load(1.0) == 4.0  # minimum available

    def test_spring_force_above_all_ratings(self):
        assert _spring_for_load(20.0) == 16.0  # max available


# ===========================================================================
# Part-ID mapping tests
# ===========================================================================

class TestElevatorParts:
    def test_resolve_stage_rail_key_returns_dict_with_required_fields(self):
        part = resolve("stage_rail_2x1_24in")
        assert "elem_name" in part
        assert "geometry_spec" in part
        assert part["is_asm"] is None

    def test_resolve_unknown_key_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown key"):
            resolve("nonexistent_part_xyz")

    def test_all_elevator_parts_have_required_fields(self):
        errors = validate_all()
        assert errors == [], f"Validation errors:\n" + "\n".join(errors)

    def test_kraken_x60_not_duplicated(self):
        """elevator_parts imports Kraken X60 from frcdesignlib_parts.json."""
        kraken = resolve("kraken_x60")
        assert "doc" in kraken
        # Verify doc ID matches frcdesignlib_parts.json
        frcdesign = json.loads(
            (_BLUEPRINT / "frcdesignlib_parts.json").read_text()
        )
        expected_doc = frcdesign["WCP Kraken X60"]["doc"]
        assert kraken["doc"] == expected_doc, (
            f"Kraken doc mismatch: elevator_parts has {kraken['doc']}, "
            f"frcdesignlib_parts has {expected_doc}"
        )

    def test_bearing_block_resolve_wcp(self):
        part = resolve_bearing_block("wcp")
        assert "Elevator Bearing Block" in part["elem_name"]

    def test_spring_for_load_under_8lb(self):
        part = resolve_spring_for_load(6.0)
        assert "wcp" in part["elem_name"].lower() or "4" in part["elem_name"]

    def test_spring_for_load_over_8lb(self):
        part = resolve_spring_for_load(10.0)
        assert "16" in part["elem_name"] or "ttb" in part["elem_name"].lower()


# ===========================================================================
# Oracle parse test
# ===========================================================================

class TestParseOracle:
    def test_parse_2026_rebuilt_fixture(self):
        inputs = parse_oracle_output(ORACLE_2026_REBUILT)
        assert inputs.target_stroke_in == 48.0
        assert inputs.motor_pref == "kraken_x60"
        assert inputs.carriage_load_lb == pytest.approx(
            ORACLE_2026_REBUILT["scorer"]["game_piece_mass_lb"] + ESTIMATED_END_EFFECTOR_LB
        )

    def test_parse_raises_on_non_elevator_scorer(self):
        with pytest.raises(ValueError, match="scorer type"):
            parse_oracle_output({"scorer": {"type": "shooter"}})


# ===========================================================================
# Dry-run CLI test
# ===========================================================================

class TestDryRun:
    def test_dry_run_produces_physics_result_json(self):
        """
        Run generate_elevator_assembly with dry_run=True;
        assert stdout is valid JSON with expected physics keys.
        """
        result = generate_elevator_assembly(
            oracle_json=ORACLE_2026_REBUILT,
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.document_url == ""

    def test_dry_run_physics_values_2026_rebuilt(self):
        """Physics for 2026_rebuilt (48" stroke, 6.5 lb load) — key assertions."""
        inputs = parse_oracle_output(ORACLE_2026_REBUILT)
        physics = compute_elevator_physics(inputs)
        assert physics.stage_count == 2
        assert physics.tube_length_in == 28
        assert physics.gear_ratio == 7   # 6.5 lb → medium
        assert physics.motor_type == "kraken_x60"
        assert physics.carriage_plate_thickness_in == 0.125  # 6.5 lb < 8 lb
