"""
Tests for Blueprint B.3 — Elevator Generator + Intake Generator
Team 2950 — The Devastators

Run: python3 test_b3_generators.py
"""

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from elevator_generator import (
    ElevatorSpec,
    MOTORS as ELEV_MOTORS,
    MotorType,
    RIGGING,
    TUBE_WALL,
    PULLEY_SPECS,
    BELT_SPECS,
    PRESETS as ELEV_PRESETS,
    recommend_gear_ratio,
    generate_elevator,
)

from intake_generator import (
    IntakeSpec,
    MOTORS as INTAKE_MOTORS,
    ROLLER_MATERIALS,
    INTAKE_TYPES,
    DEPLOY_TYPES,
    PRESETS as INTAKE_PRESETS,
    calculate_roller_config,
    recommend_roller_ratio,
    generate_intake,
)


def _elev_preset_params(name: str) -> dict:
    """Extract params from elevator preset, stripping 'description'."""
    p = ELEV_PRESETS[name].copy()
    p.pop("description", None)
    return p


# ═══════════════════════════════════════════════════════════════════
# ELEVATOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestElevatorGearRatio(unittest.TestCase):

    def test_kraken_48in_returns_ratio(self):
        result = recommend_gear_ratio(8.0, "kraken_x60", 2, 48.0)
        self.assertIn("recommended_ratio", result)
        self.assertGreater(result["recommended_ratio"], 0)

    def test_ratio_in_practical_range(self):
        result = recommend_gear_ratio(8.0, "kraken_x60", 2, 48.0)
        self.assertGreaterEqual(result["recommended_ratio"], 3.0)
        self.assertLessEqual(result["recommended_ratio"], 15.0)

    def test_heavier_load_valid(self):
        light = recommend_gear_ratio(3.0, "neo", 2, 48.0)
        heavy = recommend_gear_ratio(15.0, "neo", 2, 48.0)
        self.assertGreater(light["recommended_ratio"], 0)
        self.assertGreater(heavy["recommended_ratio"], 0)

    def test_travel_time_reported(self):
        result = recommend_gear_ratio(8.0, "kraken_x60", 2, 48.0)
        self.assertIn("travel_time_sec", result)
        self.assertGreater(result["travel_time_sec"], 0)

    def test_torque_margin_positive(self):
        result = recommend_gear_ratio(8.0, "kraken_x60", 2, 48.0)
        self.assertIn("torque_margin", result)
        self.assertGreater(result["torque_margin"], 1.0)

    def test_neo_valid(self):
        result = recommend_gear_ratio(8.0, "neo", 2, 48.0)
        self.assertGreater(result["recommended_ratio"], 0)

    def test_neo_vortex_valid(self):
        result = recommend_gear_ratio(8.0, "neo_vortex", 2, 48.0)
        self.assertGreater(result["recommended_ratio"], 0)


class TestElevatorGeneration(unittest.TestCase):

    def test_default_generates_spec(self):
        spec = generate_elevator()
        self.assertIsInstance(spec, ElevatorSpec)
        self.assertGreater(spec.total_weight_lb, 0)

    def test_travel_height_determines_stages(self):
        low = generate_elevator(travel_height_in=20.0)
        mid = generate_elevator(travel_height_in=48.0)
        tall = generate_elevator(travel_height_in=72.0)
        self.assertEqual(low.stage_count, 1)
        self.assertEqual(mid.stage_count, 2)
        self.assertEqual(tall.stage_count, 3)

    def test_tube_length_reasonable(self):
        spec = generate_elevator(travel_height_in=48.0)
        min_tube = spec.travel_height_in / spec.stage_count
        self.assertGreater(spec.tube_length_in, min_tube * 0.5)

    def test_belt_length_positive(self):
        spec = generate_elevator()
        self.assertGreater(spec.belt_length_in, 0)

    def test_spring_force_matches_gravity(self):
        spec = generate_elevator(end_effector_weight_lb=8.0)
        self.assertGreater(spec.spring_force_lb, 0)
        self.assertGreater(spec.spring_force_lb, spec.end_effector_weight_lb)

    def test_software_constants_present(self):
        spec = generate_elevator()
        self.assertIn("GEAR_RATIO", spec.software_constants)
        self.assertIn("MAX_HEIGHT_IN", spec.software_constants)
        self.assertIn("kG", spec.software_constants)

    def test_parts_list_nonempty(self):
        spec = generate_elevator()
        self.assertGreater(len(spec.parts_list), 5)

    def test_max_speed_positive(self):
        spec = generate_elevator()
        self.assertGreater(spec.max_speed_in_per_sec, 0)


class TestElevatorWeight(unittest.TestCase):

    def test_tube_weight_realistic_2stage(self):
        spec = generate_elevator(travel_height_in=48.0, tube_wall_in=0.0625)
        self.assertGreater(spec.tube_weight_lb, 3.0)
        self.assertLess(spec.tube_weight_lb, 10.0)

    def test_total_weight_under_target(self):
        spec = generate_elevator(travel_height_in=48.0)
        self.assertLess(spec.total_weight_lb, 25.0)

    def test_1_stage_lighter_than_2_stage(self):
        low = generate_elevator(travel_height_in=20.0)
        mid = generate_elevator(travel_height_in=48.0)
        self.assertLess(low.total_weight_lb, mid.total_weight_lb)

    def test_weight_components_sum_correctly(self):
        spec = generate_elevator()
        expected = round(
            spec.tube_weight_lb +
            spec.bearing_block_weight_lb +
            spec.belt_pulley_weight_lb +
            spec.motor_gearbox_weight_lb +
            spec.spring_weight_lb +
            spec.carriage_weight_lb +
            spec.hardware_weight_lb,
            2,
        )
        self.assertAlmostEqual(spec.total_weight_lb, expected, places=1)


class TestElevatorPresets(unittest.TestCase):

    def test_all_presets_generate(self):
        for name in ELEV_PRESETS:
            with self.subTest(preset=name):
                params = _elev_preset_params(name)
                spec = generate_elevator(**params)
                self.assertIsInstance(spec, ElevatorSpec)
                self.assertGreater(spec.total_weight_lb, 0)

    def test_competition_preset_passes_time(self):
        spec = generate_elevator(**_elev_preset_params("competition"))
        self.assertTrue(spec.travel_time_ok, f"Travel time {spec.full_travel_time_sec}s > 0.5s")

    def test_low_preset_is_single_stage(self):
        spec = generate_elevator(**_elev_preset_params("low"))
        self.assertEqual(spec.stage_count, 1)

    def test_cascade_preset_uses_cascade(self):
        spec = generate_elevator(**_elev_preset_params("cascade"))
        self.assertEqual(spec.rigging_type, "cascade")


class TestElevatorConstants(unittest.TestCase):

    def test_kraken_specs(self):
        motor = ELEV_MOTORS[MotorType.KRAKEN_X60]
        self.assertEqual(motor["free_speed_rpm"], 6000)
        self.assertGreater(motor["stall_torque_nm"], 5.0)

    def test_neo_specs(self):
        motor = ELEV_MOTORS[MotorType.NEO]
        self.assertEqual(motor["free_speed_rpm"], 5676)

    def test_tube_wall_weights(self):
        self.assertIn(0.0625, TUBE_WALL)
        self.assertIn(0.125, TUBE_WALL)
        self.assertGreater(
            TUBE_WALL[0.125]["weight_per_in"],
            TUBE_WALL[0.0625]["weight_per_in"],
        )

    def test_belt_specs_present(self):
        self.assertIn("9mm_htd3", BELT_SPECS)
        self.assertIn("15mm_htd3", BELT_SPECS)

    def test_pulley_circumference_positive(self):
        for name, pulley in PULLEY_SPECS.items():
            with self.subTest(pulley=name):
                self.assertGreater(pulley["circumference_in"], 0)


# ═══════════════════════════════════════════════════════════════════
# INTAKE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestIntakeRollerConfig(unittest.TestCase):

    def test_basic_config_returns_values(self):
        config = calculate_roller_config(4.5, 26.0, "flex_wheels", "over_bumper")
        self.assertGreater(config["intake_width_in"], 0)
        self.assertGreater(config["roller_count"], 0)
        self.assertGreater(config["compression_in"], 0)

    def test_full_width_intake_width(self):
        config = calculate_roller_config(4.5, 26.0, "flex_wheels", "over_bumper")
        self.assertEqual(config["intake_width_in"], 24.0)

    def test_over_bumper_has_2_plus_rollers(self):
        config = calculate_roller_config(4.5, 26.0, "flex_wheels", "over_bumper")
        self.assertGreaterEqual(config["roller_count"], 2)

    def test_full_width_has_1_roller(self):
        config = calculate_roller_config(4.5, 26.0, "flex_wheels", "fixed_full_width")
        self.assertEqual(config["roller_count"], 1)

    def test_under_bumper_has_2_rollers(self):
        config = calculate_roller_config(4.5, 26.0, "flex_wheels", "under_bumper")
        self.assertEqual(config["roller_count"], 2)

    def test_compression_proportional_to_material(self):
        flex = calculate_roller_config(4.5, 26.0, "flex_wheels", "over_bumper")
        compliant = calculate_roller_config(4.5, 26.0, "compliant_wheels", "over_bumper")
        self.assertGreater(compliant["compression_in"], flex["compression_in"])


class TestIntakeGearRatio(unittest.TestCase):

    def test_returns_valid_ratio(self):
        result = recommend_roller_ratio(4.5, 4.0, "neo", 15.0)
        self.assertGreater(result["gear_ratio"], 0)

    def test_surface_speed_near_target(self):
        result = recommend_roller_ratio(4.5, 4.0, "neo", 15.0)
        self.assertGreater(result["surface_speed_fps"], 10.0)
        self.assertLess(result["surface_speed_fps"], 25.0)

    def test_surface_speed_realistic(self):
        result = recommend_roller_ratio(4.5, 4.0, "neo", 15.0)
        self.assertLess(result["surface_speed_fps"], 30.0)

    def test_different_motors_valid(self):
        for motor_type in ["neo", "neo_550", "kraken_x60"]:
            with self.subTest(motor=motor_type):
                result = recommend_roller_ratio(4.5, 4.0, motor_type, 15.0)
                self.assertGreater(result["gear_ratio"], 0)
                self.assertLess(result["surface_speed_fps"], 30.0)


class TestIntakeGeneration(unittest.TestCase):

    def test_default_generates_spec(self):
        spec = generate_intake()
        self.assertIsInstance(spec, IntakeSpec)
        self.assertGreater(spec.total_weight_lb, 0)

    def test_over_bumper_has_deploy(self):
        spec = generate_intake(intake_type="over_bumper")
        self.assertEqual(spec.deploy_type, "pivot")
        self.assertGreater(spec.deploy_weight_lb, 0)

    def test_under_bumper_no_deploy(self):
        spec = generate_intake(intake_type="under_bumper")
        self.assertEqual(spec.deploy_type, "none")
        self.assertEqual(spec.deploy_weight_lb, 0)

    def test_fixed_no_deploy(self):
        spec = generate_intake(intake_type="fixed_full_width")
        self.assertEqual(spec.deploy_type, "none")

    def test_software_constants_present(self):
        spec = generate_intake()
        self.assertIn("ROLLER_GEAR_RATIO", spec.software_constants)
        self.assertIn("INTAKE_SPEED", spec.software_constants)
        self.assertIn("OUTTAKE_SPEED", spec.software_constants)

    def test_deploy_constants_when_deployed(self):
        spec = generate_intake(intake_type="over_bumper")
        self.assertIn("DEPLOY_GEAR_RATIO", spec.software_constants)
        self.assertIn("DEPLOY_ANGLE_DEG", spec.software_constants)

    def test_no_deploy_constants_when_fixed(self):
        spec = generate_intake(intake_type="fixed_full_width")
        self.assertNotIn("DEPLOY_GEAR_RATIO", spec.software_constants)

    def test_parts_list_nonempty(self):
        spec = generate_intake()
        self.assertGreater(len(spec.parts_list), 3)

    def test_acquire_time_positive(self):
        spec = generate_intake()
        self.assertGreater(spec.acquire_time_sec, 0)

    def test_notes_contain_r2_or_r3(self):
        spec = generate_intake(roller_material="flex_wheels", frame_width_in=26.0)
        notes_text = " ".join(spec.notes)
        self.assertTrue("R2" in notes_text or "R3" in notes_text)


class TestIntakeWeight(unittest.TestCase):

    def test_total_under_10lb(self):
        spec = generate_intake()
        self.assertLess(spec.total_weight_lb, 10.0)

    def test_weight_components_sum(self):
        spec = generate_intake()
        expected = round(
            spec.roller_weight_lb +
            spec.frame_weight_lb +
            spec.motor_weight_lb +
            spec.deploy_weight_lb +
            spec.hardware_weight_lb,
            2,
        )
        self.assertAlmostEqual(spec.total_weight_lb, expected, places=1)

    def test_fixed_lighter_than_over_bumper(self):
        fixed = generate_intake(intake_type="fixed_full_width")
        over = generate_intake(intake_type="over_bumper")
        self.assertLess(fixed.total_weight_lb, over.total_weight_lb)


class TestIntakePresets(unittest.TestCase):

    def test_all_presets_generate(self):
        for name in INTAKE_PRESETS:
            with self.subTest(preset=name):
                spec = generate_intake(**INTAKE_PRESETS[name]["params"], preset_name=name)
                self.assertIsInstance(spec, IntakeSpec)
                self.assertGreater(spec.total_weight_lb, 0)

    def test_all_presets_under_weight(self):
        for name in INTAKE_PRESETS:
            with self.subTest(preset=name):
                spec = generate_intake(**INTAKE_PRESETS[name]["params"], preset_name=name)
                self.assertTrue(spec.weight_ok, f"{name} weight {spec.total_weight_lb} > 10 lb")

    def test_coral_2026_uses_flex_wheels(self):
        spec = generate_intake(**INTAKE_PRESETS["coral_2026"]["params"])
        self.assertEqual(spec.roller_material, "flex_wheels")

    def test_small_piece_uses_green_wheels(self):
        spec = generate_intake(**INTAKE_PRESETS["small_piece"]["params"])
        self.assertEqual(spec.roller_material, "green_wheels")


class TestIntakeValidation(unittest.TestCase):

    def test_invalid_intake_type_raises(self):
        with self.assertRaises(ValueError):
            generate_intake(intake_type="nonexistent")

    def test_invalid_roller_material_raises(self):
        with self.assertRaises(ValueError):
            generate_intake(roller_material="nonexistent")

    def test_invalid_motor_raises(self):
        with self.assertRaises(ValueError):
            generate_intake(roller_motor_type="nonexistent")

    def test_invalid_deploy_type_raises(self):
        with self.assertRaises(ValueError):
            generate_intake(deploy_type="nonexistent")


# ═══════════════════════════════════════════════════════════════════
# SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestElevatorSmoke(unittest.TestCase):

    def test_all_presets_produce_json(self):
        from dataclasses import asdict
        for name in ELEV_PRESETS:
            with self.subTest(preset=name):
                params = _elev_preset_params(name)
                spec = generate_elevator(**params)
                data = asdict(spec)
                json_str = json.dumps(data)
                self.assertGreater(len(json_str), 100)

    def test_custom_params_work(self):
        spec = generate_elevator(
            travel_height_in=36.0,
            end_effector_weight_lb=5.0,
            motor_type="neo",
            motor_count=1,
        )
        self.assertEqual(spec.travel_height_in, 36.0)
        self.assertEqual(spec.end_effector_weight_lb, 5.0)


class TestIntakeSmoke(unittest.TestCase):

    def test_all_presets_produce_json(self):
        from dataclasses import asdict
        for name in INTAKE_PRESETS:
            with self.subTest(preset=name):
                params = INTAKE_PRESETS[name]["params"].copy()
                spec = generate_intake(**params, preset_name=name)
                data = asdict(spec)
                json_str = json.dumps(data)
                self.assertGreater(len(json_str), 100)

    def test_custom_params_work(self):
        spec = generate_intake(
            intake_type="under_bumper",
            game_piece_diameter_in=3.0,
            frame_width_in=28.0,
            roller_material="green_wheels",
            roller_motor_type="neo_550",
        )
        self.assertEqual(spec.intake_type, "under_bumper")
        self.assertEqual(spec.frame_width_in, 28.0)

    def test_all_roller_materials(self):
        for material in ROLLER_MATERIALS:
            with self.subTest(material=material):
                spec = generate_intake(roller_material=material)
                self.assertEqual(spec.roller_material, material)
                self.assertGreater(spec.total_weight_lb, 0)

    def test_all_intake_types(self):
        for itype in INTAKE_TYPES:
            with self.subTest(type=itype):
                spec = generate_intake(intake_type=itype)
                self.assertEqual(spec.intake_type, itype)


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):

    def test_combined_weight_under_budget(self):
        elevator = generate_elevator(**_elev_preset_params("competition"))
        intake = generate_intake(**INTAKE_PRESETS["coral_2026"]["params"])
        combined = elevator.total_weight_lb + intake.total_weight_lb
        self.assertLess(combined, 45.0, f"Combined weight {combined} lb exceeds 45 lb mechanism budget")

    def test_elevator_and_intake_specs_serialize(self):
        from dataclasses import asdict
        elevator = generate_elevator(**_elev_preset_params("competition"))
        intake = generate_intake(**INTAKE_PRESETS["coral_2026"]["params"])
        combined = {"elevator": asdict(elevator), "intake": asdict(intake)}
        json_str = json.dumps(combined)
        self.assertGreater(len(json_str), 200)


# ═══════════════════════════════════════════════════════════════════
# PHYSICS MODEL TESTS (ReCalc-derived)
# ═══════════════════════════════════════════════════════════════════

class TestDCMotorModel(unittest.TestCase):
    """Test the shared DC motor physics model."""

    def test_motor_constants_derived(self):
        from motor_model import MOTOR_DB
        m = MOTOR_DB["kraken_x60"]
        self.assertGreater(m.R, 0)
        self.assertGreater(m.kV, 0)
        self.assertGreater(m.kT, 0)
        self.assertGreater(m.b, 0)

    def test_current_at_stall(self):
        from motor_model import MOTOR_DB
        m = MOTOR_DB["kraken_x60"]
        # At zero speed, current should equal stall current
        current = m.current_at_speed(0)
        self.assertAlmostEqual(current, m.stall_current_a, places=0)

    def test_current_at_free_speed(self):
        from motor_model import MOTOR_DB
        m = MOTOR_DB["kraken_x60"]
        # At free speed, current should be ~free current
        current = m.current_at_speed(m.free_speed_rads)
        self.assertAlmostEqual(current, m.free_current_a, delta=1.0)

    def test_current_limited_torque_capped(self):
        from motor_model import MOTOR_DB
        m = MOTOR_DB["kraken_x60"]
        limited = m.current_limited_torque(0, 40.0)
        unlimited = m.torque_at_current(m.stall_current_a)
        self.assertLess(limited, unlimited)

    def test_stall_load_positive(self):
        from motor_model import MOTOR_DB
        m = MOTOR_DB["kraken_x60"]
        load = m.stall_load_lb(3.0, 0.01, motor_count=2, current_limit_a=40.0)
        self.assertGreater(load, 0)

    def test_all_motors_have_valid_constants(self):
        from motor_model import MOTOR_DB
        for name, m in MOTOR_DB.items():
            with self.subTest(motor=name):
                self.assertGreater(m.R, 0, f"{name}: R must be positive")
                self.assertGreater(m.kV, 0, f"{name}: kV must be positive")
                self.assertGreater(m.kT, 0, f"{name}: kT must be positive")


class TestMotionProfile(unittest.TestCase):
    """Test the motion profile simulator."""

    def test_simulation_completes(self):
        from motor_model import MOTOR_DB, simulate_linear_motion
        result = simulate_linear_motion(
            motor=MOTOR_DB["kraken_x60"],
            motor_count=2, gear_ratio=3.0, spool_diameter_in=1.35,
            load_lb=15.0, travel_distance_in=48.0, current_limit_a=40.0,
        )
        self.assertGreater(result.travel_time_sec, 0)
        self.assertLess(result.travel_time_sec, 5.0)

    def test_current_limited(self):
        from motor_model import MOTOR_DB, simulate_linear_motion
        result = simulate_linear_motion(
            motor=MOTOR_DB["kraken_x60"],
            motor_count=2, gear_ratio=3.0, spool_diameter_in=1.35,
            load_lb=15.0, travel_distance_in=48.0, current_limit_a=40.0,
        )
        # Peak current should be at or near the limit
        self.assertLessEqual(result.peak_current_a, 40.1)

    def test_lower_current_limit_slower(self):
        from motor_model import MOTOR_DB, simulate_linear_motion
        fast = simulate_linear_motion(
            motor=MOTOR_DB["kraken_x60"],
            motor_count=2, gear_ratio=3.0, spool_diameter_in=1.35,
            load_lb=15.0, travel_distance_in=48.0, current_limit_a=60.0,
        )
        slow = simulate_linear_motion(
            motor=MOTOR_DB["kraken_x60"],
            motor_count=2, gear_ratio=3.0, spool_diameter_in=1.35,
            load_lb=15.0, travel_distance_in=48.0, current_limit_a=20.0,
        )
        self.assertLess(fast.travel_time_sec, slow.travel_time_sec)

    def test_stall_load_with_current_limit(self):
        from motor_model import MOTOR_DB, simulate_linear_motion
        result = simulate_linear_motion(
            motor=MOTOR_DB["kraken_x60"],
            motor_count=2, gear_ratio=3.0, spool_diameter_in=1.35,
            load_lb=15.0, travel_distance_in=48.0, current_limit_a=40.0,
        )
        self.assertGreater(result.stall_load_lb, 15.0)  # must exceed the load


class TestElevatorPhysics(unittest.TestCase):
    """Test elevator generator uses physics simulation correctly."""

    def test_current_limit_in_spec(self):
        spec = generate_elevator(current_limit_a=40.0)
        self.assertEqual(spec.current_limit_a, 40.0)
        self.assertIn("CURRENT_LIMIT_A", spec.software_constants)

    def test_efficiency_in_spec(self):
        spec = generate_elevator(efficiency=0.85)
        self.assertEqual(spec.efficiency, 0.85)
        self.assertIn("EFFICIENCY", spec.software_constants)

    def test_peak_current_reported(self):
        spec = generate_elevator()
        self.assertGreater(spec.peak_current_a, 0)
        self.assertLessEqual(spec.peak_current_a, spec.current_limit_a + 0.1)

    def test_stall_load_reported(self):
        spec = generate_elevator()
        self.assertGreater(spec.stall_load_lb, 0)

    def test_kg_derived_from_physics(self):
        spec = generate_elevator()
        # kG should be derived from motor model, not hardcoded
        self.assertGreater(spec.software_constants["kG"], 0)
        self.assertLess(spec.software_constants["kG"], 5.0)  # reasonable range

    def test_kv_derived_from_physics(self):
        spec = generate_elevator()
        # kV should be small (V·s/in)
        self.assertGreater(spec.software_constants["kV"], 0.001)
        self.assertLess(spec.software_constants["kV"], 0.1)

    def test_lower_efficiency_slower(self):
        fast = generate_elevator(efficiency=0.95)
        slow = generate_elevator(efficiency=0.70)
        self.assertLessEqual(fast.full_travel_time_sec, slow.full_travel_time_sec)


class TestIntakePhysics(unittest.TestCase):
    """Test intake generator uses drivetrain-linked speed correctly."""

    def test_drivetrain_speed_in_spec(self):
        spec = generate_intake(drivetrain_speed_fps=14.5)
        self.assertEqual(spec.drivetrain_speed_fps, 14.5)

    def test_surface_speed_near_2x_drivetrain(self):
        spec = generate_intake(drivetrain_speed_fps=14.5)
        # Surface speed should be roughly 2x drivetrain speed
        self.assertGreater(spec.surface_speed_fps, 14.5 * 1.5)  # at least 1.5x
        self.assertLess(spec.surface_speed_fps, 14.5 * 3.0)  # no more than 3x

    def test_faster_drivetrain_faster_intake(self):
        slow_drive = generate_intake(drivetrain_speed_fps=10.0)
        fast_drive = generate_intake(drivetrain_speed_fps=18.0)
        self.assertLess(slow_drive.surface_speed_fps, fast_drive.surface_speed_fps)

    def test_recalc_note_present(self):
        spec = generate_intake(drivetrain_speed_fps=14.5)
        notes_text = " ".join(spec.notes)
        self.assertIn("ReCalc", notes_text)

    def test_zero_drivetrain_uses_fallback(self):
        spec = generate_intake(drivetrain_speed_fps=0)
        # Should fall back to target_surface_speed_fps
        self.assertGreater(spec.surface_speed_fps, 10.0)
        self.assertLess(spec.surface_speed_fps, 25.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
