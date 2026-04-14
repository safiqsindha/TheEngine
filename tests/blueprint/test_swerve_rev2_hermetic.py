"""
tests/blueprint/test_swerve_rev2_hermetic.py
Team 2950 — The Devastators

21 hermetic tests for swerve_rev2.py and swerve_parts.py.
No Onshape dependency — all MCP calls are blocked at import time.
Tests cover: physics layer, part-ID mapping, oracle parse, dry-run output.
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BLUEPRINT    = _PROJECT_ROOT / "blueprint"

if str(_BLUEPRINT) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT))
if str(_BLUEPRINT / "generators") not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT / "generators"))

from cots_parts.swerve_parts import (
    SWERVE_PARTS,
    resolve,
    resolve_module,
    validate_all,
)
from generators.swerve_rev2 import (
    SwerveInputs,
    SwervePhysicsResult,
    compute_swerve_physics,
    parse_oracle_output,
    generate_swerve_assembly,
    set_mcp_module,
    ORACLE_SWERVE_26x26,
    ORACLE_SWERVE_28x28,
    MODULE_COUNT,
    GUSSET_COUNT,
    DEFAULT_WHEELBASE_IN,
    DEFAULT_TRACKWIDTH_IN,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _inputs(wheelbase=26.0, trackwidth=26.0, module_type="sds_mk4i"):
    return SwerveInputs(
        wheelbase_in=wheelbase,
        trackwidth_in=trackwidth,
        module_type=module_type,
        module_count=4,
        weight_budget_lb=35.0,
    )


# ===========================================================================
# Physics layer tests
# ===========================================================================

class TestRailLengths:
    def test_longside_rail_equals_trackwidth(self):
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=28.0))
        assert result.rail_longside_in == 28.0

    def test_shortside_rail_equals_wheelbase(self):
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=28.0))
        assert result.rail_shortside_in == 26.0

    def test_square_frame_has_equal_rails(self):
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=26.0))
        assert result.rail_longside_in == result.rail_shortside_in == 26.0

    def test_rail_spec_is_standard_tube(self):
        result = compute_swerve_physics(_inputs())
        assert result.rail_spec == "2x1x0.0625"

    def test_default_wheelbase_trackwidth(self):
        result = compute_swerve_physics(_inputs())
        assert result.wheelbase_in == DEFAULT_WHEELBASE_IN
        assert result.trackwidth_in == DEFAULT_TRACKWIDTH_IN


class TestModuleResolution:
    def test_sds_mk4i_resolves_directly(self):
        result = compute_swerve_physics(_inputs(module_type="sds_mk4i"))
        assert result.module_part_key == "sds_mk4i"
        assert result.module_type_orig == "sds_mk4i"

    def test_wcp_swerve_x_falls_back_to_mk4i(self):
        result = compute_swerve_physics(_inputs(module_type="wcp_swerve_x"))
        assert result.module_part_key == "sds_mk4i"   # fallback
        assert result.module_type_orig == "wcp_swerve_x"  # original preserved

    def test_rev_maxswerve_falls_back_to_mk4i(self):
        result = compute_swerve_physics(_inputs(module_type="rev_maxswerve"))
        assert result.module_part_key == "sds_mk4i"
        assert result.module_type_orig == "rev_maxswerve"

    def test_unknown_module_type_falls_back_to_mk4i(self):
        result = compute_swerve_physics(_inputs(module_type="fictional_module"))
        assert result.module_part_key == "sds_mk4i"


class TestCounts:
    def test_module_count_is_always_four(self):
        result = compute_swerve_physics(_inputs())
        assert result.module_count == MODULE_COUNT == 4

    def test_gusset_count_is_always_four(self):
        result = compute_swerve_physics(_inputs())
        assert result.gusset_count == GUSSET_COUNT == 4


class TestLayoutMm:
    def test_layout_has_all_expected_roles(self):
        result = compute_swerve_physics(_inputs())
        expected_roles = {
            "RAIL_LS_1", "RAIL_LS_2", "RAIL_LS_3", "RAIL_LS_4",
            "RAIL_SS_1", "RAIL_SS_2",
            "GUSSET_1", "GUSSET_2", "GUSSET_3", "GUSSET_4",
            "MOD_FL", "MOD_FR", "MOD_RL", "MOD_RR",
        }
        assert set(result.layout_mm.keys()) == expected_roles

    def test_layout_has_14_roles(self):
        result = compute_swerve_physics(_inputs())
        assert len(result.layout_mm) == 14

    def test_front_modules_positive_y(self):
        """Front modules (FL, FR) should be at positive Y (forward)."""
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=26.0))
        assert result.layout_mm["MOD_FL"]["y"] > 0
        assert result.layout_mm["MOD_FR"]["y"] > 0

    def test_rear_modules_negative_y(self):
        """Rear modules (RL, RR) should be at negative Y (rearward)."""
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=26.0))
        assert result.layout_mm["MOD_RL"]["y"] < 0
        assert result.layout_mm["MOD_RR"]["y"] < 0

    def test_left_modules_negative_x(self):
        """Left modules (FL, RL) should be at negative X."""
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=26.0))
        assert result.layout_mm["MOD_FL"]["x"] < 0
        assert result.layout_mm["MOD_RL"]["x"] < 0

    def test_right_modules_positive_x(self):
        """Right modules (FR, RR) should be at positive X."""
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=26.0))
        assert result.layout_mm["MOD_FR"]["x"] > 0
        assert result.layout_mm["MOD_RR"]["x"] > 0

    def test_module_xy_offset_matches_half_wb_tw(self):
        """Module X offset = trackwidth/2 in mm; Y offset = wheelbase/2 in mm."""
        result = compute_swerve_physics(_inputs(wheelbase=26.0, trackwidth=28.0))
        expected_x_mm = (28.0 / 2) * 25.4   # 355.6 mm
        expected_y_mm = (26.0 / 2) * 25.4   # 330.2 mm
        assert abs(abs(result.layout_mm["MOD_FL"]["x"]) - expected_x_mm) < 0.01
        assert abs(abs(result.layout_mm["MOD_FL"]["y"]) - expected_y_mm) < 0.01


class TestWeightEstimate:
    def test_weight_estimate_positive(self):
        result = compute_swerve_physics(_inputs())
        assert result.estimated_weight_lb > 0

    def test_larger_frame_heavier(self):
        small = compute_swerve_physics(_inputs(wheelbase=22.0, trackwidth=22.0))
        large = compute_swerve_physics(_inputs(wheelbase=28.0, trackwidth=28.0))
        assert large.estimated_weight_lb > small.estimated_weight_lb


# ===========================================================================
# Part-ID mapping tests
# ===========================================================================

class TestSwerveParts:
    def test_resolve_unknown_key_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown key"):
            resolve("nonexistent_part_xyz")

    def test_all_swerve_parts_have_required_fields(self):
        errors = validate_all()
        assert errors == [], "Validation errors:\n" + "\n".join(errors)

    def test_sds_mk4i_imports_from_frcdesignlib(self):
        """swerve_parts imports MK4i from frcdesignlib_parts.json — no duplicate doc ID."""
        part = resolve("sds_mk4i")
        frcdesign = json.loads((_BLUEPRINT / "frcdesignlib_parts.json").read_text())
        expected_doc = frcdesign["SDS MK4i Swerve Module"]["doc"]
        assert part["doc"] == expected_doc, (
            f"MK4i doc mismatch: swerve_parts has {part['doc']}, "
            f"frcdesignlib_parts has {expected_doc}"
        )

    def test_gusset_imports_from_frcdesignlib(self):
        """swerve_parts imports WCP gusset from frcdesignlib_parts.json."""
        part = resolve("wcp_90deg_gusset_2x1")
        frcdesign = json.loads((_BLUEPRINT / "frcdesignlib_parts.json").read_text())
        expected_doc = frcdesign["WCP 90° Gusset (2x1 to 2x1)"]["doc"]
        assert part["doc"] == expected_doc

    def test_sds_mk4i_is_assembly(self):
        part = resolve("sds_mk4i")
        assert part["is_asm"] is True

    def test_gusset_is_part_studio(self):
        part = resolve("wcp_90deg_gusset_2x1")
        assert part["is_asm"] is False

    def test_frame_rails_are_geometry_created(self):
        longside = resolve("frame_rail_longside")
        shortside = resolve("frame_rail_shortside")
        assert longside["is_asm"] is None
        assert shortside["is_asm"] is None

    def test_resolve_module_mk4i_returns_mk4i(self):
        part, effective_key = resolve_module("sds_mk4i")
        assert effective_key == "sds_mk4i"
        assert part.get("is_asm") is True

    def test_resolve_module_wcp_falls_back(self):
        part, effective_key = resolve_module("wcp_swerve_x")
        assert effective_key == "sds_mk4i"   # fallback applied

    def test_resolve_module_unknown_falls_back(self):
        part, effective_key = resolve_module("totally_unknown_module")
        assert effective_key == "sds_mk4i"


# ===========================================================================
# Oracle parse tests
# ===========================================================================

class TestParseOracle:
    def test_parse_26x26_fixture(self):
        inputs = parse_oracle_output(ORACLE_SWERVE_26x26)
        assert inputs.wheelbase_in == 26.0
        assert inputs.trackwidth_in == 26.0
        assert inputs.module_type == "sds_mk4i"
        assert inputs.module_count == 4

    def test_parse_28x28_fixture(self):
        inputs = parse_oracle_output(ORACLE_SWERVE_28x28)
        assert inputs.wheelbase_in == 28.0
        assert inputs.trackwidth_in == 28.0

    def test_parse_raises_on_non_swerve_scorer(self):
        with pytest.raises(ValueError, match="scorer type"):
            parse_oracle_output({"scorer": {"type": "elevator"}})

    def test_parse_raises_on_wrong_module_count(self):
        bad_oracle = {
            "scorer": {
                "type": "swerve",
                "wheelbase_in": 26.0,
                "trackwidth_in": 26.0,
                "module_type": "sds_mk4i",
                "module_count": 6,
            },
            "weight_budget": {"scorer_lb": 35.0},
        }
        with pytest.raises(ValueError, match="module_count"):
            parse_oracle_output(bad_oracle)


# ===========================================================================
# Dry-run tests
# ===========================================================================

class TestDryRun:
    def test_dry_run_returns_assembly_result_with_dry_run_flag(self):
        result = generate_swerve_assembly(
            oracle_json=ORACLE_SWERVE_26x26,
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.document_url == ""

    def test_dry_run_physics_26x26_rail_lengths(self):
        """Physics for 26x26 frame — rail lengths match wheelbase/trackwidth."""
        inputs = parse_oracle_output(ORACLE_SWERVE_26x26)
        physics = compute_swerve_physics(inputs)
        assert physics.rail_longside_in == 26.0
        assert physics.rail_shortside_in == 26.0
        assert physics.module_count == 4
        assert physics.gusset_count == 4

    def test_dry_run_instance_count_is_zero(self):
        """Dry-run must not create any MCP instances."""
        result = generate_swerve_assembly(
            oracle_json=ORACLE_SWERVE_26x26,
            dry_run=True,
        )
        assert result.instance_count == 0
        assert result.fastened_count == 0
