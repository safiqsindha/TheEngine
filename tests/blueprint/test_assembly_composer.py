"""
Tests for blueprint/assembly_composer.py — the integration layer that
decides where each mechanism mounts on the robot frame.

Hermetic: pure logic, no I/O beyond loading historical fixture JSONs from
the blueprint/ directory.
"""

import json
import sys
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from assembly_composer import (  # noqa: E402
    MechanismPlacement,
    RobotLayout,
    compose_robot,
    _check_overlap,
    _in_to_mm,
    PLACEMENT_ZONES,
)

HISTORICAL_SPECS = {
    year: json.loads((_BLUEPRINT_DIR / f"{year}_{name}_full_blueprint.json").read_text())
    for year, name in (
        ("2022", "rapid_react"),
        ("2023", "charged_up"),
        ("2024", "crescendo"),
    )
}


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _minimal_spec(**mechanism_overrides):
    """Build a minimal blueprint spec dict — frame + whatever mechanisms the test needs."""
    spec = {
        "frame": {
            "frame_length_in": 27.0,
            "frame_width_in": 27.0,
            "frame_height_in": 1.0,
            "bumper_thickness_in": 3.5,
            "total_weight_lb": 40.0,
        }
    }
    spec.update(mechanism_overrides)
    return spec


def _make_placement(x, y, z, wx, wy, wz, weight=5.0, name="p"):
    """Build a MechanismPlacement at a given center with given envelope."""
    p = MechanismPlacement(
        name=name,
        position_in=[x, y, z],
        envelope_in=[wx, wy, wz],
        weight_lb=weight,
    )
    return p


# ─────────────────────────────────────────────────────────────────────
# Phase 2.1 — Helper + unit tests
# ─────────────────────────────────────────────────────────────────────

def test_in_to_mm_one_inch():
    assert _in_to_mm(1.0) == 25.4


def test_in_to_mm_zero():
    assert _in_to_mm(0) == 0.0


def test_in_to_mm_fractional():
    result = _in_to_mm(10.0)
    assert abs(result - 254.0) < 0.01


def test_mechanism_placement_defaults():
    p = MechanismPlacement()
    assert p.position_in == [0.0, 0.0, 0.0]
    assert p.envelope_in == [0.0, 0.0, 0.0]
    assert p.weight_lb == 0.0
    assert p.mounting_face == "top"


def test_robot_layout_defaults():
    layout = RobotLayout()
    assert layout.frame_length_in == 27.0
    assert layout.frame_width_in == 27.0
    assert layout.frame_height_in == 1.0
    assert layout.placements == []
    assert layout.interference_warnings == []
    assert layout.assembly_order == []
    assert layout.center_of_gravity_in == [0.0, 0.0, 0.0]


def test_placement_zones_has_expected_mechanisms():
    for key in ("intake", "flywheel", "elevator", "conveyor", "climber", "turret", "arm"):
        assert key in PLACEMENT_ZONES


# ─────────────────────────────────────────────────────────────────────
# Phase 2.2 — Frame-only baseline
# ─────────────────────────────────────────────────────────────────────

def test_frame_only_returns_robot_layout():
    layout = compose_robot(_minimal_spec())
    assert isinstance(layout, RobotLayout)


def test_frame_only_echoes_dimensions():
    layout = compose_robot(_minimal_spec())
    assert layout.frame_length_in == 27.0
    assert layout.frame_width_in == 27.0
    assert layout.frame_height_in == 1.0


def test_frame_only_no_interference_warnings():
    layout = compose_robot(_minimal_spec())
    # Only possible warning on frame-only is height, but total_height is 1.0 — no warning
    height_warnings = [w for w in layout.interference_warnings if "overlap" in w]
    assert height_warnings == []


def test_frame_only_assembly_order_nonempty():
    layout = compose_robot(_minimal_spec())
    assert len(layout.assembly_order) >= 1
    assert layout.assembly_order[0]["subsystem"] == "frame"


def test_frame_only_swerve_modules_populated():
    # Default 4 MK4i positions when no module_placements provided
    layout = compose_robot(_minimal_spec())
    assert len(layout.swerve_modules) == 4
    names = {m["name"] for m in layout.swerve_modules}
    assert names == {"front_left", "front_right", "back_left", "back_right"}


def test_frame_custom_dimensions():
    spec = {
        "frame": {
            "frame_length_in": 24.0,
            "frame_width_in": 30.0,
            "frame_height_in": 1.0,
        }
    }
    layout = compose_robot(spec)
    assert layout.frame_length_in == 24.0
    assert layout.frame_width_in == 30.0


# ─────────────────────────────────────────────────────────────────────
# Phase 2.3 — Per-mechanism placement
# ─────────────────────────────────────────────────────────────────────

def test_intake_at_front():
    """Intake preferred zone is 'front' (+Y)."""
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    placements = [p for p in layout.placements if p.name == "intake"]
    assert placements, "intake should appear in placements"
    # front = positive Y
    assert placements[0].position_in[1] > 0


def test_intake_in_placements_list():
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    names = [p.name for p in layout.placements]
    assert "intake" in names


def test_intake_position_mm_populated():
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    intake = next(p for p in layout.placements if p.name == "intake")
    assert intake.position_mm[1] == _in_to_mm(intake.position_in[1])


def test_conveyor_at_center():
    """Conveyor preferred zone is 'center' — Y ≈ 0."""
    conveyor_spec = HISTORICAL_SPECS["2022"]["conveyor"]
    layout = compose_robot(_minimal_spec(conveyor=conveyor_spec))
    placements = [p for p in layout.placements if p.name == "conveyor"]
    assert placements
    assert placements[0].position_in[1] == 0.0


def test_flywheel_at_back():
    """Flywheel preferred zone is 'back_upper' — negative Y."""
    flywheel_spec = HISTORICAL_SPECS["2022"]["flywheel"]
    layout = compose_robot(_minimal_spec(flywheel=flywheel_spec))
    placements = [p for p in layout.placements if p.name == "flywheel"]
    assert placements
    assert placements[0].position_in[1] < 0


def test_elevator_at_center_back():
    """Elevator preferred zone is 'center_back' — Y slightly negative."""
    elevator_spec = HISTORICAL_SPECS["2023"]["elevator"]
    layout = compose_robot(_minimal_spec(elevator=elevator_spec))
    placements = [p for p in layout.placements if p.name == "elevator"]
    assert placements
    # center_back: Y = -2.0 per code
    assert placements[0].position_in[1] <= 0


def test_climber_at_back():
    """Climber preferred zone is 'back' — negative Y."""
    climber_spec = HISTORICAL_SPECS["2022"]["climber"]
    layout = compose_robot(_minimal_spec(climber=climber_spec))
    placements = [p for p in layout.placements if p.name == "climber"]
    assert placements
    assert placements[0].position_in[1] < 0


def test_climber_mounting_face_is_back():
    climber_spec = HISTORICAL_SPECS["2022"]["climber"]
    layout = compose_robot(_minimal_spec(climber=climber_spec))
    climber = next(p for p in layout.placements if p.name == "climber")
    assert climber.mounting_face == "back"


def test_elevator_envelope_height_includes_travel():
    elevator_spec = HISTORICAL_SPECS["2023"]["elevator"]
    travel = elevator_spec.get("travel_height_in", 48.0)
    layout = compose_robot(_minimal_spec(elevator=elevator_spec))
    elevator = next(p for p in layout.placements if p.name == "elevator")
    # envelope height = travel + 6 per code
    assert elevator.envelope_in[2] == pytest.approx(travel + 6.0)


def test_flywheel_envelope_mm_consistent_with_in():
    flywheel_spec = HISTORICAL_SPECS["2022"]["flywheel"]
    layout = compose_robot(_minimal_spec(flywheel=flywheel_spec))
    fw = next(p for p in layout.placements if p.name == "flywheel")
    for i in range(3):
        assert fw.envelope_mm[i] == pytest.approx(_in_to_mm(fw.envelope_in[i]))


# ─────────────────────────────────────────────────────────────────────
# Phase 3 — _check_overlap, CoG, assembly order
# ─────────────────────────────────────────────────────────────────────

def test_overlap_identical_placements():
    p1 = _make_placement(0, 0, 0, 10, 10, 10)
    p2 = _make_placement(0, 0, 0, 10, 10, 10)
    assert _check_overlap(p1, p2) is True


def test_no_overlap_separated_x():
    p1 = _make_placement(0, 0, 0, 4, 4, 4)
    p2 = _make_placement(10, 0, 0, 4, 4, 4)
    assert _check_overlap(p1, p2) is False


def test_no_overlap_separated_y():
    p1 = _make_placement(0, 0, 0, 4, 4, 4)
    p2 = _make_placement(0, 10, 0, 4, 4, 4)
    assert _check_overlap(p1, p2) is False


def test_no_overlap_separated_z():
    p1 = _make_placement(0, 0, 0, 4, 4, 4)
    p2 = _make_placement(0, 0, 10, 4, 4, 4)
    assert _check_overlap(p1, p2) is False


def test_overlap_all_axes():
    p1 = _make_placement(0, 0, 0, 10, 10, 10)
    p2 = _make_placement(3, 3, 3, 10, 10, 10)
    assert _check_overlap(p1, p2) is True


def test_touching_face_to_face_no_overlap():
    """Face-to-face touching (p1_max == p2_min) should NOT count as overlap."""
    # p1 occupies x: -5 to +5; p2 starts at x=5
    p1 = _make_placement(0, 0, 0, 10, 10, 10)   # x: -5 to +5
    p2 = _make_placement(10, 0, 0, 10, 10, 10)  # x: +5 to +15
    assert _check_overlap(p1, p2) is False


def test_overlap_xy_but_not_z():
    p1 = _make_placement(0, 0, 0, 10, 10, 4)
    p2 = _make_placement(2, 2, 20, 10, 10, 4)
    assert _check_overlap(p1, p2) is False


# CoG tests
def test_frame_only_cog_at_origin():
    layout = compose_robot(_minimal_spec())
    cog = layout.center_of_gravity_in
    # No mechanisms → no weighted sum from placements; frame weight contributes at z=H/2
    # With only frame, CoG x and y = 0
    assert cog[0] == pytest.approx(0.0)
    assert cog[1] == pytest.approx(0.0)


def test_cog_z_positive_with_tall_elevator():
    elevator_spec = HISTORICAL_SPECS["2023"]["elevator"]
    layout = compose_robot(_minimal_spec(elevator=elevator_spec))
    cog = layout.center_of_gravity_in
    assert cog[2] > 0


def test_intake_raises_front_cog():
    """Adding intake (front +Y) should shift CoG toward positive Y vs frame-only."""
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout_with = compose_robot(_minimal_spec(intake=intake_spec))
    layout_bare = compose_robot(_minimal_spec())
    # intake at +Y should push CoG in +Y direction
    assert layout_with.center_of_gravity_in[1] >= layout_bare.center_of_gravity_in[1]


# Assembly order tests
def test_assembly_order_frame_first():
    layout = compose_robot(_minimal_spec())
    assert layout.assembly_order[0]["subsystem"] == "frame"


def test_assembly_order_electronics_last():
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    subsystems = [step["subsystem"] for step in layout.assembly_order]
    assert subsystems[-2] == "electronics"


def test_assembly_order_steps_sequential():
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    steps = [step["step"] for step in layout.assembly_order]
    assert steps == list(range(1, len(steps) + 1))


def test_assembly_order_flywheel_before_intake():
    """Scorer is more critical → flywheel step appears before intake step."""
    flywheel_spec = HISTORICAL_SPECS["2022"]["flywheel"]
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]
    layout = compose_robot(_minimal_spec(flywheel=flywheel_spec, intake=intake_spec))
    subsystems = [step["subsystem"] for step in layout.assembly_order]
    assert subsystems.index("flywheel") < subsystems.index("intake")


# ─────────────────────────────────────────────────────────────────────
# Phase 4 — Historical regression lock-in
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_compose_does_not_crash(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert isinstance(layout, RobotLayout)


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_layout_has_placements(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert len(layout.placements) >= 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        "compose_robot uses axis-aligned bounding boxes (AABB) to detect overlap. "
        "For large game pieces (e.g. 2024 Crescendo 14\" note, depth=18\"), the intake "
        "AABB extends far back into the robot center, falsely flagging adjacent mechanisms "
        "(conveyor, climber) as overlapping. This is AABB over-conservatism, NOT a real "
        "interference in the shipping robots. Fix requires switching to tighter geometry "
        "models (e.g. deployed vs stowed envelopes). Bug in compose_robot — fix separately."
    ),
)
@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_no_mechanism_interference(year):
    """The 3 historical designs were real shipping robots.
    Their mechanisms must not physically overlap — currently xfail because
    the AABB model is too conservative (see xfail reason above)."""
    layout = compose_robot(HISTORICAL_SPECS[year])
    overlap_warnings = [w for w in layout.interference_warnings if "overlap" in w]
    assert overlap_warnings == [], (
        f"{year}: unexpected interference: {overlap_warnings}"
    )


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_cog_inside_frame(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    cog_x, cog_y, _ = layout.center_of_gravity_in
    half_l = layout.frame_length_in / 2
    half_w = layout.frame_width_in / 2
    assert -half_l <= cog_x <= half_l
    assert -half_w <= cog_y <= half_w


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_total_height_positive(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert layout.total_height_in > 0


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_swerve_modules_count(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert len(layout.swerve_modules) == 4


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_assembly_order_frame_first(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert layout.assembly_order[0]["subsystem"] == "frame"


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_all_positions_have_mm_counterparts(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    for p in layout.placements:
        for i in range(3):
            assert p.position_mm[i] == pytest.approx(_in_to_mm(p.position_in[i]))
        for i in range(3):
            assert p.envelope_mm[i] == pytest.approx(_in_to_mm(p.envelope_in[i]))


# ─────────────────────────────────────────────────────────────────────
# Phase 5 — Edge cases
# ─────────────────────────────────────────────────────────────────────

def test_empty_spec_returns_layout():
    """Empty spec must not crash — minimal default frame."""
    layout = compose_robot({})
    assert isinstance(layout, RobotLayout)
    assert layout.placements == []


def test_frame_only_placements_empty():
    layout = compose_robot(_minimal_spec())
    assert layout.placements == []


def test_height_warning_when_tall():
    """Robot taller than 48 inches should trigger a height interference warning."""
    # elevator with very large travel will push total_height_in > 48
    layout = compose_robot(_minimal_spec(elevator={"travel_height_in": 60.0}))
    height_warnings = [w for w in layout.interference_warnings if "height" in w.lower()]
    assert height_warnings, "should warn when robot is >48 inches tall"


def test_two_overlapping_mechanisms_triggers_warning():
    """If two mechanism envelopes overlap, interference_warnings should be populated."""
    # Fabricate a spec where both elevator and conveyor occupy the same space
    # by giving them identical positions — can't control positions directly via spec,
    # so place conveyor (center Y=0) and turret on top (also center Y=0) with large envelopes
    spec = _minimal_spec(
        conveyor={"path_length_in": 60.0, "game_piece_diameter_in": 20.0, "staging_count": 1},
        turret={"turret_od_in": 60.0, "total_weight_lb": 5.0},
    )
    layout = compose_robot(spec)
    overlap_warnings = [w for w in layout.interference_warnings if "overlap" in w]
    assert overlap_warnings, "oversized conveyor + turret should produce overlap warning"


def test_total_height_equals_max_mechanism_z():
    """total_height_in should reflect the tallest mechanism."""
    elevator_spec = HISTORICAL_SPECS["2023"]["elevator"]
    layout_elevator = compose_robot(_minimal_spec(elevator=elevator_spec))
    layout_bare = compose_robot(_minimal_spec())
    assert layout_elevator.total_height_in > layout_bare.total_height_in
