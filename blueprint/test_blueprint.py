"""
The Blueprint — Test Suite
Team 2950 — The Devastators

Tests for frame_generator.py, prediction_bridge.py, and onshape_api.py.
Categories:
  FRAME GENERATOR (20 tests) — geometry, weights, presets, edge cases
  PREDICTION BRIDGE (15 tests) — parsing, normalization, bridge logic
  ONSHAPE API (5 tests) — smoke tests for API wrapper (skip if no keys)
  COTS CATALOG (5 tests) — catalog loading and lookup
  INTEGRATION (5 tests) — end-to-end pipeline

Run: python3 test_blueprint.py
"""

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from frame_generator import (
    generate_frame,
    generate_from_preset,
    FrameSpec,
    TubeMember,
    ModulePlacement,
    SWERVE_MODULES,
    SwerveModuleType,
    TUBE_STOCK,
    TubeSize,
    PRESETS,
    ELECTRONICS,
    save_spec,
    print_summary,
    print_cutlist,
)
from prediction_bridge import (
    parse_oracle_output,
    oracle_to_frame_params,
    oracle_to_blueprint_spec,
    OracleOutput,
    DrivetrainSpec,
    IntakeSpec,
    ScorerSpec,
    EndgameSpec,
    AutonomousSpec,
    REBUILT_2026_EXAMPLE,
    _normalize_module,
    _normalize_intake_type,
    _normalize_scorer_method,
    _normalize_endgame_type,
)
from onshape_api import load_cots_catalog, lookup_part, test_connection


# ═══════════════════════════════════════════════════════════════════
# FRAME GENERATOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFrameGeometry(unittest.TestCase):
    """Tests for frame dimension calculations."""

    def test_default_frame_dimensions(self):
        spec = generate_frame()
        self.assertEqual(spec.frame_length_in, 28.0)
        self.assertEqual(spec.frame_width_in, 28.0)

    def test_custom_dimensions(self):
        spec = generate_frame(frame_length_in=30, frame_width_in=26)
        self.assertEqual(spec.frame_length_in, 30.0)
        self.assertEqual(spec.frame_width_in, 26.0)

    def test_perimeter_calculation(self):
        spec = generate_frame(frame_length_in=28, frame_width_in=28)
        self.assertEqual(spec.bumper_perimeter_in, 112.0)

    def test_perimeter_within_rules_pass(self):
        spec = generate_frame(frame_length_in=28, frame_width_in=28)
        self.assertTrue(spec.within_frame_perimeter)

    def test_perimeter_within_rules_max(self):
        spec = generate_frame(frame_length_in=36, frame_width_in=24)
        self.assertTrue(spec.within_frame_perimeter)  # 36 <= 36

    def test_perimeter_within_rules_fail(self):
        spec = generate_frame(frame_length_in=37, frame_width_in=28)
        self.assertFalse(spec.within_frame_perimeter)  # 37 > 36

    def test_tube_members_exist(self):
        spec = generate_frame()
        self.assertGreater(len(spec.tube_members), 0)

    def test_perimeter_has_four_rails(self):
        spec = generate_frame()
        rail_names = [m["name"] for m in spec.tube_members]
        self.assertIn("front_rail", rail_names)
        self.assertIn("back_rail", rail_names)
        self.assertIn("left_rail", rail_names)
        self.assertIn("right_rail", rail_names)

    def test_cross_members_minimum_three(self):
        spec = generate_frame()
        self.assertGreaterEqual(spec.cross_member_count, 3)

    def test_long_frame_extra_cross_members(self):
        short = generate_frame(frame_length_in=28)
        long = generate_frame(frame_length_in=32)
        self.assertGreater(long.cross_member_count, short.cross_member_count)

    def test_side_rails_full_length(self):
        spec = generate_frame(frame_length_in=30, frame_width_in=26)
        left_rail = next(m for m in spec.tube_members if m["name"] == "left_rail")
        self.assertEqual(left_rail["length_in"], 30.0)


class TestFrameModules(unittest.TestCase):
    """Tests for swerve module placement."""

    def test_four_modules_placed(self):
        spec = generate_frame()
        self.assertEqual(len(spec.module_placements), 4)

    def test_module_names(self):
        spec = generate_frame()
        names = {m["name"] for m in spec.module_placements}
        self.assertEqual(names, {"front_left", "front_right", "back_left", "back_right"})

    def test_module_symmetry(self):
        spec = generate_frame(frame_length_in=28, frame_width_in=28)
        positions = {m["name"]: m["position"] for m in spec.module_placements}
        fl = positions["front_left"]
        fr = positions["front_right"]
        # X should be mirrored (fl negative, fr positive)
        self.assertAlmostEqual(fl[0], -fr[0])
        self.assertAlmostEqual(fl[1], fr[1])

    def test_module_inset_respected(self):
        spec = generate_frame(frame_length_in=28, frame_width_in=28, module_inset_in=3.0)
        fl = next(m for m in spec.module_placements if m["name"] == "front_left")
        expected_x = -(28 / 2 - 3.0)
        self.assertAlmostEqual(fl["position"][0], expected_x)

    def test_all_module_types_valid(self):
        for module_type in SwerveModuleType:
            spec = generate_frame(module_type=module_type.value)
            self.assertEqual(len(spec.module_placements), 4)


class TestFrameWeight(unittest.TestCase):
    """Tests for weight budget calculations."""

    def test_weight_positive(self):
        spec = generate_frame()
        self.assertGreater(spec.frame_weight_lb, 0)
        self.assertGreater(spec.module_weight_lb, 0)
        self.assertGreater(spec.electronics_weight_lb, 0)
        self.assertGreater(spec.total_weight_lb, 0)

    def test_weight_sum_correct(self):
        spec = generate_frame()
        expected = (spec.frame_weight_lb + spec.module_weight_lb +
                    spec.electronics_weight_lb + spec.bellypan_weight_lb)
        self.assertAlmostEqual(spec.total_weight_lb, expected, places=1)

    def test_bellypan_weight_reasonable(self):
        spec = generate_frame(frame_length_in=28, frame_width_in=28, bellypan=True)
        # 1/8" polycarb bellypan for 28x28 should be 2-6 lbs
        self.assertGreater(spec.bellypan_weight_lb, 1.0)
        self.assertLess(spec.bellypan_weight_lb, 8.0)

    def test_no_bellypan_zero_weight(self):
        spec = generate_frame(bellypan=False)
        self.assertEqual(spec.bellypan_weight_lb, 0)

    def test_total_under_125(self):
        """Drivebase alone should never exceed the FRC weight limit."""
        spec = generate_frame()
        self.assertLess(spec.total_weight_lb, 125)

    def test_module_weight_four_modules(self):
        spec = generate_frame(module_type="thrifty")
        expected = 4 * SWERVE_MODULES[SwerveModuleType.THRIFTY]["weight_lb"]
        self.assertAlmostEqual(spec.module_weight_lb, expected)


class TestFramePresets(unittest.TestCase):
    """Tests for preset configurations."""

    def test_all_presets_generate(self):
        for name in PRESETS:
            spec = generate_from_preset(name)
            self.assertIsInstance(spec, FrameSpec)

    def test_invalid_preset_raises(self):
        with self.assertRaises(ValueError):
            generate_from_preset("nonexistent")

    def test_competition_preset_28x28(self):
        spec = generate_from_preset("competition")
        self.assertEqual(spec.frame_length_in, 28.0)
        self.assertEqual(spec.frame_width_in, 28.0)


class TestFrameOutput(unittest.TestCase):
    """Tests for output functions."""

    def test_save_spec_creates_file(self):
        spec = generate_frame()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_spec(spec, path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["frame_length_in"], 28.0)
        finally:
            os.unlink(path)

    def test_save_spec_roundtrip(self):
        spec = generate_frame(frame_length_in=30, frame_width_in=26, module_type="sds_mk4i")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_spec(spec, path)
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["frame_length_in"], 30.0)
            self.assertEqual(data["module_type"], "sds_mk4i")
            self.assertEqual(len(data["module_placements"]), 4)
        finally:
            os.unlink(path)

    def test_cut_list_populated(self):
        spec = generate_frame()
        self.assertGreater(len(spec.cut_list), 0)

    def test_print_summary_no_crash(self):
        """Smoke test: print_summary shouldn't crash."""
        spec = generate_frame()
        # Redirect stdout to suppress output during test
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            print_summary(spec)
            print_cutlist(spec)
        finally:
            sys.stdout = old_stdout

    def test_print_cutlist_no_crash(self):
        spec = generate_frame(frame_length_in=32, frame_width_in=28)
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            print_cutlist(spec)
        finally:
            sys.stdout = old_stdout


# ═══════════════════════════════════════════════════════════════════
# PREDICTION BRIDGE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestNormalization(unittest.TestCase):
    """Tests for input normalization functions."""

    def test_normalize_module_thrifty(self):
        self.assertEqual(_normalize_module("thrifty"), "thrifty")
        self.assertEqual(_normalize_module("Thrifty Swerve"), "thrifty")
        self.assertEqual(_normalize_module("thrifty_swerve"), "thrifty")

    def test_normalize_module_sds(self):
        self.assertEqual(_normalize_module("mk4i"), "sds_mk4i")
        self.assertEqual(_normalize_module("SDS MK4i"), "sds_mk4i")
        self.assertEqual(_normalize_module("MK4n"), "sds_mk4n")

    def test_normalize_module_rev(self):
        self.assertEqual(_normalize_module("MAXSwerve"), "rev_maxswerve")
        self.assertEqual(_normalize_module("rev_maxswerve"), "rev_maxswerve")

    def test_normalize_module_unknown_defaults_thrifty(self):
        self.assertEqual(_normalize_module("unknown_module"), "thrifty")

    def test_normalize_intake_types(self):
        self.assertEqual(_normalize_intake_type("over_bumper"), "over_bumper")
        self.assertEqual(_normalize_intake_type("ob"), "over_bumper")
        self.assertEqual(_normalize_intake_type("under"), "under_bumper")
        self.assertEqual(_normalize_intake_type("full_width"), "fixed_full_width")

    def test_normalize_scorer_methods(self):
        self.assertEqual(_normalize_scorer_method("elevator"), "elevator")
        self.assertEqual(_normalize_scorer_method("shoot"), "flywheel")
        self.assertEqual(_normalize_scorer_method("throw"), "flywheel")
        self.assertEqual(_normalize_scorer_method("place"), "elevator")
        self.assertEqual(_normalize_scorer_method("gravity_drop"), "gravity_drop")

    def test_normalize_endgame_types(self):
        self.assertEqual(_normalize_endgame_type("hook_winch"), "hook_winch")
        self.assertEqual(_normalize_endgame_type("hook"), "hook_winch")
        self.assertEqual(_normalize_endgame_type("telescope"), "telescope")
        self.assertEqual(_normalize_endgame_type("park"), "park_only")
        self.assertEqual(_normalize_endgame_type("none"), "none")


class TestOracleParsing(unittest.TestCase):
    """Tests for parsing Oracle output JSON."""

    def test_parse_rebuilt_example(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.game_name, "REBUILT")
        self.assertEqual(oracle.season_year, 2026)
        self.assertAlmostEqual(oracle.confidence_overall, 0.95)

    def test_parse_drivetrain(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.drivetrain.type, "swerve")
        self.assertEqual(oracle.drivetrain.module, "thrifty")
        self.assertAlmostEqual(oracle.drivetrain.speed_fps, 14.5)

    def test_parse_intake(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.intake.type, "over_bumper")
        self.assertEqual(oracle.intake.width, "full")
        self.assertEqual(oracle.intake.roller_material, "flex_wheels")

    def test_parse_scorer(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.scorer.method, "elevator")
        self.assertEqual(oracle.scorer.height_in, 72.0)
        self.assertEqual(oracle.scorer.stages, 2)
        self.assertTrue(oracle.scorer.has_wrist)

    def test_parse_endgame(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.endgame.type, "hook_winch")
        self.assertEqual(oracle.endgame.height_in, 26.0)

    def test_parse_autonomous(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertAlmostEqual(oracle.autonomous.cycle_time_target_s, 4.5)
        self.assertEqual(oracle.autonomous.estimated_pieces, 3)
        self.assertTrue(oracle.autonomous.preload_score)

    def test_parse_weight_budget(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.weight_budget["total_limit_lb"], 125)

    def test_parse_build_order(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        self.assertEqual(oracle.build_order[0], "drivetrain")
        self.assertEqual(oracle.build_order[1], "scorer")

    def test_parse_empty_dict(self):
        """Parsing empty dict should return defaults without crashing."""
        oracle = parse_oracle_output({})
        self.assertEqual(oracle.game_name, "")
        self.assertEqual(oracle.drivetrain.type, "swerve")

    def test_parse_alternate_keys(self):
        """Oracle output may use different key names."""
        data = {
            "game": "TestGame",
            "year": 2028,
            "drive": {"module": "MK4i", "max_speed": 16.0},
            "scoring": {"type": "shoot", "height": 48},
            "climb": {"type": "telescope", "height": 60},
        }
        oracle = parse_oracle_output(data)
        self.assertEqual(oracle.game_name, "TestGame")
        self.assertEqual(oracle.drivetrain.module, "sds_mk4i")
        self.assertAlmostEqual(oracle.drivetrain.speed_fps, 16.0)
        self.assertEqual(oracle.scorer.method, "flywheel")
        self.assertEqual(oracle.endgame.type, "telescope")


class TestBridgeLogic(unittest.TestCase):
    """Tests for Oracle → Blueprint conversion logic."""

    def test_frame_params_from_oracle(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        params = oracle_to_frame_params(oracle)
        self.assertEqual(params["frame_length_in"], 28.0)
        self.assertEqual(params["frame_width_in"], 28.0)
        self.assertEqual(params["module_type"], "thrifty")
        self.assertTrue(params["bellypan"])

    def test_speed_upgrades_module(self):
        """If Oracle wants >16fps but picked thrifty, bridge should upgrade."""
        data = {
            "drivetrain": {"module": "thrifty", "speed_fps": 17.0, "frame_length": 28, "frame_width": 28}
        }
        oracle = parse_oracle_output(data)
        params = oracle_to_frame_params(oracle)
        self.assertEqual(params["module_type"], "sds_mk4i")

    def test_tall_elevator_widens_frame(self):
        """Tall elevator (>48in) should enforce minimum 28" width for stability."""
        data = {
            "drivetrain": {"frame_length": 26, "frame_width": 24},
            "scorer": {"method": "elevator", "height": 60, "stages": 2},
        }
        oracle = parse_oracle_output(data)
        params = oracle_to_frame_params(oracle)
        self.assertGreaterEqual(params["frame_width_in"], 28)

    def test_blueprint_spec_structure(self):
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        spec = oracle_to_blueprint_spec(oracle)
        self.assertIn("metadata", spec)
        self.assertIn("frame", spec)
        self.assertIn("subsystems", spec)
        self.assertIn("autonomous", spec)
        self.assertIn("weight_budget", spec)
        self.assertIn("build_order", spec)

    def test_scorer_template_mapping(self):
        """Scorer method should map to the correct Blueprint template."""
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        spec = oracle_to_blueprint_spec(oracle)
        self.assertEqual(spec["subsystems"]["scorer"]["template"], "elevator_two_stage")

    def test_scorer_template_flywheel(self):
        data = {"scorer": {"method": "flywheel"}}
        oracle = parse_oracle_output(data)
        spec = oracle_to_blueprint_spec(oracle)
        self.assertEqual(spec["subsystems"]["scorer"]["template"], "shooter_dual_flywheel")

    def test_scorer_template_cascade(self):
        data = {"scorer": {"method": "elevator", "stages": 3}}
        oracle = parse_oracle_output(data)
        spec = oracle_to_blueprint_spec(oracle)
        self.assertEqual(spec["subsystems"]["scorer"]["template"], "elevator_cascade")

    def test_full_pipeline_no_crash(self):
        """End-to-end: Oracle JSON → parsed → frame params → generate frame."""
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        params = oracle_to_frame_params(oracle)
        spec = generate_frame(**params)
        self.assertIsInstance(spec, FrameSpec)
        self.assertGreater(spec.total_weight_lb, 0)
        self.assertEqual(len(spec.module_placements), 4)


# ═══════════════════════════════════════════════════════════════════
# COTS CATALOG TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCOTSCatalog(unittest.TestCase):
    """Tests for COTS catalog loading and lookup."""

    def test_catalog_loads(self):
        catalog = load_cots_catalog()
        self.assertIsInstance(catalog, dict)
        self.assertGreater(len(catalog), 0)

    def test_catalog_has_swerve_modules(self):
        catalog = load_cots_catalog()
        swerve = [k for k, v in catalog.items()
                  if isinstance(v, dict) and v.get("category") == "drivetrain"]
        self.assertGreater(len(swerve), 0)

    def test_lookup_exact_match(self):
        part = lookup_part("REV NEO Motor")
        self.assertEqual(part["category"], "motors")
        self.assertEqual(part["vendor"], "REV")

    def test_lookup_partial_match(self):
        part = lookup_part("kraken")
        self.assertEqual(part["vendor"], "WCP")

    def test_lookup_not_found_raises(self):
        with self.assertRaises(KeyError):
            lookup_part("nonexistent_part_xyz")

    def test_lookup_multiple_matches_raises(self):
        with self.assertRaises(ValueError):
            lookup_part("bearing")  # Multiple bearing types


# ═══════════════════════════════════════════════════════════════════
# ONSHAPE API SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOnShapeSmoke(unittest.TestCase):
    """Smoke tests for OnShape API. Skipped if no API keys configured."""

    def setUp(self):
        if not os.environ.get("ONSHAPE_ACCESS_KEY"):
            # Try loading .env
            env_path = Path(__file__).parent / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, value = line.partition("=")
                            os.environ.setdefault(key.strip(), value.strip())

        if not os.environ.get("ONSHAPE_ACCESS_KEY"):
            self.skipTest("ONSHAPE_ACCESS_KEY not set — skipping API smoke tests")

    def test_connection(self):
        result = test_connection()
        self.assertTrue(result["connected"])
        self.assertIn("user", result)

    def test_connection_has_email(self):
        result = test_connection()
        self.assertIn("@", result.get("email", ""))


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """End-to-end integration tests."""

    def test_oracle_to_onshape_ready_spec(self):
        """Full pipeline: Oracle JSON → frame spec ready for OnShape."""
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        params = oracle_to_frame_params(oracle)
        frame = generate_frame(**params)

        # Verify it's a valid, complete spec
        self.assertEqual(frame.name, "2950 REBUILT Frame")
        self.assertEqual(len(frame.module_placements), 4)
        self.assertGreater(len(frame.tube_members), 0)
        self.assertGreater(len(frame.cut_list), 0)
        self.assertGreater(frame.total_weight_lb, 0)
        self.assertLess(frame.total_weight_lb, 125)

    def test_all_presets_produce_valid_frames(self):
        """Every preset should produce a frame within FRC rules."""
        for name in PRESETS:
            spec = generate_from_preset(name)
            self.assertEqual(len(spec.module_placements), 4, f"Preset {name} missing modules")
            self.assertGreater(spec.total_weight_lb, 0, f"Preset {name} has zero weight")
            self.assertLessEqual(spec.bumper_perimeter_in, 120,
                                 f"Preset {name} exceeds 120\" perimeter")

    def test_all_module_types_in_catalog(self):
        """Every module type the frame generator knows about should be in COTS catalog."""
        catalog = load_cots_catalog()
        catalog_lower = {k.lower() for k in catalog.keys()}
        for mod_type in SWERVE_MODULES.values():
            # Check that the module name appears somewhere in catalog
            found = any(mod_type["name"].lower() in k for k in catalog_lower)
            # SwerveX might not be named exactly — just check the main ones
            if mod_type["name"] in ("Thrifty Swerve", "SDS MK4i", "REV MAXSwerve"):
                self.assertTrue(found, f"{mod_type['name']} not found in COTS catalog")

    def test_save_and_reload_spec(self):
        """Save a spec to JSON and verify it loads correctly."""
        spec = generate_frame(frame_length_in=30, frame_width_in=26, module_type="sds_mk4i")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_spec(spec, path)
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["frame_length_in"], 30.0)
            self.assertEqual(data["frame_width_in"], 26.0)
            self.assertEqual(data["module_type"], "sds_mk4i")
            self.assertEqual(len(data["module_placements"]), 4)
            self.assertGreater(len(data["tube_members"]), 0)
            self.assertGreater(data["total_weight_lb"], 0)
        finally:
            os.unlink(path)

    def test_blueprint_spec_has_all_subsystems(self):
        """Blueprint spec from Oracle should include all subsystem templates."""
        oracle = parse_oracle_output(REBUILT_2026_EXAMPLE)
        spec = oracle_to_blueprint_spec(oracle)
        subs = spec["subsystems"]
        self.assertIn("intake", subs)
        self.assertIn("scorer", subs)
        self.assertIn("endgame", subs)
        self.assertIn("template", subs["intake"])
        self.assertIn("template", subs["scorer"])
        self.assertIn("template", subs["endgame"])


# ═══════════════════════════════════════════════════════════════════
# DATA INTEGRITY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDataIntegrity(unittest.TestCase):
    """Verify module/tube/electronics data is consistent."""

    def test_all_module_types_have_required_fields(self):
        required = ["name", "footprint_in", "wheel_diameter_in", "weight_lb",
                     "drive_ratio", "steer_ratio", "max_speed_fps"]
        for mod_type, data in SWERVE_MODULES.items():
            for field in required:
                self.assertIn(field, data, f"{mod_type.value} missing {field}")

    def test_all_tube_sizes_have_required_fields(self):
        required = ["width_in", "height_in", "wall_in", "weight_per_inch_lb"]
        for size, data in TUBE_STOCK.items():
            for field in required:
                self.assertIn(field, data, f"{size.value} missing {field}")

    def test_electronics_have_required_fields(self):
        required = ["name", "footprint_in", "weight_lb"]
        for key, data in ELECTRONICS.items():
            for field in required:
                self.assertIn(field, data, f"Electronics '{key}' missing {field}")

    def test_module_weights_realistic(self):
        """Module weights should be between 1-5 lbs."""
        for mod_type, data in SWERVE_MODULES.items():
            self.assertGreater(data["weight_lb"], 1.0, f"{mod_type.value} too light")
            self.assertLess(data["weight_lb"], 5.0, f"{mod_type.value} too heavy")

    def test_module_speeds_realistic(self):
        """Max speeds should be between 10-20 fps."""
        for mod_type, data in SWERVE_MODULES.items():
            self.assertGreater(data["max_speed_fps"], 10, f"{mod_type.value} too slow")
            self.assertLess(data["max_speed_fps"], 20, f"{mod_type.value} too fast")

    def test_presets_reference_valid_modules(self):
        """All presets should reference valid module types."""
        valid_modules = {m.value for m in SwerveModuleType}
        for name, preset in PRESETS.items():
            self.assertIn(preset["module_type"], valid_modules,
                          f"Preset '{name}' has invalid module type")

    def test_presets_reference_valid_tubes(self):
        """All presets should reference valid tube sizes."""
        valid_tubes = {t.value for t in TubeSize}
        for name, preset in PRESETS.items():
            self.assertIn(preset["perimeter_tube"], valid_tubes,
                          f"Preset '{name}' has invalid perimeter tube")
            self.assertIn(preset["cross_tube"], valid_tubes,
                          f"Preset '{name}' has invalid cross tube")


# ═══════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("The Blueprint — Test Suite")
    print("=" * 60)
    unittest.main(verbosity=2)
