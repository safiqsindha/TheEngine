"""Tests for pick_board.py cmd_setup --force flag.

The --force path preserves picks/history/dnp/live_matches from the
existing state file while overwriting event_key/our_team/our_seed/
captains/teams. All tests monkeypatch get_event_teams so there are
no network calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

import pick_board as pb  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────

def _fake_raw_team(team: int, rank: int = 1, epa: float = 50.0) -> dict:
    """Minimal Statbotics event-team dict that _parse_team can handle."""
    return {
        "team": team,
        "team_name": f"Team {team}",
        "epa": {
            "total_points": {"mean": epa, "sd": 10.0},
            "breakdown": {
                "auto_points": epa * 0.25,
                "teleop_points": epa * 0.55,
                "endgame_points": epa * 0.20,
            },
        },
        "record": {"qual": {"rank": rank, "wins": 8, "losses": 2}},
    }


def _fake_event_teams(n: int = 16) -> list:
    return [_fake_raw_team(1000 + i, rank=i + 1, epa=80.0 - i * 2) for i in range(n)]


@pytest.fixture
def tmp_pb(tmp_path, monkeypatch):
    """Redirect pick_board STATE_FILE/STATE_DIR at tmp_path."""
    state_dir = tmp_path / "draft"
    state_dir.mkdir()
    state_file = state_dir / "live_draft.json"
    monkeypatch.setattr(pb, "STATE_DIR", state_dir, raising=True)
    monkeypatch.setattr(pb, "STATE_FILE", state_file, raising=True)
    # Patch the name as it's bound in pick_board's namespace so cmd_setup
    # never calls the real Statbotics endpoint.
    monkeypatch.setattr(pb, "get_event_teams", lambda event_key: _fake_event_teams())
    return state_file


# ── Tests ────────────────────────────────────────────────────────────

def test_setup_creates_state_file(tmp_pb, capsys):
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    assert tmp_pb.exists()
    state = json.loads(tmp_pb.read_text())
    assert state["event_key"] == "2026txbel"
    assert state["our_team"] == 1003
    assert state["our_seed"] == 4
    assert len(state["teams"]) == 16


def test_setup_refuses_overwrite_without_force(tmp_pb, capsys):
    # First setup — no existing file.
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    # Second setup without --force should print an error and NOT overwrite.
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "5"])
    out = capsys.readouterr().out
    assert "already exists" in out or "ERROR" in out
    # Seed should still be 4 (original).
    state = json.loads(tmp_pb.read_text())
    assert state["our_seed"] == 4


def test_setup_force_updates_seed(tmp_pb):
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "2", "--force"])
    state = json.loads(tmp_pb.read_text())
    assert state["our_seed"] == 2


def test_setup_force_preserves_picks(tmp_pb):
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    # Inject a fake pick and DNP entry into the state.
    state = json.loads(tmp_pb.read_text())
    state["picks"] = [{"alliance": 4, "team": 1010, "round": 1}]
    state["dnp"] = [1011]
    state["history"] = [json.dumps([])]
    tmp_pb.write_text(json.dumps(state))

    # Re-setup with --force (seed correction after qual rankings posted).
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "2", "--force"])
    after = json.loads(tmp_pb.read_text())

    assert after["our_seed"] == 2
    assert len(after["picks"]) == 1
    assert after["picks"][0]["team"] == 1010
    assert 1011 in after["dnp"]
    assert len(after["history"]) == 1


def test_setup_force_clears_live_matches_replaced_by_fresh_teams(tmp_pb):
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    state = json.loads(tmp_pb.read_text())
    state["live_matches"] = {"2026txbel_qm1": {"red_score": 80, "blue_score": 60}}
    tmp_pb.write_text(json.dumps(state))

    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "3", "--force"])
    after = json.loads(tmp_pb.read_text())

    assert after["our_seed"] == 3
    assert "2026txbel_qm1" in after["live_matches"]


def test_setup_force_teams_refreshed(tmp_pb, monkeypatch):
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4"])
    orig_count = len(json.loads(tmp_pb.read_text())["teams"])

    # Simulate a teams DB that gained one more team (event team list updated).
    bigger = _fake_event_teams(n=20)
    monkeypatch.setattr(pb, "get_event_teams", lambda event_key: bigger)
    pb.cmd_setup(["2026txbel", "--team", "1003", "--seed", "4", "--force"])
    after = json.loads(tmp_pb.read_text())

    assert len(after["teams"]) == 20
    assert len(after["teams"]) > orig_count
