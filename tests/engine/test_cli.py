"""Smoke tests for the unified `engine` CLI (Click)."""
from __future__ import annotations

from unittest import mock

import pytest
from click.testing import CliRunner

from engine.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_top_level_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    # All 7 sub-commands should be advertised in help output.
    for cmd in (
        "predict",
        "pick-board",
        "match-brief",
        "pre-event",
        "game-analysis",
        "tune-beta",
        "status",
    ):
        assert cmd in result.output


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "engine" in result.output.lower()


def test_status_prints_version_and_counts(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "engine version" in result.output
    assert "tests" in result.output
    assert "oracle rules" in result.output


def test_predict_bad_arg(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["predict", "/nonexistent/path/does_not_exist.json"])
    # Click raises BadParameter on unknown example / missing file
    assert result.exit_code != 0


def test_predict_delegates_to_oracle(runner: CliRunner) -> None:
    fake_game = mock.MagicMock()
    fake_pred = {"winner": "red"}
    with mock.patch("blueprint.oracle.HISTORICAL_GAMES", {"2022": fake_game}), \
         mock.patch("blueprint.oracle.apply_rules", return_value=fake_pred) as apply_rules, \
         mock.patch("blueprint.oracle.display_prediction") as display:
        result = runner.invoke(cli, ["predict", "2022"])
    assert result.exit_code == 0, result.output
    apply_rules.assert_called_once_with(fake_game)
    display.assert_called_once_with(fake_pred)


def test_match_brief_delegates(runner: CliRunner) -> None:
    fake_brief = mock.MagicMock()
    with mock.patch("scout.match_brief.generate_match_brief", return_value=fake_brief) as gen, \
         mock.patch("scout.match_brief.render_markdown", return_value="# brief") as render:
        result = runner.invoke(cli, ["match-brief", "--match", "2025wor_qm1", "--team", "2950"])
    assert result.exit_code == 0, result.output
    gen.assert_called_once()
    kwargs = gen.call_args.kwargs
    assert kwargs["event_key"] == "2025wor"
    assert kwargs["match_key"] == "2025wor_qm1"
    assert kwargs["year"] == 2025
    assert kwargs["our_team_number"] == 2950
    render.assert_called_once_with(fake_brief)


def test_match_brief_requires_match(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["match-brief"])
    assert result.exit_code != 0
    assert "--match" in result.output or "Missing option" in result.output


def test_pick_board_requires_state(runner: CliRunner, tmp_path) -> None:
    # Point STATE_FILE at a non-existent path to force the "no state" branch.
    missing = tmp_path / "state.json"
    with mock.patch("scout.pick_board.STATE_FILE", missing):
        result = runner.invoke(cli, ["pick-board", "--event", "2025txcmp2"])
    assert result.exit_code == 2
    assert "No pick-board state" in result.output


def test_pre_event_delegates(runner: CliRunner) -> None:
    with mock.patch("scout.pre_event_report.build_profiles", return_value=[]) as build, \
         mock.patch("scout.pre_event_report.display_report") as disp, \
         mock.patch("scout.pre_event_report.save_report") as save:
        result = runner.invoke(cli, ["pre-event", "--event", "2025txcmp2"])
    assert result.exit_code == 0, result.output
    build.assert_called_once()
    disp.assert_called_once()
    save.assert_called_once()


def test_tune_beta_delegates(runner: CliRunner) -> None:
    fake_result = mock.MagicMock(best_beta=0.85, n_matches=0, status="OK")
    with mock.patch("blueprint.tune_attribution_beta.tune_beta_for_season", return_value=fake_result) as tune, \
         mock.patch("blueprint.tune_attribution_beta.fetch_season_matches", create=True, return_value=[]):
        result = runner.invoke(cli, ["tune-beta", "--year", "2024"])
    assert result.exit_code == 0, result.output
    tune.assert_called_once()
    assert "best_beta=0.85" in result.output


def test_game_analysis_delegates(runner: CliRunner, tmp_path) -> None:
    fake_report = mock.MagicMock()
    out = tmp_path / "analysis.md"
    with mock.patch("scout.game_analysis.generate_game_analysis", return_value=fake_report) as gen, \
         mock.patch("scout.game_analysis.render_markdown", return_value="# report") as render:
        result = runner.invoke(cli, ["game-analysis", "--year", "2024", "--output", str(out)])
    assert result.exit_code == 0, result.output
    gen.assert_called_once_with(2024)
    render.assert_called_once_with(fake_report)
    assert out.with_suffix(".md").exists()
