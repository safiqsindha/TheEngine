"""
Tests for blueprint/oracle.py — the prediction engine that applies
CROSS_SEASON_PATTERNS R1-R19 to a GameRules input.

Hermetic: pure logic, no I/O.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from oracle import (  # noqa: E402
    GameRules,
    RuleResult,
    apply_rules,
    predict_game,
    predict_from_file,
    validate_all,
    HISTORICAL_GAMES,
    GROUND_TRUTH,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _minimal_game(**overrides):
    """Build a GameRules with minimal valid defaults; override what each test cares about."""
    base = dict(
        game_name="Test",
        year=2027,
        game_piece_name="widget",
        game_piece_shape="cylindrical",
        game_piece_diameter_in=4.5,
        scoring_targets=[
            {"name": "T1", "height_in": 60, "distance_ft": 8, "auto_pts": 4,
             "teleop_pts": 2, "type": "ranged", "distributed": True,
             "cap_type": "uncapped", "max_alliance_pts": 999},
        ],
        endgame_type="climb",
        endgame_height_in=30,
        endgame_points=10,
        endgame_pct_of_winning_score=0.15,
    )
    base.update(overrides)
    return GameRules(**base)


# ─────────────────────────────────────────────────────────────────────
# Phase 2 — Per-rule happy paths
# ─────────────────────────────────────────────────────────────────────

# ── R1: Drivetrain ──

def test_r1_drivetrain_always_swerve():
    pred = apply_rules(_minimal_game())
    assert pred["drivetrain"]["type"] == "swerve"
    assert pred["drivetrain"]["module"] == "sds_mk4i"


def test_r1_large_field_gears_for_speed():
    pred = apply_rules(_minimal_game(field_is_small=False))
    assert pred["drivetrain"]["gear_for"] == "speed"
    assert pred["drivetrain"]["speed_fps"] == 16.0


def test_r1_small_field_gears_for_acceleration():
    pred = apply_rules(_minimal_game(field_is_small=True))
    assert pred["drivetrain"]["gear_for"] == "acceleration"
    assert pred["drivetrain"]["speed_fps"] == 14.0


def test_r1_default_frame_size_is_27():
    pred = apply_rules(_minimal_game(max_frame_perimeter_in=120))
    assert pred["drivetrain"]["frame_length"] == 27.0
    assert pred["drivetrain"]["frame_width"] == 27.0


def test_r1_small_perimeter_shrinks_frame():
    # frame_size = min(27, perimeter/4 - 1) when perimeter < 112
    pred = apply_rules(_minimal_game(max_frame_perimeter_in=100))
    assert pred["drivetrain"]["frame_length"] == 24.0  # 100/4 - 1


def test_r1_perimeter_boundary_112_uses_default():
    # 112 is NOT < 112, so default frame stays
    pred = apply_rules(_minimal_game(max_frame_perimeter_in=112))
    assert pred["drivetrain"]["frame_length"] == 27.0


# ── R2: Intake width ──

def test_r2_intake_full_width():
    pred = apply_rules(_minimal_game(pieces_floor_pickup=True))
    assert pred["intake"]["width"] == "full"
    assert pred["intake"]["motors"] == 2


def test_r2_intake_deploys_when_floor_pickup():
    pred = apply_rules(_minimal_game(pieces_floor_pickup=True))
    assert pred["intake"]["deploy"] is True


# ── R3: Roller material ──

def test_r3_spherical_uses_compliant_wheels():
    pred = apply_rules(_minimal_game(game_piece_shape="spherical"))
    assert pred["intake"]["roller_material"] == "compliant_wheels"


def test_r3_flat_disc_uses_mecanum_funnel():
    pred = apply_rules(_minimal_game(game_piece_shape="flat disc"))
    assert pred["intake"]["roller_material"] == "mecanum_funnel"


def test_r3_cylindrical_uses_flex_wheels():
    pred = apply_rules(_minimal_game(game_piece_shape="cylindrical tube"))
    assert pred["intake"]["roller_material"] == "flex_wheels"


def test_r3_irregular_uses_flex_wheels():
    pred = apply_rules(_minimal_game(game_piece_shape="irregular"))
    assert pred["intake"]["roller_material"] == "flex_wheels"


def test_r3_unknown_shape_defaults_to_flex():
    pred = apply_rules(_minimal_game(game_piece_shape="alien-blob"))
    assert pred["intake"]["roller_material"] == "flex_wheels"


def test_r3_under_bumper_when_piece_small():
    pred = apply_rules(_minimal_game(game_piece_diameter_in=2.5))
    assert pred["intake"]["type"] == "under_bumper"


def test_r3_over_bumper_when_piece_large():
    pred = apply_rules(_minimal_game(game_piece_diameter_in=5.0))
    assert pred["intake"]["type"] == "over_bumper"


# ── R4: Scorer method ──

def test_r4_ranged_target_uses_flywheel():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Hub", "height_in": 80, "distance_ft": 10, "auto_pts": 4,
         "teleop_pts": 2, "type": "ranged", "distributed": True,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    assert pred["scorer"]["method"] == "flywheel"


def test_r4_placement_target_uses_elevator():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Reef", "height_in": 60, "distance_ft": 0, "auto_pts": 6,
         "teleop_pts": 5, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 100},
    ]))
    assert pred["scorer"]["method"] == "elevator"


def test_r4_ground_target_uses_gravity_drop():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Floor", "height_in": 0, "distance_ft": 0, "auto_pts": 3,
         "teleop_pts": 2, "type": "ground", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 50},
    ]))
    assert pred["scorer"]["method"] == "gravity_drop"


def test_r4_no_targets_defaults_to_elevator():
    pred = apply_rules(_minimal_game(scoring_targets=[]))
    assert pred["scorer"]["method"] == "elevator"


# ── R5: Elevator stage count ──

def test_r5_low_target_no_elevator():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Low", "height_in": 20, "distance_ft": 0, "auto_pts": 2,
         "teleop_pts": 2, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 50},
    ]))
    assert pred["scorer"]["stages"] == 0


def test_r5_mid_target_single_stage():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Mid", "height_in": 36, "distance_ft": 0, "auto_pts": 4,
         "teleop_pts": 3, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 50},
    ]))
    assert pred["scorer"]["stages"] == 1


def test_r5_high_target_two_stage():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "High", "height_in": 50, "distance_ft": 0, "auto_pts": 5,
         "teleop_pts": 4, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 50},
    ]))
    assert pred["scorer"]["stages"] == 2


def test_r5_extreme_height_caps_at_two_stage():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Sky", "height_in": 80, "distance_ft": 0, "auto_pts": 7,
         "teleop_pts": 6, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 50},
    ]))
    assert pred["scorer"]["stages"] == 2  # 3-stage too complex


# ── R6: Turret ──

def test_r6_ranged_distributed_builds_continuous_turret():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Hub", "height_in": 80, "distance_ft": 10, "auto_pts": 4,
         "teleop_pts": 2, "type": "ranged", "distributed": True,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    assert pred["scorer"]["turret"] == "continuous"


def test_r6_ranged_fixed_skips_turret():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Speaker", "height_in": 80, "distance_ft": 10, "auto_pts": 5,
         "teleop_pts": 2, "type": "ranged", "distributed": False,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    assert pred["scorer"]["turret"] == "none"


def test_r6_placement_distributed_skips_turret():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Reef", "height_in": 60, "distance_ft": 0, "auto_pts": 6,
         "teleop_pts": 5, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 100},
    ]))
    assert pred["scorer"]["turret"] == "none"


def test_r6_placement_fixed_skips_turret():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Slot", "height_in": 60, "distance_ft": 0, "auto_pts": 6,
         "teleop_pts": 5, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 100},
    ]))
    assert pred["scorer"]["turret"] == "none"


# ── R7: Endgame ──

def test_r7_high_value_climb_required():
    pred = apply_rules(_minimal_game(
        endgame_type="climb", endgame_height_in=48,
        endgame_pct_of_winning_score=0.25,
    ))
    assert pred["endgame"]["type"] != "none"
    assert pred["endgame"]["motors"] >= 1


def test_r7_telescope_for_tall_climbs():
    pred = apply_rules(_minimal_game(
        endgame_type="climb", endgame_height_in=50,
        endgame_pct_of_winning_score=0.20,
    ))
    assert pred["endgame"]["type"] == "telescope"


def test_r7_hook_winch_for_short_climbs():
    pred = apply_rules(_minimal_game(
        endgame_type="climb", endgame_height_in=25,
        endgame_pct_of_winning_score=0.20,
    ))
    assert pred["endgame"]["type"] == "hook_winch"


def test_r7_balance_endgame():
    pred = apply_rules(_minimal_game(
        endgame_type="balance", endgame_height_in=12,
        endgame_pct_of_winning_score=0.15,
    ))
    assert pred["endgame"]["type"] == "balance"


def test_r7_park_only_endgame():
    pred = apply_rules(_minimal_game(
        endgame_type="park", endgame_height_in=0,
        endgame_pct_of_winning_score=0.05,
    ))
    assert pred["endgame"]["type"] == "park_only"
    assert pred["endgame"]["motors"] == 0


def test_r7_15_percent_threshold_must_climb():
    # 15% is the boundary — climb_must = climb_pct >= 0.15
    pred = apply_rules(_minimal_game(
        endgame_type="climb", endgame_height_in=30,
        endgame_pct_of_winning_score=0.15,
    ))
    assert pred["endgame"]["type"] != "none"


# ── R8: Autonomous ──

def test_r8_baseline_three_piece_auto():
    pred = apply_rules(_minimal_game(
        auto_duration_s=15, pieces_at_known_positions=True, field_is_small=False,
    ))
    assert pred["autonomous"]["estimated_pieces"] == 3


def test_r8_small_field_bumps_auto_pieces():
    pred = apply_rules(_minimal_game(
        auto_duration_s=15, pieces_at_known_positions=True, field_is_small=True,
    ))
    assert pred["autonomous"]["estimated_pieces"] == 4


def test_r8_cycle_time_normal_field():
    pred = apply_rules(_minimal_game(field_is_small=False))
    assert pred["autonomous"]["cycle_time_s"] == 5.0


def test_r8_cycle_time_small_field():
    pred = apply_rules(_minimal_game(field_is_small=True))
    assert pred["autonomous"]["cycle_time_s"] == 4.0


# ── R10: Game piece detection ──

def test_r10_no_detection_when_known_positions():
    pred = apply_rules(_minimal_game(
        pieces_at_known_positions=True, pieces_shared_contested=False,
    ))
    rule = next(r for r in pred["rule_log"] if r["rule"] == "R10")
    assert rule["recommendation"] == "none"


def test_r10_hsv_for_high_contrast_scattered():
    pred = apply_rules(_minimal_game(
        pieces_floor_pickup=True,
        pieces_at_known_positions=False,
        piece_high_contrast=True,
    ))
    rule = next(r for r in pred["rule_log"] if r["rule"] == "R10")
    assert rule["recommendation"] == "hsv_color"


def test_r10_yolo_for_low_contrast_scattered():
    pred = apply_rules(_minimal_game(
        pieces_floor_pickup=True,
        pieces_at_known_positions=False,
        piece_high_contrast=False,
    ))
    rule = next(r for r in pred["rule_log"] if r["rule"] == "R10")
    assert rule["recommendation"] == "yolo_neural"


def test_r10_yolo_for_contested_pieces():
    pred = apply_rules(_minimal_game(
        pieces_at_known_positions=True,
        pieces_shared_contested=True,
    ))
    rule = next(r for r in pred["rule_log"] if r["rule"] == "R10")
    assert rule["recommendation"] == "yolo_neural"


# ── R18: Obstacles ──

def test_r18_obstacle_check_fires():
    pred = apply_rules(_minimal_game(
        field_has_obstacles=True, field_obstacle_height_in=3,
    ))
    assert any(r["rule"] == "R18" for r in pred["rule_log"])


def test_r18_no_obstacle_no_rule():
    pred = apply_rules(_minimal_game(field_has_obstacles=False))
    assert not any(r["rule"] == "R18" for r in pred["rule_log"])


# ── R19: Capped vs uncapped ──

def test_r19_only_uncapped_no_rule():
    # R19 only fires when both capped and uncapped exist
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "T1", "height_in": 60, "distance_ft": 8, "auto_pts": 4,
         "teleop_pts": 2, "type": "ranged", "distributed": True,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    assert not any(r["rule"] == "R19" for r in pred["rule_log"])


def test_r19_mixed_targets_fires():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Capped", "height_in": 30, "distance_ft": 0, "auto_pts": 2,
         "teleop_pts": 2, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 50},
        {"name": "Uncapped", "height_in": 12, "distance_ft": 0, "auto_pts": 0,
         "teleop_pts": 6, "type": "placement", "distributed": False,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    assert any(r["rule"] == "R19" for r in pred["rule_log"])


def test_r19_saturating_capped_recommends_uncapped():
    # Low max_alliance_pts → saturates → uncapped becomes priority
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Capped", "height_in": 30, "distance_ft": 0, "auto_pts": 2,
         "teleop_pts": 4, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 50},
        {"name": "Uncapped", "height_in": 12, "distance_ft": 0, "auto_pts": 0,
         "teleop_pts": 6, "type": "placement", "distributed": False,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    r19 = next(r for r in pred["rule_log"] if r["rule"] == "R19")
    assert r19["recommendation"] == "uncapped_priority"


def test_r19_non_saturating_capped_remains_priority():
    # High max_alliance_pts → won't saturate
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Capped", "height_in": 30, "distance_ft": 0, "auto_pts": 1,
         "teleop_pts": 1, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 5000},
        {"name": "Uncapped", "height_in": 12, "distance_ft": 0, "auto_pts": 0,
         "teleop_pts": 6, "type": "placement", "distributed": False,
         "cap_type": "uncapped", "max_alliance_pts": 999},
    ]))
    r19 = next(r for r in pred["rule_log"] if r["rule"] == "R19")
    assert r19["recommendation"] == "capped_priority"


# ─────────────────────────────────────────────────────────────────────
# Phase 3 — Historical regression lock-in
# ─────────────────────────────────────────────────────────────────────

def test_validate_all_meets_accuracy_threshold(capsys):
    """Lock in oracle accuracy. If a rule change drops historical accuracy
    below 90%, this test fails and forces an explicit decision."""
    result = validate_all()
    capsys.readouterr()  # discard the printed report
    assert result["accuracy_pct"] >= 90.0, (
        f"Oracle accuracy dropped to {result['accuracy_pct']}% — "
        f"a rule change broke historical validation. "
        f"{result['correct']}/{result['total_checks']}"
    )


def test_validate_all_returns_expected_keys(capsys):
    result = validate_all()
    capsys.readouterr()
    assert "total_checks" in result
    assert "correct" in result
    assert "accuracy_pct" in result
    assert "results" in result


def test_validate_all_covers_all_historical_games(capsys):
    """If a new historical game is added without ground truth, this fails."""
    result = validate_all()
    capsys.readouterr()
    assert set(result["results"].keys()) == set(HISTORICAL_GAMES.keys())
    assert set(HISTORICAL_GAMES.keys()) == set(GROUND_TRUTH.keys())


def test_historical_games_nonempty():
    assert len(HISTORICAL_GAMES) >= 4
    assert "2022" in HISTORICAL_GAMES
    assert "2023" in HISTORICAL_GAMES
    assert "2024" in HISTORICAL_GAMES
    assert "2025" in HISTORICAL_GAMES


@pytest.mark.parametrize("year_str", sorted(HISTORICAL_GAMES.keys()))
def test_historical_drivetrain_matches_truth(year_str):
    pred = apply_rules(HISTORICAL_GAMES[year_str])
    assert pred["drivetrain"]["type"] == GROUND_TRUTH[year_str]["drivetrain"]


@pytest.mark.parametrize("year_str", sorted(HISTORICAL_GAMES.keys()))
def test_historical_intake_width_matches_truth(year_str):
    pred = apply_rules(HISTORICAL_GAMES[year_str])
    assert pred["intake"]["width"] == GROUND_TRUTH[year_str]["intake_width"]


@pytest.mark.parametrize("year_str", sorted(HISTORICAL_GAMES.keys()))
def test_historical_scorer_matches_truth(year_str):
    pred = apply_rules(HISTORICAL_GAMES[year_str])
    assert pred["scorer"]["method"] == GROUND_TRUTH[year_str]["scorer_method"]


@pytest.mark.parametrize("year_str", sorted(HISTORICAL_GAMES.keys()))
def test_historical_endgame_engages(year_str):
    pred = apply_rules(HISTORICAL_GAMES[year_str])
    truth_endgame = GROUND_TRUTH[year_str]["endgame"]
    # Both predicted and truth must be a non-trivial endgame
    assert pred["endgame"]["type"] != "none"
    assert truth_endgame in ("climb", "balance")


# ─────────────────────────────────────────────────────────────────────
# Phase 4 — Edge cases + JSON round-trip
# ─────────────────────────────────────────────────────────────────────

def test_empty_scoring_targets_does_not_crash():
    pred = apply_rules(_minimal_game(scoring_targets=[]))
    # Falls back to placement/elevator default
    assert pred["scorer"]["method"] == "elevator"
    assert "build_order" in pred


def test_single_scoring_target_works():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Solo", "height_in": 60, "distance_ft": 0, "auto_pts": 5,
         "teleop_pts": 4, "type": "placement", "distributed": False,
         "cap_type": "capped", "max_alliance_pts": 100},
    ]))
    assert pred["scorer"]["method"] == "elevator"


def test_build_order_non_empty():
    pred = apply_rules(_minimal_game())
    assert len(pred["build_order"]) >= 4
    assert "drivetrain" in pred["build_order"]


def test_build_order_elevator_first_for_tall_targets():
    pred = apply_rules(_minimal_game(scoring_targets=[
        {"name": "Tall", "height_in": 60, "distance_ft": 0, "auto_pts": 6,
         "teleop_pts": 5, "type": "placement", "distributed": True,
         "cap_type": "capped", "max_alliance_pts": 100},
    ]))
    # When elevator + height > 40, scorer comes before intake
    assert pred["build_order"].index("scorer") < pred["build_order"].index("intake")


def test_rule_log_populated():
    pred = apply_rules(_minimal_game())
    rule_ids = {r["rule"] for r in pred["rule_log"]}
    # Always-firing rules should always be present
    for rid in ("R1", "R2", "R3", "R4", "R6", "R7", "R8", "R10"):
        assert rid in rule_ids


def test_weight_budget_sums_under_limit():
    pred = apply_rules(_minimal_game())
    wb = pred["weight_budget"]
    components = [v for k, v in wb.items() if k.endswith("_lb") and k != "total_limit_lb"]
    assert sum(components) <= wb["total_limit_lb"]


def test_confidence_in_valid_range():
    pred = apply_rules(_minimal_game())
    assert 0.0 <= pred["confidence"] <= 1.0


def test_predict_game_matches_apply_rules():
    game = _minimal_game()
    assert predict_game(game) == apply_rules(game)


def test_predict_from_file_loads_scalar_fields(tmp_path):
    """Round-trip via JSON preserves scalar fields (drivetrain stays swerve, etc.)."""
    game = HISTORICAL_GAMES["2024"]
    json_path = tmp_path / "game.json"
    json_path.write_text(json.dumps(asdict(game)))
    pred = predict_from_file(str(json_path))
    assert pred["drivetrain"]["type"] == "swerve"
    assert pred["game_name"] == game.game_name
    assert pred["year"] == game.year
    assert pred["endgame"]["type"] != "none"  # endgame_type carries over


def test_predict_from_file_full_round_trip(tmp_path):
    """A GameRules → JSON → predict_from_file → same prediction as in-memory.

    Bug fixed: GameRules.from_dict() now uses dataclasses.fields() for proper
    field enumeration, so list-typed fields (scoring_targets) are preserved.
    """
    game = HISTORICAL_GAMES["2024"]
    json_path = tmp_path / "game.json"
    json_path.write_text(json.dumps(asdict(game)))
    pred_from_file = predict_from_file(str(json_path))
    pred_in_memory = apply_rules(game)
    assert pred_from_file["scorer"] == pred_in_memory["scorer"]


def test_predict_from_file_ignores_unknown_keys(tmp_path):
    game = _minimal_game(game_name="EdgeCase")
    data = asdict(game)
    data["totally_made_up_field"] = "ignore me"
    json_path = tmp_path / "game.json"
    json_path.write_text(json.dumps(data))
    pred = predict_from_file(str(json_path))
    assert pred["game_name"] == "EdgeCase"


def test_gamerules_from_dict_round_trip():
    """asdict → from_dict → asdict yields the same dict for all historical games."""
    for year, game in HISTORICAL_GAMES.items():
        data = asdict(game)
        rebuilt = GameRules.from_dict(data)
        assert asdict(rebuilt) == data, f"round-trip failed for {year}"


def test_gamerules_from_dict_drops_unknown_keys():
    """Extra keys in the input dict should not crash from_dict."""
    data = {"game_name": "Test", "year": 2027, "totally_made_up": "ignore me"}
    game = GameRules.from_dict(data)
    assert game.game_name == "Test"
    assert game.year == 2027


def test_gamerules_from_dict_handles_minimal_input():
    """Passing only a name produces a GameRules with all other defaults."""
    game = GameRules.from_dict({"game_name": "Sparse"})
    assert game.game_name == "Sparse"
    assert game.scoring_targets == []  # default_factory respected
    assert game.year == 2027  # default value


def test_gamerules_from_dict_preserves_scoring_targets():
    """The actual bug fix: scoring_targets must survive a from_dict round-trip."""
    original = HISTORICAL_GAMES["2024"]
    data = asdict(original)
    rebuilt = GameRules.from_dict(data)
    assert len(rebuilt.scoring_targets) == len(original.scoring_targets)
    assert rebuilt.scoring_targets == original.scoring_targets


def test_gamerules_to_dict_returns_dict():
    game = HISTORICAL_GAMES["2022"]
    d = game.to_dict()
    assert isinstance(d, dict)
    assert d["game_name"] == "Rapid React"


def test_gamerules_to_dict_includes_scoring_targets():
    """to_dict must include the scoring_targets list (regression check)."""
    game = HISTORICAL_GAMES["2022"]
    d = game.to_dict()
    assert "scoring_targets" in d
    assert len(d["scoring_targets"]) > 0


def test_predict_from_file_preserves_scoring_targets(tmp_path):
    """End-to-end bug fix verification: predict_from_file now produces the
    same scorer prediction as in-memory apply_rules."""
    import json as _json
    game = HISTORICAL_GAMES["2024"]
    json_path = tmp_path / "game.json"
    json_path.write_text(_json.dumps(asdict(game)))
    pred_from_file = predict_from_file(str(json_path))
    pred_in_memory = apply_rules(game)
    assert pred_from_file["scorer"] == pred_in_memory["scorer"]
    assert pred_from_file["intake"]["roller_material"] == pred_in_memory["intake"]["roller_material"]


def test_rule_result_dataclass_construction():
    r = RuleResult("R99", True, "test_rec", 0.5, "test reason")
    assert r.rule_id == "R99"
    assert r.applies is True
    assert r.recommendation == "test_rec"
    assert r.confidence == 0.5
    assert r.reasoning == "test reason"
