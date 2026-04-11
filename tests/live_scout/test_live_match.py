"""Tests for scout/live_match.py — LiveMatch dataclass + serialization."""

import json
import sys
from pathlib import Path

import pytest

# Make scout/ importable for the tests
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402


# ─── Fixtures ───


def _valid_match_kwargs(**overrides):
    base = dict(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        match_num=32,
        comp_level="qm",
        red_teams=[2950, 1234, 5678],
        blue_teams=[148, 254, 1678],
        red_score=88,
        blue_score=72,
        winning_alliance="red",
        timer_state="post",
        source_video_id="abc123",
        source_tier="vod",
        confidence=0.97,
    )
    base.update(overrides)
    return base


def _valid_match(**overrides) -> LiveMatch:
    return LiveMatch(**_valid_match_kwargs(**overrides))


# ─── Construction + validation ───


def test_construct_valid_qm_match():
    m = _valid_match()
    assert m.event_key == "2026txbel"
    assert m.match_num == 32
    assert m.is_complete
    assert m.processed_at > 0  # auto-stamped


def test_construct_valid_playoff_match():
    m = _valid_match(
        match_key="2026txbel_qf1m1",
        match_num=1,
        comp_level="qf",
    )
    assert m.comp_level == "qf"


@pytest.mark.parametrize("bad_event_key", [
    "txbel",            # missing year
    "2026TXBEL",        # uppercase
    "2026_txbel",       # underscore in event prefix
    "26txbel",          # 2-digit year
    "",
])
def test_invalid_event_key_rejected(bad_event_key):
    with pytest.raises(ValueError, match="event_key"):
        _valid_match(event_key=bad_event_key, match_key=f"{bad_event_key}_qm32")


@pytest.mark.parametrize("bad_match_key", [
    "2026txbel-qm32",     # dash instead of underscore
    "2026txbel_QM32",     # uppercase level
    "2026txbel_qm",       # missing number
    "qm32",               # missing event prefix
    "",
])
def test_invalid_match_key_rejected(bad_match_key):
    with pytest.raises(ValueError, match="match_key"):
        _valid_match(match_key=bad_match_key)


def test_match_key_event_prefix_must_match_event_key():
    with pytest.raises(ValueError, match="event prefix"):
        _valid_match(event_key="2026txbel", match_key="2026txdri_qm32")


def test_match_key_level_must_match_comp_level():
    with pytest.raises(ValueError, match="level"):
        _valid_match(match_key="2026txbel_qf1m1", comp_level="qm")


def test_match_key_num_must_match_match_num():
    with pytest.raises(ValueError, match="num"):
        _valid_match(match_key="2026txbel_qm32", match_num=99)


def test_invalid_comp_level():
    with pytest.raises(ValueError, match="comp_level"):
        _valid_match(comp_level="quals", match_key="2026txbel_qm32")


def test_invalid_timer_state():
    with pytest.raises(ValueError, match="timer_state"):
        _valid_match(timer_state="halftime")


def test_invalid_source_tier():
    with pytest.raises(ValueError, match="source_tier"):
        _valid_match(source_tier="recorded")


def test_invalid_winning_alliance():
    with pytest.raises(ValueError, match="winning_alliance"):
        _valid_match(winning_alliance="purple")


def test_confidence_out_of_range():
    with pytest.raises(ValueError, match="confidence"):
        _valid_match(confidence=1.5)


def test_invalid_team_number():
    with pytest.raises(ValueError, match="red_teams"):
        _valid_match(red_teams=[2950, 0, 5678])


def test_team_numbers_must_be_ints():
    with pytest.raises(ValueError, match="red_teams"):
        _valid_match(red_teams=["2950", "1234", "5678"])


# ─── Serialization round-trip ───


def test_to_dict_round_trip():
    original = _valid_match()
    restored = LiveMatch.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()


def test_to_json_round_trip():
    original = _valid_match()
    restored = LiveMatch.from_json(original.to_json())
    assert restored.to_dict() == original.to_dict()


def test_from_dict_drops_unknown_fields():
    """Schema evolution: older state files with extra keys should still load."""
    data = _valid_match().to_dict()
    data["legacy_field_we_dropped"] = "should be ignored"
    data["another_unknown"] = 42
    restored = LiveMatch.from_dict(data)
    assert restored.match_key == "2026txbel_qm32"


def test_to_json_is_stable_sorted():
    """Stable key order so two equivalent records hash identically."""
    a = _valid_match().to_json()
    b = _valid_match().to_json()
    # Both should produce the same string given the same processed_at
    a_dict = json.loads(a)
    b_dict = json.loads(b)
    a_dict.pop("processed_at")
    b_dict.pop("processed_at")
    assert a_dict == b_dict


# ─── Convenience properties ───


def test_is_complete_when_both_scores_set():
    assert _valid_match().is_complete


def test_is_not_complete_when_red_score_missing():
    m = _valid_match(red_score=None)
    assert not m.is_complete


def test_all_teams_concatenates_red_and_blue():
    m = _valid_match()
    assert m.all_teams == [2950, 1234, 5678, 148, 254, 1678]


def test_winner_from_scores_red():
    m = _valid_match(red_score=100, blue_score=50)
    assert m.winner_from_scores() == "red"


def test_winner_from_scores_blue():
    m = _valid_match(red_score=50, blue_score=100, winning_alliance="blue")
    assert m.winner_from_scores() == "blue"


# ─── Phase 2 vision fields ───


def test_vision_fields_default_to_empty_containers():
    m = _valid_match()
    assert m.vision_events == []
    assert m.cycle_counts == {}
    assert m.climb_results == {}


def test_vision_fields_round_trip_through_json():
    m = _valid_match(
        vision_events=[
            {"frame_idx": 30, "event_type": "cycle", "team_num": 2950, "confidence": 0.91},
            {"frame_idx": 45, "event_type": "climb_success", "team_num": 1678, "confidence": 0.88},
        ],
        cycle_counts={"2950": 7, "1234": 5, "1678": 6},
        climb_results={"2950": "success", "1234": "attempt", "1678": "success"},
    )
    restored = LiveMatch.from_json(m.to_json())
    assert restored.vision_events == m.vision_events
    assert restored.cycle_counts == m.cycle_counts
    assert restored.climb_results == m.climb_results


def test_invalid_vision_event_type_rejected():
    with pytest.raises(ValueError, match="invalid vision event_type"):
        _valid_match(vision_events=[{"event_type": "teleporting"}])


def test_vision_events_must_be_list_of_dicts():
    with pytest.raises(ValueError, match="vision_events entries must be dict"):
        _valid_match(vision_events=["not a dict"])


def test_cycle_counts_must_be_str_to_int():
    with pytest.raises(ValueError, match="cycle_counts entry"):
        _valid_match(cycle_counts={"2950": -1})


def test_climb_results_must_use_valid_categories():
    with pytest.raises(ValueError, match="climb_results entry"):
        _valid_match(climb_results={"2950": "yeeted into space"})


def test_winner_from_scores_tie():
    m = _valid_match(red_score=80, blue_score=80, winning_alliance="tie")
    assert m.winner_from_scores() == "tie"


def test_winner_from_scores_returns_none_when_incomplete():
    m = _valid_match(red_score=None, blue_score=None, winning_alliance=None)
    assert m.winner_from_scores() is None
