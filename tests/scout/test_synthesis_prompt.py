"""Tests for scout/synthesis_prompt.py — Phase 2 T3 S1.

Pure-logic module: no network I/O, no pick_board I/O. Fixtures are
plain dicts so we can drift-proof the aggregate shapes.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from synthesis_prompt import (  # noqa: E402
    SynthesisInputs,
    build_synthesis_prompt,
    collect_synthesis_inputs,
    dump_inputs_json,
)


# ─── Fixtures ───


def _team(team, *, real_avg=None, epa=40.0, sd=0.0, real_sd=None,
          streak="", rank=99, record="0-0", name=""):
    return {
        "team": team,
        "name": name or f"Team{team}",
        "epa": epa,
        "sd": sd,
        "real_avg_score": real_avg,
        "real_sd": real_sd if real_sd is not None else sd,
        "streak": streak,
        "qual_rank": rank,
        "qual_record": record,
    }


def _match(match_num, red, blue, *, red_score=None, blue_score=None,
           winner=None, comp_level="qm", event_key="2026txbel"):
    return {
        "event_key": event_key,
        "match_key": f"{event_key}_{comp_level}{match_num}",
        "match_num": match_num,
        "comp_level": comp_level,
        "red_teams": list(red),
        "blue_teams": list(blue),
        "red_score": red_score,
        "blue_score": blue_score,
        "winning_alliance": winner,
    }


def _state(*, teams=None, matches=None, dnp=None, captains=None):
    return {
        "event_key": "2026txbel",
        "teams": {str(t["team"]): t for t in (teams or [])},
        "live_matches": {m["match_key"]: m for m in (matches or [])},
        "dnp": list(dnp or []),
        "captains": list(captains or []),
    }


# ─── collect_synthesis_inputs ───


def test_collect_happy_path_ranks_by_real_avg():
    state = _state(
        teams=[
            _team(2950, real_avg=80.0, rank=2, record="8-2"),
            _team(148, real_avg=95.0, rank=1, record="9-1"),
            _team(1678, real_avg=70.0, rank=5, record="6-4"),
        ],
        matches=[
            _match(1, [2950, 148, 1678], [1234, 5678, 9012],
                   red_score=100, blue_score=80, winner="red"),
        ],
    )
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=2950)
    assert [t["team"] for t in inputs.top_teams] == [148, 2950, 1678]
    assert len(inputs.recent_matches) == 1
    assert inputs.recent_matches[0]["red_score"] == 100


def test_collect_falls_back_to_epa_when_no_live_data():
    state = _state(teams=[
        _team(148, real_avg=None, epa=85.0),
        _team(2950, real_avg=None, epa=90.0),
    ])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=2950)
    assert [t["team"] for t in inputs.top_teams] == [2950, 148]


def test_collect_tiebreaks_by_sd_then_team_number():
    state = _state(teams=[
        _team(11, real_avg=80.0, sd=5.0, real_sd=5.0),
        _team(22, real_avg=80.0, sd=3.0, real_sd=3.0),  # lower SD wins
        _team(33, real_avg=80.0, sd=5.0, real_sd=5.0),  # same as 11 → lower number wins
    ])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=11)
    assert [t["team"] for t in inputs.top_teams] == [22, 11, 33]


def test_collect_top_n_cap():
    state = _state(teams=[_team(i, real_avg=float(100 - i)) for i in range(1, 40)])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=1, top_n=5)
    assert len(inputs.top_teams) == 5
    # Ranked descending — team 1 has highest real_avg (99), team 2 (98)...
    assert [t["team"] for t in inputs.top_teams] == [1, 2, 3, 4, 5]


def test_collect_recent_n_cap_from_tail():
    state = _state(matches=[
        _match(i, [1, 2, 3], [4, 5, 6], red_score=10 * i, blue_score=5 * i, winner="red")
        for i in range(1, 20)
    ])
    inputs = collect_synthesis_inputs(
        state, "2026txbel", our_team=1, recent_n=3,
    )
    assert len(inputs.recent_matches) == 3
    assert [m["match_num"] for m in inputs.recent_matches] == [17, 18, 19]


def test_collect_filters_matches_by_event_key():
    other = _match(5, [1, 2, 3], [4, 5, 6], event_key="2026txdri")
    ours = _match(5, [1, 2, 3], [4, 5, 6], red_score=90, blue_score=80, winner="red")
    state = _state(matches=[other, ours])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=1)
    assert len(inputs.recent_matches) == 1
    assert inputs.recent_matches[0]["match_key"] == "2026txbel_qm5"


def test_collect_upcoming_matches_only_unscored_with_our_team():
    state = _state(matches=[
        # Past match (scored) — excluded even though our team is on it
        _match(1, [2950, 148, 1678], [1, 2, 3], red_score=50, blue_score=40, winner="red"),
        # Upcoming with our team
        _match(10, [2950, 9, 10], [11, 12, 13]),
        # Upcoming without our team — excluded
        _match(11, [14, 15, 16], [17, 18, 19]),
        # Upcoming with our team on blue
        _match(12, [20, 21, 22], [2950, 23, 24]),
    ])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=2950)
    nums = [m["match_num"] for m in inputs.next_opponent_matches]
    assert nums == [10, 12]
    assert inputs.next_opponent_matches[0]["our_alliance"] == "red"
    assert inputs.next_opponent_matches[0]["partners"] == [9, 10]
    assert inputs.next_opponent_matches[0]["opponents"] == [11, 12, 13]
    assert inputs.next_opponent_matches[1]["our_alliance"] == "blue"
    assert inputs.next_opponent_matches[1]["partners"] == [23, 24]
    assert inputs.next_opponent_matches[1]["opponents"] == [20, 21, 22]


def test_collect_empty_state_returns_empty_fields():
    inputs = collect_synthesis_inputs({}, "2026txbel", our_team=2950)
    assert inputs.top_teams == []
    assert inputs.recent_matches == []
    assert inputs.next_opponent_matches == []
    assert inputs.our_team == 2950


def test_collect_carries_dnp_and_captains():
    state = _state(dnp=[9999, 8888], captains=[148, 254, 2950])
    inputs = collect_synthesis_inputs(state, "2026txbel", our_team=2950)
    assert inputs.dnp == [9999, 8888]
    assert inputs.captains == [148, 254, 2950]


def test_collect_top_n_zero_returns_empty():
    state = _state(teams=[_team(2950, real_avg=99.0)])
    inputs = collect_synthesis_inputs(
        state, "2026txbel", our_team=2950, top_n=0,
    )
    assert inputs.top_teams == []


# ─── build_synthesis_prompt ───


def test_build_prompt_returns_system_and_user_tuple():
    inputs = SynthesisInputs(
        event_key="2026txbel",
        our_team=2950,
        top_teams=[_team(148, real_avg=95.0, rank=1, record="9-1", streak="HOT")],
        recent_matches=[{
            "match_key": "2026txbel_qm1",
            "comp_level": "qm",
            "match_num": 1,
            "red_teams": [148, 1, 2],
            "blue_teams": [3, 4, 5],
            "red_score": 100,
            "blue_score": 80,
            "winning_alliance": "red",
        }],
        next_opponent_matches=[{
            "match_key": "2026txbel_qm32",
            "match_num": 32,
            "our_alliance": "red",
            "partners": [11, 12],
            "opponents": [13, 14, 15],
        }],
    )
    system, user = build_synthesis_prompt(inputs)
    assert "FRC Team 2950" in system
    assert "2026txbel" in user
    assert "OUR TEAM: 2950" in user
    assert "#148" in user
    assert "HOT" in user
    assert "2026txbel_qm1" in user
    assert "2026txbel_qm32" in user
    assert "partners: 11/12" in user


def test_build_prompt_empty_state_still_formats_cleanly():
    inputs = SynthesisInputs(
        event_key="2026txbel", our_team=2950,
        top_teams=[], recent_matches=[], next_opponent_matches=[],
    )
    system, user = build_synthesis_prompt(inputs)
    assert "no team data yet" in user
    assert "no live matches yet" in user
    assert "none scheduled" in user


def test_build_prompt_uses_epa_when_real_avg_missing():
    inputs = SynthesisInputs(
        event_key="2026txbel", our_team=2950,
        top_teams=[_team(148, real_avg=None, epa=87.5)],
        recent_matches=[], next_opponent_matches=[],
    )
    _, user = build_synthesis_prompt(inputs)
    assert "epa=87.5" in user
    assert "live=" not in user


def test_build_prompt_shows_dnp_and_captains():
    inputs = SynthesisInputs(
        event_key="2026txbel", our_team=2950,
        top_teams=[], recent_matches=[], next_opponent_matches=[],
        dnp=[1234], captains=[148, 254],
    )
    _, user = build_synthesis_prompt(inputs)
    assert "DO NOT PICK: 1234" in user
    assert "148, 254" in user


# ─── dump_inputs_json ───


def test_dump_inputs_json_is_valid_json():
    import json as _json
    inputs = SynthesisInputs(
        event_key="2026txbel", our_team=2950,
        top_teams=[_team(148, real_avg=95.0)],
        recent_matches=[],
        next_opponent_matches=[],
    )
    parsed = _json.loads(dump_inputs_json(inputs))
    assert parsed["event_key"] == "2026txbel"
    assert parsed["our_team"] == 2950
    assert parsed["top_teams"][0]["team"] == 148
