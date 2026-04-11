"""Hermetic tests for antenna/live_scout_commands.py.

Strategy
────────
Every test redirects pick_board.STATE_FILE + STATE_DIR at a pytest
tmp_path so:

  - No real draft state is touched.
  - No subprocess is ever spawned (that's the whole point of the
    module we're testing).
  - No network is ever hit. cmd_lookup tests monkey-patch
    statbotics_client; cmd_brief tests write a fake JSON file.

A small `_make_state()` helper builds a realistic 8-captain state
with 16 teams so the richer pick_board functions (recommend_pick,
project_board, predict_captains, sim_playoffs) have enough data to
produce meaningful output.

Covers cmd_rec, cmd_pick, cmd_board, cmd_undo, cmd_dnp, cmd_alliances,
cmd_sim, cmd_captains, cmd_lookup, cmd_brief, cmd_preview, and the
small internal helpers (_team_int, _safe_load_state).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "antenna"))
sys.path.insert(0, str(_ROOT / "scout"))

import live_scout_commands as lsc  # noqa: E402
import pick_board as pb  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────


def _team_dict(
    team: int,
    *,
    name: str | None = None,
    epa: float = 50.0,
    qual_rank: int = 10,
) -> dict:
    """Build a realistic team dict with every field pick_board may read."""
    return {
        "team": team,
        "name": name or f"Team {team}",
        "epa": epa,
        "sd": 10.0,
        "floor": epa - 15,
        "ceiling": epa + 15,
        "epa_auto": epa * 0.25,
        "epa_teleop": epa * 0.55,
        "epa_endgame": epa * 0.20,
        "total_fuel": epa * 0.55,
        "total_tower": epa * 0.20,
        "qual_rank": qual_rank,
        "qual_record": "8-2",
        "wins": 8,
        "losses": 2,
        "ties": 0,
        "eye_composite": 0,
        "eye_confidence": 0,
    }


def _make_state(event_key: str = "2026txbel", our_seed: int = 4) -> dict:
    """Build a realistic 8-captain + 8-non-captain state.

    Our team is 2950 at `our_seed`. EPA spreads from 92 down to 28 so
    recommend_pick has a meaningful ordering.
    """
    state = pb._blank_state()
    state["event_key"] = event_key
    state["our_team"] = 2950
    state["our_seed"] = our_seed

    # 8 captains — EPA 92 → 60, ranked 1-8.
    captains = [
        (148, 92, 1),
        (254, 88, 2),
        (1678, 84, 3),
        (2950, 80, 4),   # us
        (118, 76, 5),
        (2056, 72, 6),
        (1114, 68, 7),
        (1323, 64, 8),
    ]
    state["captains"] = [c[0] for c in captains]
    for team, epa, rank in captains:
        state["teams"][str(team)] = _team_dict(team, epa=epa, qual_rank=rank)

    # 8 non-captains — EPA 58 → 28, ranked 9-16.
    non_caps = [
        (1538, 58, 9),
        (971, 54, 10),
        (604, 50, 11),
        (3476, 46, 12),
        (1690, 42, 13),
        (2910, 38, 14),
        (6328, 34, 15),
        (9999, 28, 16),
    ]
    for team, epa, rank in non_caps:
        state["teams"][str(team)] = _team_dict(team, epa=epa, qual_rank=rank)

    return state


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect pick_board STATE_FILE/STATE_DIR at a tmp file.

    Also flushes lsc's cached pick_board so stale references don't
    leak between tests (not strictly necessary today — lsc imports
    pick_board fresh inside each cmd — but protects against future
    regressions).
    """
    state_dir = tmp_path / "draft"
    state_dir.mkdir()
    state_file = state_dir / "live_draft.json"
    monkeypatch.setattr(pb, "STATE_DIR", state_dir, raising=True)
    monkeypatch.setattr(pb, "STATE_FILE", state_file, raising=True)
    return state_file


def _write(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2))


# ── _team_int ───────────────────────────────────────────────────────


def test_team_int_accepts_plain_integer():
    assert lsc._team_int("148") == 148


def test_team_int_accepts_hash_and_frc_prefix():
    assert lsc._team_int("#148") == 148
    assert lsc._team_int("frc148") == 148
    assert lsc._team_int("FRC148") == 148


def test_team_int_rejects_nonsense():
    assert lsc._team_int("") is None
    assert lsc._team_int("abc") is None
    assert lsc._team_int("0") is None
    assert lsc._team_int("100000") is None
    assert lsc._team_int(None) is None


# ── _safe_load_state ────────────────────────────────────────────────


def test_safe_load_state_missing_file_returns_error(tmp_state):
    state, err = lsc._safe_load_state()
    assert state is None
    assert err and "No active draft" in err


def test_safe_load_state_corrupt_file_returns_error(tmp_state):
    tmp_state.write_text("this is not json {")
    state, err = lsc._safe_load_state()
    assert state is None
    assert err and "unreadable" in err


def test_safe_load_state_happy_path(tmp_state):
    _write(tmp_state, _make_state())
    state, err = lsc._safe_load_state()
    assert err is None
    assert state is not None
    assert state["our_team"] == 2950


# ── cmd_rec ─────────────────────────────────────────────────────────


def test_cmd_rec_no_state_file(tmp_state):
    out = lsc.cmd_rec()
    assert "Error" in out
    assert "No active draft" in out


def test_cmd_rec_with_valid_state(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_rec()
    # Headline + top-10 table
    assert "PICK RECOMMENDATION" in out
    assert "RECOMMENDATION: pick" in out
    # The best non-captain in our state is 1538 (EPA 58); it MUST
    # appear in the top-10 block.
    assert "1538" in out


# ── cmd_pick ────────────────────────────────────────────────────────


def test_cmd_pick_missing_args_returns_usage(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_pick("", "")
    assert "Usage" in out


def test_cmd_pick_bad_alliance_type(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_pick("abc", "1538")
    assert "Error" in out and "integer" in out


def test_cmd_pick_alliance_out_of_range(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_pick("99", "1538")
    assert "Error" in out and "alliance must be" in out


def test_cmd_pick_unknown_team(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_pick("4", "7777")  # 7777 not in state
    assert "Error" in out and "not found" in out


def test_cmd_pick_already_taken(tmp_state):
    _write(tmp_state, _make_state())
    # 148 is the alliance-1 captain, automatically taken.
    out = lsc.cmd_pick("4", "148")
    assert "already taken" in out


def test_cmd_pick_happy_path_persists_state(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_pick("4", "1538")
    assert "RECORDED" in out

    # State on disk now has exactly one entry in history + picks.
    reloaded = json.loads(tmp_state.read_text())
    assert len(reloaded["picks"]) == 1
    assert reloaded["picks"][0]["team"] == 1538
    assert reloaded["picks"][0]["alliance"] == 4
    assert len(reloaded["history"]) == 1


# ── cmd_board ───────────────────────────────────────────────────────


def test_cmd_board_renders_alliances(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_board()
    assert "PICK BOARD" in out
    assert "CURRENT ALLIANCES" in out
    assert "← US" in out  # our alliance marker
    # All 8 captains should render as A1..A8 lines.
    for a in range(1, 9):
        assert f"A{a}" in out


# ── cmd_undo ────────────────────────────────────────────────────────


def test_cmd_undo_empty_history(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_undo()
    assert "Nothing to undo" in out


def test_cmd_undo_rolls_back_pick(tmp_state):
    _write(tmp_state, _make_state())
    lsc.cmd_pick("4", "1538")
    out = lsc.cmd_undo()
    assert "Undid" in out and "1538" in out
    reloaded = json.loads(tmp_state.read_text())
    assert reloaded["picks"] == []
    assert reloaded["history"] == []


# ── cmd_dnp ─────────────────────────────────────────────────────────


def test_cmd_dnp_empty_list(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_dnp()
    assert "No teams on DNP" in out


def test_cmd_dnp_toggle_add_then_remove(tmp_state):
    _write(tmp_state, _make_state())
    out1 = lsc.cmd_dnp("9999")
    assert "added to DNP" in out1
    reloaded = json.loads(tmp_state.read_text())
    assert 9999 in reloaded["dnp"]

    out2 = lsc.cmd_dnp("9999")
    assert "removed from DNP" in out2
    reloaded = json.loads(tmp_state.read_text())
    assert 9999 not in reloaded["dnp"]


def test_cmd_dnp_unknown_team(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_dnp("7777")
    assert "not found" in out


def test_cmd_dnp_shows_populated_list(tmp_state):
    state = _make_state()
    state["dnp"] = [1538, 971]
    _write(tmp_state, state)
    out = lsc.cmd_dnp()
    assert "1538" in out and "971" in out
    assert "2 teams" in out


# ── cmd_alliances ───────────────────────────────────────────────────


def test_cmd_alliances_all_captains(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_alliances()
    assert "ALLIANCES" in out
    for a in range(1, 9):
        assert f"A{a}" in out
    assert "← US" in out


# ── cmd_sim ─────────────────────────────────────────────────────────


def test_cmd_sim_small_n_returns_output(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_sim("100")
    assert "PLAYOFF SIM" in out
    # sim_playoffs prints each alliance; our alliance should appear.
    assert "2950" in out or "A4" in out


def test_cmd_sim_bad_n_sims(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_sim("abc")
    assert "Error" in out and "integer" in out


# ── cmd_captains ────────────────────────────────────────────────────


def test_cmd_captains_predicts_eight(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_captains()
    assert "PREDICTED CAPTAIN PICKS" in out
    assert "R1 predictions" in out
    # All 8 alliances should show a picks line.
    for a in range(1, 9):
        assert f"A{a}" in out
    assert "Projected final captains" in out


# ── cmd_lookup ──────────────────────────────────────────────────────


def test_cmd_lookup_missing_team():
    out = lsc.cmd_lookup("")
    assert "Usage" in out


def test_cmd_lookup_bad_team():
    out = lsc.cmd_lookup("abc")
    assert "Error" in out and "invalid team" in out


def test_cmd_lookup_happy_path_monkeypatched(monkeypatch):
    """Stub out statbotics_client so we don't touch the network."""
    import statbotics_client as sc

    class _FakeEPA:
        epa_total = 72.1
        epa_rank = 25
        epa_auto = 18.0
        auto_pct = 25.0
        epa_teleop = 40.0
        teleop_pct = 55.0
        epa_endgame = 14.1
        endgame_pct = 20.0
        wins = 20
        losses = 5
        ties = 0
        winrate = 0.80

    class _FakeEvent:
        event = "2025txhou"
        epa_total = 70.0
        epa_auto = 18.0
        epa_teleop = 38.0
        epa_endgame = 14.0

    monkeypatch.setattr(sc, "get_team_year", lambda team, year: _FakeEPA())
    monkeypatch.setattr(
        sc, "get_team_events_in_year", lambda team, year: [_FakeEvent()]
    )
    monkeypatch.setattr(sc, "epa_trend", lambda events: "stable")

    out = lsc.cmd_lookup("148")
    assert "TEAM 148" in out
    assert "72.1" in out
    assert "EVENT HISTORY" in out


# ── cmd_brief ───────────────────────────────────────────────────────


def test_cmd_brief_no_event_key_and_no_state(tmp_state):
    out = lsc.cmd_brief()
    # No state file + no event_key arg → usage hint
    assert "Usage" in out or "Error" in out


def test_cmd_brief_file_missing(tmp_path, monkeypatch):
    # Point the module's _REPO_ROOT at a blank tmp dir so no brief
    # can possibly exist.
    monkeypatch.setattr(lsc, "_REPO_ROOT", tmp_path)
    out = lsc.cmd_brief("2026txbel")
    assert "Error" in out and "no brief yet" in out


def test_cmd_brief_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(lsc, "_REPO_ROOT", tmp_path)
    briefs = tmp_path / "workers" / ".state" / "briefs"
    briefs.mkdir(parents=True)
    (briefs / "brief_2026txbel.json").write_text(
        json.dumps({"dry_run": True, "event_key": "2026txbel"})
    )
    out = lsc.cmd_brief("2026txbel")
    assert "DRY-RUN" in out


def test_cmd_brief_real_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(lsc, "_REPO_ROOT", tmp_path)
    briefs = tmp_path / "workers" / ".state" / "briefs"
    briefs.mkdir(parents=True)
    (briefs / "brief_2026txbel.json").write_text(json.dumps({
        "dry_run": False,
        "event_key": "2026txbel",
        "our_team": 2950,
        "generated_at": "2026-04-11T12:00Z",
        "model": "claude-opus-4",
        "summary": "Pick 1538, avoid 9999.",
        "top_picks": [1538, 971, 604],
    }))
    out = lsc.cmd_brief("2026txbel")
    assert "STRATEGIC BRIEF" in out
    assert "Pick 1538" in out
    assert "1538" in out


# ── cmd_preview ─────────────────────────────────────────────────────


# ── cmd_status ──────────────────────────────────────────────────────


def test_cmd_status_no_draft(tmp_state):
    # No state file → reports "no state file" without crashing.
    out = lsc.cmd_status()
    assert "LIVE SCOUT STATUS" in out
    assert "no state file" in out


def test_cmd_status_with_draft(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_status()
    assert "LIVE SCOUT STATUS" in out
    assert "2026txbel" in out
    assert "DRAFT" in out


def test_cmd_status_shows_pick_counts(tmp_state):
    # After recording a pick the status should reflect it.
    _write(tmp_state, _make_state())
    lsc.cmd_pick("4", "1538")  # record one pick
    out = lsc.cmd_status()
    # State was updated: 1 pick should be visible somewhere in output
    assert "pick#1" in out


# ── cmd_preview ─────────────────────────────────────────────────────


def test_cmd_preview_missing_team(tmp_state):
    _write(tmp_state, _make_state())
    out = lsc.cmd_preview("")
    assert "Usage" in out


def test_cmd_preview_no_event(tmp_state):
    # No state on disk → no active event → error.
    out = lsc.cmd_preview("148")
    assert "Error" in out and "no active event" in out


def test_cmd_preview_team_not_at_event(tmp_state, monkeypatch):
    _write(tmp_state, _make_state())
    # Mock build_report_for_team to return "" (team not found at event).
    import pre_event_report as per
    monkeypatch.setattr(per, "build_report_for_team", lambda event, team, **kw: "")
    out = lsc.cmd_preview("7777")
    assert "Error" in out and "no pre-event report" in out


def test_cmd_preview_real_report(tmp_state, monkeypatch):
    _write(tmp_state, _make_state())
    # Mock build_report_for_team to return a realistic one-team report.
    import pre_event_report as per
    fake_report = (
        "TEAM 1538 — RoboJackets\n"
        "Rank at 2026txbel: #9 of 40\n"
        "EPA: 58.0  (avg 50.0)\n"
        "  Auto:    14.5\n"
        "  Teleop:  31.9\n"
        "  Endgame: 11.6\n"
        "Trend: stable  (+2%)\n"
        "Scouting priority: HIGH — Top EPA — potential alliance pick"
    )
    monkeypatch.setattr(per, "build_report_for_team", lambda event, team, **kw: fake_report)
    out = lsc.cmd_preview("1538")
    assert "PREVIEW — 1538" in out
    assert "RoboJackets" in out
    assert "EPA" in out
