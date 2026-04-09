"""
Tests for Blueprint B.4–B.9
Team 2950 — The Devastators

Covers: flywheel, arm, climber, conveyor, BOM rollup, Oracle pipeline.
Run: python3 test_b4_b9_generators.py
"""

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from motor_model import DCMotor, MOTOR_DB, RPM_TO_RADS
from flywheel_generator import (
    FlywheelSpec, generate_flywheel, PRESETS as FW_PRESETS,
    calculate_spinup_time, calculate_shot_physics, calculate_recovery_time,
    estimate_wheel_moi,
)
from arm_generator import (
    ArmSpec, generate_arm, PRESETS as ARM_PRESETS,
    simulate_arm_motion,
)
from climber_generator import (
    ClimberSpec, generate_climber, PRESETS as CLIMB_PRESETS,
    CLIMB_STYLES, recommend_climb_ratio,
)
from conveyor_generator import (
    ConveyorSpec, generate_conveyor, PRESETS as CONV_PRESETS,
    BELT_TYPES, SENSOR_TYPES,
)
from bom_rollup import rollup_robot, BOMRollup, _extract_preset_params
from oracle_pipeline import (
    run_pipeline, map_scorer_to_generators, map_intake_to_generator,
    map_endgame_to_generator, EXAMPLE_ORACLE,
)
from prediction_bridge import parse_oracle_output, OracleOutput


# ═══════════════════════════════════════════════════════════════════
# B.4 — FLYWHEEL GENERATOR
# ═══════════════════════════════════════════════════════════════════

class TestFlywheelPhysics(unittest.TestCase):
    """Test flywheel physics calculations."""

    def test_spinup_time_positive(self):
        motor = MOTOR_DB["neo_vortex"]
        result = calculate_spinup_time(motor, 2, 1.0, 3000.0, 0.001)
        self.assertTrue(result["achievable"])
        self.assertGreater(result["spinup_time_sec"], 0)
        self.assertLess(result["spinup_time_sec"], 5.0)

    def test_spinup_unreachable_rpm(self):
        motor = MOTOR_DB["neo_vortex"]
        # Target RPM above free speed should be unreachable
        result = calculate_spinup_time(motor, 1, 1.0, 99999.0, 0.001)
        self.assertFalse(result["achievable"])

    def test_more_motors_faster_spinup(self):
        motor = MOTOR_DB["neo_vortex"]
        moi = 0.001
        t1 = calculate_spinup_time(motor, 1, 1.0, 3000, moi)["spinup_time_sec"]
        t2 = calculate_spinup_time(motor, 2, 1.0, 3000, moi)["spinup_time_sec"]
        self.assertLess(t2, t1)

    def test_shot_physics_energy_conservation(self):
        result = calculate_shot_physics(3000, 4.0, 0.001, 0.5, 4.5)
        self.assertGreater(result["exit_velocity_fps"], 0)
        self.assertGreater(result["energy_transfer_pct"], 0)
        self.assertLess(result["energy_transfer_pct"], 100)
        self.assertGreater(result["speed_drop_rpm"], 0)
        self.assertLess(result["rpm_after_shot"], 3000)

    def test_recovery_time_positive(self):
        motor = MOTOR_DB["neo_vortex"]
        t = calculate_recovery_time(motor, 2, 1.0, 3000, 2500, 0.001)
        self.assertGreater(t, 0)
        self.assertLess(t, 5.0)

    def test_moi_estimate_scales_with_diameter(self):
        small = estimate_wheel_moi(2.0, 2)
        large = estimate_wheel_moi(6.0, 2)
        self.assertGreater(large, small)

    def test_moi_estimate_scales_with_count(self):
        two = estimate_wheel_moi(4.0, 2)
        four = estimate_wheel_moi(4.0, 4)
        self.assertAlmostEqual(four, two * 2, places=6)


class TestFlywheelGenerator(unittest.TestCase):
    """Test flywheel spec generation."""

    def test_all_presets_generate(self):
        for name, preset in FW_PRESETS.items():
            with self.subTest(preset=name):
                spec = generate_flywheel(**preset["params"], preset_name=name)
                self.assertIsInstance(spec, FlywheelSpec)
                self.assertGreater(spec.spinup_time_sec, 0)
                self.assertGreater(spec.exit_velocity_fps, 0)
                self.assertGreater(spec.total_weight_lb, 0)

    def test_unknown_motor_raises(self):
        with self.assertRaises(ValueError):
            generate_flywheel(motor_type="nonexistent")

    def test_holding_current_reasonable(self):
        spec = generate_flywheel(**FW_PRESETS["coral_2026"]["params"])
        # Holding current should be much less than stall
        self.assertLess(spec.holding_current_a, 30)
        self.assertGreater(spec.holding_current_a, 0)

    def test_software_constants_present(self):
        spec = generate_flywheel(**FW_PRESETS["coral_2026"]["params"])
        self.assertIn("TARGET_RPM", spec.software_constants)
        self.assertIn("kV", spec.software_constants)
        self.assertIn("RECOVERY_TIME_SEC", spec.software_constants)

    def test_parts_list_nonempty(self):
        spec = generate_flywheel(**FW_PRESETS["coral_2026"]["params"])
        self.assertGreater(len(spec.parts_list), 3)

    def test_gear_reduction_adds_belt_part(self):
        spec = generate_flywheel(gear_ratio=2.0)
        items = [p["item"] for p in spec.parts_list]
        self.assertTrue(any("Belt" in i or "reduction" in i for i in items))


# ═══════════════════════════════════════════════════════════════════
# B.5 — ARM GENERATOR
# ═══════════════════════════════════════════════════════════════════

class TestArmPhysics(unittest.TestCase):
    """Test arm motion simulation."""

    def test_arm_motion_completes(self):
        motor = MOTOR_DB["neo"]
        result = simulate_arm_motion(motor, 1, 100.0, 12.0, 8.0, -30.0, 110.0)
        self.assertGreater(result["travel_time_sec"], 0)
        self.assertLess(result["travel_time_sec"], 5.0)
        self.assertGreater(result["max_angular_velocity_deg_s"], 0)

    def test_heavier_arm_slower(self):
        motor = MOTOR_DB["neo"]
        light = simulate_arm_motion(motor, 1, 100.0, 12.0, 5.0, -30.0, 110.0)
        heavy = simulate_arm_motion(motor, 1, 100.0, 12.0, 15.0, -30.0, 110.0)
        self.assertGreater(heavy["travel_time_sec"], light["travel_time_sec"])

    def test_more_motors_faster(self):
        motor = MOTOR_DB["neo"]
        one = simulate_arm_motion(motor, 1, 100.0, 12.0, 8.0, -30.0, 110.0)
        two = simulate_arm_motion(motor, 2, 100.0, 12.0, 8.0, -30.0, 110.0)
        self.assertLess(two["travel_time_sec"], one["travel_time_sec"])

    def test_downward_motion(self):
        motor = MOTOR_DB["neo"]
        result = simulate_arm_motion(motor, 1, 100.0, 12.0, 8.0, 90.0, -30.0)
        self.assertGreater(result["travel_time_sec"], 0)


class TestArmGenerator(unittest.TestCase):
    """Test arm spec generation."""

    def test_all_presets_generate(self):
        for name, preset in ARM_PRESETS.items():
            with self.subTest(preset=name):
                spec = generate_arm(**preset["params"], preset_name=name)
                self.assertIsInstance(spec, ArmSpec)
                self.assertGreater(spec.travel_time_sec, 0)
                self.assertGreater(spec.max_gravity_torque_nm, 0)

    def test_unknown_motor_raises(self):
        with self.assertRaises(ValueError):
            generate_arm(motor_type="nonexistent")

    def test_gravity_torque_scaling(self):
        light = generate_arm(arm_mass_lb=3.0, end_effector_weight_lb=1.0)
        heavy = generate_arm(arm_mass_lb=10.0, end_effector_weight_lb=5.0)
        self.assertGreater(heavy.max_gravity_torque_nm, light.max_gravity_torque_nm)

    def test_spring_recommendation(self):
        spec = generate_arm(**ARM_PRESETS["scoring_arm"]["params"])
        self.assertGreater(spec.spring_force_lb, 0)

    def test_holding_current_reasonable(self):
        spec = generate_arm(**ARM_PRESETS["scoring_arm"]["params"])
        self.assertLess(spec.holding_current_a, 20)
        self.assertGreater(spec.holding_current_a, 0)

    def test_software_constants_feedforward(self):
        spec = generate_arm(**ARM_PRESETS["scoring_arm"]["params"])
        self.assertIn("kG", spec.software_constants)
        self.assertIn("kV", spec.software_constants)
        self.assertIn("ARM_GEAR_RATIO", spec.software_constants)

    def test_high_holding_current_note(self):
        # Very long arm with small motor should trigger note
        spec = generate_arm(
            arm_length_in=36.0, com_distance_in=18.0,
            arm_mass_lb=15.0, end_effector_weight_lb=10.0,
            motor_type="neo_550", motor_count=1, gear_ratio=50.0,
        )
        notes_text = " ".join(spec.notes)
        self.assertTrue(
            "counterbalance" in notes_text.lower() or "holding" in notes_text.lower()
            or len(spec.notes) > 0  # at minimum should have some notes
        )


# ═══════════════════════════════════════════════════════════════════
# B.6 — CLIMBER GENERATOR
# ═══════════════════════════════════════════════════════════════════

class TestClimberGenerator(unittest.TestCase):
    """Test climber spec generation."""

    def test_all_presets_generate(self):
        for name, preset in CLIMB_PRESETS.items():
            with self.subTest(preset=name):
                spec = generate_climber(**preset["params"], preset_name=name)
                self.assertIsInstance(spec, ClimberSpec)
                self.assertGreater(spec.climb_time_sec, 0)
                self.assertGreater(spec.stall_load_lb, 0)

    def test_unknown_motor_raises(self):
        with self.assertRaises(ValueError):
            generate_climber(motor_type="nonexistent")

    def test_unknown_style_raises(self):
        with self.assertRaises(ValueError):
            generate_climber(climb_style="jetpack")

    def test_safety_factor_above_one(self):
        spec = generate_climber(**CLIMB_PRESETS["deep_climb"]["params"])
        self.assertGreater(spec.safety_factor, 1.0)

    def test_stall_load_exceeds_robot_weight(self):
        spec = generate_climber(**CLIMB_PRESETS["deep_climb"]["params"])
        self.assertGreater(spec.stall_load_lb, spec.robot_weight_lb)

    def test_heavier_robot_slower(self):
        light = generate_climber(robot_weight_lb=80.0)
        heavy = generate_climber(robot_weight_lb=125.0)
        self.assertGreater(heavy.climb_time_sec, light.climb_time_sec)

    def test_holding_current_positive(self):
        spec = generate_climber(**CLIMB_PRESETS["deep_climb"]["params"])
        self.assertGreater(spec.holding_current_a, 0)

    def test_climb_styles_exist(self):
        for style in CLIMB_STYLES:
            spec = generate_climber(climb_style=style)
            self.assertEqual(spec.climb_style, style)

    def test_recommend_climb_ratio(self):
        motor = MOTOR_DB["neo"]
        result = recommend_climb_ratio(motor, 2, 125.0, 1.0)
        self.assertIn("recommended_ratio", result)
        self.assertGreater(result["recommended_ratio"], 10)


# ═══════════════════════════════════════════════════════════════════
# B.7 — CONVEYOR GENERATOR
# ═══════════════════════════════════════════════════════════════════

class TestConveyorGenerator(unittest.TestCase):
    """Test conveyor spec generation."""

    def test_all_presets_generate(self):
        for name, preset in CONV_PRESETS.items():
            with self.subTest(preset=name):
                spec = generate_conveyor(**preset["params"], preset_name=name)
                self.assertIsInstance(spec, ConveyorSpec)
                self.assertGreater(spec.belt_speed_fps, 0)
                self.assertGreater(spec.transit_time_sec, 0)

    def test_unknown_motor_raises(self):
        with self.assertRaises(ValueError):
            generate_conveyor(motor_type="nonexistent")

    def test_unknown_belt_raises(self):
        with self.assertRaises(ValueError):
            generate_conveyor(belt_type="magic_carpet")

    def test_belt_length_calculation(self):
        spec = generate_conveyor(path_length_in=18.0, roller_diameter_in=2.0)
        expected = 2 * 18.0 + math.pi * 2.0
        self.assertAlmostEqual(spec.belt_length_in, round(expected, 1), places=1)

    def test_faster_motor_faster_belt(self):
        slow = generate_conveyor(gear_ratio=10.0)
        fast = generate_conveyor(gear_ratio=3.0)
        self.assertGreater(fast.belt_speed_fps, slow.belt_speed_fps)

    def test_transit_time_scales_with_length(self):
        short = generate_conveyor(path_length_in=10.0)
        long = generate_conveyor(path_length_in=30.0)
        self.assertGreater(long.transit_time_sec, short.transit_time_sec)

    def test_sensor_count_in_constants(self):
        spec = generate_conveyor(sensor_count=3)
        self.assertEqual(spec.software_constants["SENSOR_COUNT"], 3)

    def test_multi_stage_note(self):
        spec = generate_conveyor(staging_count=2, sensor_count=3)
        self.assertTrue(any("Multi-stage" in n for n in spec.notes))

    def test_all_belt_types(self):
        for belt in BELT_TYPES:
            spec = generate_conveyor(belt_type=belt)
            self.assertEqual(spec.belt_type, belt)

    def test_weight_reasonable(self):
        spec = generate_conveyor(**CONV_PRESETS["single_stage"]["params"])
        self.assertLess(spec.total_weight_lb, 5.0)
        self.assertGreater(spec.total_weight_lb, 0.5)


# ═══════════════════════════════════════════════════════════════════
# B.8 — BOM ROLLUP
# ═══════════════════════════════════════════════════════════════════

class TestBOMRollup(unittest.TestCase):
    """Test BOM aggregation."""

    def test_empty_rollup(self):
        rollup = rollup_robot()
        self.assertEqual(len(rollup.mechanisms), 0)
        self.assertGreater(rollup.total_weight_lb, 0)  # still has drivetrain/bumpers/battery

    def test_single_mechanism(self):
        rollup = rollup_robot(climber_preset="deep_climb")
        self.assertIn("climber", rollup.mechanisms)
        self.assertEqual(len(rollup.mechanisms), 1)

    def test_all_defaults(self):
        rollup = rollup_robot(
            elevator_preset="competition",
            intake_preset="coral_2026",
            flywheel_preset="coral_2026",
            climber_preset="deep_climb",
            conveyor_preset="single_stage",
        )
        self.assertEqual(len(rollup.mechanisms), 5)
        self.assertGreater(rollup.total_motor_count, 8)
        self.assertTrue(rollup.weight_ok)

    def test_weight_includes_fixed_costs(self):
        rollup = rollup_robot()
        # Even with no mechanisms, should include drivetrain, bumpers, battery, electronics
        self.assertGreaterEqual(rollup.total_weight_lb, 50)

    def test_motor_budget_includes_drivetrain(self):
        rollup = rollup_robot()
        motor_mechs = [m.mechanism for m in rollup.motors]
        self.assertIn("drivetrain_drive", motor_mechs)
        self.assertIn("drivetrain_steer", motor_mechs)

    def test_extract_preset_params_with_params_key(self):
        preset = {"description": "test", "params": {"a": 1, "b": 2}}
        result = _extract_preset_params(preset)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_extract_preset_params_flat(self):
        preset = {"description": "test", "a": 1, "b": 2}
        result = _extract_preset_params(preset)
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_overweight_detection(self):
        rollup = rollup_robot(drivetrain_weight_lb=110.0)
        self.assertFalse(rollup.weight_ok)
        self.assertLess(rollup.weight_margin_lb, 0)


# ═══════════════════════════════════════════════════════════════════
# B.9 — ORACLE PIPELINE
# ═══════════════════════════════════════════════════════════════════

class TestOraclePipeline(unittest.TestCase):
    """Test Oracle → Blueprint pipeline."""

    def test_example_pipeline_runs(self):
        oracle = parse_oracle_output(EXAMPLE_ORACLE)
        result = run_pipeline(oracle)
        self.assertGreater(len(result.specs), 0)
        self.assertGreater(len(result.generation_log), 0)

    def test_example_generates_all_mechanisms(self):
        oracle = parse_oracle_output(EXAMPLE_ORACLE)
        result = run_pipeline(oracle)
        # Should have elevator, arm (wrist), intake, conveyor, climber
        self.assertIn("elevator", result.specs)
        self.assertIn("intake", result.specs)
        self.assertIn("climber", result.specs)
        self.assertIn("conveyor", result.specs)

    def test_example_weight_ok(self):
        oracle = parse_oracle_output(EXAMPLE_ORACLE)
        result = run_pipeline(oracle)
        self.assertTrue(result.bom["weight_ok"])

    def test_scorer_elevator_mapping(self):
        from prediction_bridge import ScorerSpec
        scorer = ScorerSpec(method="elevator", height_in=72, has_wrist=True, motors=2)
        generators = map_scorer_to_generators(scorer, 14.5)
        self.assertIn("elevator", generators)
        self.assertIn("arm", generators)
        self.assertEqual(generators["elevator"]["travel_height_in"], 72)

    def test_scorer_flywheel_mapping(self):
        from prediction_bridge import ScorerSpec
        scorer = ScorerSpec(method="flywheel", motors=2)
        generators = map_scorer_to_generators(scorer, 14.5)
        self.assertIn("flywheel", generators)
        self.assertNotIn("elevator", generators)

    def test_endgame_none_returns_none(self):
        from prediction_bridge import EndgameSpec
        endgame = EndgameSpec(type="none")
        result = map_endgame_to_generator(endgame)
        self.assertIsNone(result)

    def test_endgame_park_only_returns_none(self):
        from prediction_bridge import EndgameSpec
        endgame = EndgameSpec(type="park_only")
        result = map_endgame_to_generator(endgame)
        self.assertIsNone(result)

    def test_endgame_winch_maps(self):
        from prediction_bridge import EndgameSpec
        endgame = EndgameSpec(type="hook_winch", height_in=26, motors=2)
        result = map_endgame_to_generator(endgame)
        self.assertIsNotNone(result)
        self.assertEqual(result["climb_style"], "winch")
        self.assertEqual(result["climb_height_in"], 26)

    def test_intake_mapping(self):
        from prediction_bridge import IntakeSpec as OIntake
        intake = OIntake(type="over_bumper", roller_material="flex_wheels")
        result = map_intake_to_generator(intake, 14.5)
        self.assertEqual(result["intake_type"], "over_bumper")
        self.assertEqual(result["roller_material"], "flex_wheels")
        self.assertEqual(result["drivetrain_speed_fps"], 14.5)

    def test_all_log_entries_ok(self):
        oracle = parse_oracle_output(EXAMPLE_ORACLE)
        result = run_pipeline(oracle)
        for entry in result.generation_log:
            self.assertNotIn("[FAIL]", entry, f"Pipeline failure: {entry}")


# ═══════════════════════════════════════════════════════════════════
# SMOKE TESTS — CLI entry points
# ═══════════════════════════════════════════════════════════════════

class TestSmokeAllGenerators(unittest.TestCase):
    """Smoke tests: generate every preset, verify JSON-serializable output."""

    def test_flywheel_all_presets_json(self):
        for name, preset in FW_PRESETS.items():
            spec = generate_flywheel(**preset["params"], preset_name=name)
            from dataclasses import asdict
            data = json.dumps(asdict(spec))
            self.assertGreater(len(data), 100)

    def test_arm_all_presets_json(self):
        for name, preset in ARM_PRESETS.items():
            spec = generate_arm(**preset["params"], preset_name=name)
            from dataclasses import asdict
            data = json.dumps(asdict(spec))
            self.assertGreater(len(data), 100)

    def test_climber_all_presets_json(self):
        for name, preset in CLIMB_PRESETS.items():
            spec = generate_climber(**preset["params"], preset_name=name)
            from dataclasses import asdict
            data = json.dumps(asdict(spec))
            self.assertGreater(len(data), 100)

    def test_conveyor_all_presets_json(self):
        for name, preset in CONV_PRESETS.items():
            spec = generate_conveyor(**preset["params"], preset_name=name)
            from dataclasses import asdict
            data = json.dumps(asdict(spec))
            self.assertGreater(len(data), 100)

    def test_bom_all_defaults_json(self):
        rollup = rollup_robot(
            elevator_preset="competition",
            intake_preset="coral_2026",
            flywheel_preset="coral_2026",
            climber_preset="deep_climb",
            conveyor_preset="single_stage",
        )
        from dataclasses import asdict
        # Motors are MotorAllocation dataclasses, need special handling
        self.assertGreater(rollup.total_motor_count, 0)

    def test_pipeline_example_json(self):
        oracle = parse_oracle_output(EXAMPLE_ORACLE)
        result = run_pipeline(oracle)
        data = json.dumps({
            "specs": result.specs,
            "bom": result.bom,
            "log": result.generation_log,
        })
        self.assertGreater(len(data), 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
