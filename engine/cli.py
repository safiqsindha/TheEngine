"""Unified `engine` CLI — consolidates scattered entrypoints.

Each sub-command delegates to existing module functions. No logic is
reimplemented here; the CLI is a thin Click wrapper for discoverability.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

ROOT = Path(__file__).resolve().parent.parent

__version__ = "1.0.0"


@click.group(help="The Engine — unified CLI for prediction, scouting, and tuning.")
@click.version_option(__version__, prog_name="engine")
def cli() -> None:
    """Top-level group."""


# ---------------------------------------------------------------------------
# engine predict <event>
# ---------------------------------------------------------------------------
@cli.command("predict", help="Run oracle prediction for an event / game rules file.")
@click.argument("event")
def predict_cmd(event: str) -> None:
    from blueprint import oracle

    # Accept either --example-YEAR / file path / 4-digit year shorthand
    game = None
    path = Path(event)
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        game = oracle.GameRules(
            **{k: v for k, v in data.items() if hasattr(oracle.GameRules, k)}
        )
    else:
        # try historical key (e.g. "2022")
        key = event.lstrip("-").replace("example-", "")
        hist = getattr(oracle, "HISTORICAL_GAMES", {})
        if key in hist:
            game = hist[key]
        elif event in hist:
            game = hist[event]

    if game is None:
        raise click.BadParameter(
            f"'{event}' is not an example key ({list(getattr(oracle, 'HISTORICAL_GAMES', {}).keys())}) "
            "or an existing game-rules JSON path."
        )

    pred = oracle.apply_rules(game)
    oracle.display_prediction(pred)


# ---------------------------------------------------------------------------
# engine pick-board --event <key> [--year N]
# ---------------------------------------------------------------------------
@cli.command("pick-board", help="Build / display the live alliance pick board.")
@click.option("--event", "event_key", required=True, help="TBA event key (e.g. 2025txcmp2).")
@click.option("--year", type=int, default=None, help="FRC season year (default: inferred from event).")
def pick_board_cmd(event_key: str, year: Optional[int]) -> None:
    from scout import pick_board

    state_path = getattr(pick_board, "STATE_FILE", None)
    if state_path is None or not Path(state_path).exists():
        click.echo(
            "No pick-board state found. Run `pick_board.py setup <event> --team N --seed N` first.",
            err=True,
        )
        sys.exit(2)

    state = pick_board.load_state()
    if state.get("event_key") and state["event_key"] != event_key:
        click.echo(
            f"State event_key={state['event_key']!r} does not match --event {event_key!r}.",
            err=True,
        )
        sys.exit(2)

    board = pick_board.project_board(state)
    year = year or int(event_key[:4]) if event_key[:4].isdigit() else 2025
    click.echo(f"[pick-board] {event_key} year={year} — {len(board)} teams projected")
    pick_board.cmd_board([])


# ---------------------------------------------------------------------------
# engine match-brief --match <key>
# ---------------------------------------------------------------------------
@cli.command("match-brief", help="Generate a pre-match brief for drive team.")
@click.option("--match", "match_key", required=True, help="Match key (e.g. 2025wor_qm1 or qm1).")
@click.option("--event", "event_key", default=None, help="TBA event key (inferred from match key if omitted).")
@click.option("--team", type=int, default=2950, show_default=True, help="Our team number.")
@click.option("--year", type=int, default=None, help="Season year (default: inferred).")
def match_brief_cmd(match_key: str, event_key: Optional[str], team: int, year: Optional[int]) -> None:
    from scout import match_brief

    if event_key is None:
        # match keys often look like 2025wor_qm1
        if "_" in match_key:
            event_key = match_key.split("_", 1)[0]
        else:
            raise click.BadParameter("--event is required when --match has no event prefix.")

    if year is None:
        try:
            year = int(event_key[:4])
        except (ValueError, TypeError):
            year = 2025

    brief = match_brief.generate_match_brief(
        event_key=event_key,
        match_key=match_key,
        year=year,
        our_team_number=team,
    )
    click.echo(match_brief.render_markdown(brief))


# ---------------------------------------------------------------------------
# engine pre-event --event <key>
# ---------------------------------------------------------------------------
@cli.command("pre-event", help="Generate pre-event scouting report.")
@click.option("--event", "event_key", required=True, help="TBA event key.")
@click.option("--team", type=int, default=None, help="Our team number (optional).")
@click.option("--top", "top_n", type=int, default=0, help="Show top-N teams.")
def pre_event_cmd(event_key: str, team: Optional[int], top_n: int) -> None:
    from scout import pre_event_report

    year = int(event_key[:4]) if event_key[:4].isdigit() else 2025
    profiles = pre_event_report.build_profiles(event_key, year=year, our_team=team)
    pre_event_report.display_report(profiles, event_key, our_team=team, top_n=top_n, year=year)
    pre_event_report.save_report(profiles, event_key)


# ---------------------------------------------------------------------------
# engine game-analysis --year N [--output path]
# ---------------------------------------------------------------------------
@cli.command("game-analysis", help="Generate post-season game retrospective.")
@click.option("--year", type=int, required=True, help="FRC season year.")
@click.option("--output", "output", default=None, help="Output path (markdown or pdf).")
@click.option("--md-only", is_flag=True, default=True, help="Write markdown only (default).")
def game_analysis_cmd(year: int, output: Optional[str], md_only: bool) -> None:
    from scout import game_analysis

    out = Path(output) if output else Path(f"reports/game_analysis_{year}.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    report = game_analysis.generate_game_analysis(year)
    md = game_analysis.render_markdown(report)
    out.with_suffix(".md").write_text(md)
    click.echo(f"[game-analysis] Markdown written to {out.with_suffix('.md')}")

    if not md_only and output and output.endswith(".pdf"):
        try:
            game_analysis.render_pdf(report, out)
            click.echo(f"[game-analysis] PDF written to {out}")
        except RuntimeError as exc:
            click.echo(f"[game-analysis] PDF skipped: {exc}", err=True)


# ---------------------------------------------------------------------------
# engine tune-beta --year N
# ---------------------------------------------------------------------------
@cli.command("tune-beta", help="Tune attribution β for a given season.")
@click.option("--year", type=int, required=True, help="FRC season year.")
@click.option("--bootstrap", type=int, default=0, show_default=True, help="Bootstrap resamples (0 = skip CI).")
def tune_beta_cmd(year: int, bootstrap: int) -> None:
    from blueprint import tune_attribution_beta as tab

    # The actual season fetch happens via run_beta_tuning wrapper; we delegate
    # to tune_beta_for_season directly with an empty record set if no data is
    # available so we don't silently hit the network here.
    try:
        fetch = getattr(tab, "fetch_season_matches", None)
        matches: list = []
        if callable(fetch):
            matches = fetch(year) or []
    except Exception as exc:  # pragma: no cover - network-dependent
        click.echo(f"[tune-beta] data fetch failed: {exc}", err=True)
        matches = []

    result = tab.tune_beta_for_season(year, matches, n_bootstrap=bootstrap)
    click.echo(
        f"[tune-beta] year={year} best_beta={result.best_beta} "
        f"n_matches={result.n_matches} status={result.status}"
    )


# ---------------------------------------------------------------------------
# engine status
# ---------------------------------------------------------------------------
@cli.command("status", help="Print repo version + test count + oracle rule count.")
def status_cmd() -> None:
    # Version
    version = __version__

    # Test count — cheap grep rather than running pytest
    test_count = 0
    for p in (ROOT / "tests").rglob("test_*.py"):
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        test_count += len(re.findall(r"^\s*def\s+test_", text, flags=re.MULTILINE))

    # Oracle rule count — count distinct R<id> RuleResult constructions
    rule_count = 0
    oracle_src = ROOT / "blueprint" / "oracle.py"
    if oracle_src.exists():
        text = oracle_src.read_text(errors="ignore")
        ids = set(re.findall(r'RuleResult\(\s*"(R\d+)"', text))
        rule_count = len(ids)

    click.echo(f"engine version : {version}")
    click.echo(f"tests (def test_*) : {test_count}")
    click.echo(f"oracle rules : {rule_count}")


def main() -> None:  # console_script entrypoint
    cli()


if __name__ == "__main__":
    main()
