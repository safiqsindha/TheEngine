#!/usr/bin/env python3
"""
The Antenna — Live Scout command handlers
Team 2950 — The Devastators

Pure-Python command layer that antenna/bot.py delegates to for every Live
Scout Discord command (!rec, !pick, !board, !undo, !dnp, !alliances, !sim,
!captains, !lookup, !brief, !preview). Each `cmd_*` function returns a
Discord-ready string; it never raises into the bot loop, never calls
discord.py, and never shells out to a subprocess.

Why this module exists
──────────────────────
The original bot.py wired its pick_board commands by shelling out:
`subprocess.run(["python3", "scout/pick_board.py", "rec"], ...)`. That
worked as a quick-and-dirty bridge but had five real problems:

  1. ~300-500 ms Python interpreter startup on every command — bad on a
     competition-day laptop juggling draft picks in a live Discord channel.
  2. No input validation — bad args fail inside the subprocess with a
     cryptic traceback that lands in the Discord channel as "Error: ..."
  3. Stdout parsing — any format change to pick_board's CLI output
     silently breaks the bot.
  4. No error context — exceptions get swallowed before they're useful.
  5. Missing commands — pick_board has undo/alliances/sim/predict/dnp/dp
     that the bot never exposed. Draft day, the operator has to drop to
     a CLI shell to undo a mistyped pick.

This module calls the pick_board Python API directly (load_state,
save_state, recommend_pick, project_board, get_alliances, sim_playoffs,
predict_captains, etc.). One Python process, one state load per command,
deterministic error handling, fully testable, and every pick_board feature
is exposed as a single-function Discord command.

Conventions
───────────
  - Every public function is named `cmd_<verb>` so it mirrors the
    `@bot.command(name="verb")` handler in bot.py one-to-one.
  - Every function returns `str`. The string is what gets sent to
    Discord (the bot handles splitting for the 2000-char limit).
  - Never raise on user-input errors. Return a formatted "Usage: ..."
    or "Error: ..." string instead. Only truly exceptional internal
    failures propagate, and those should be caught by the bot layer.
  - State is always reloaded at the start of each command. Pick boards
    can be updated by a different operator between commands; stale
    in-memory state would be wrong.
  - No global mutable state in this module. Everything flows through
    pick_board's STATE_FILE via load_state/save_state.
  - Tests can monkeypatch `scout.pick_board.STATE_FILE` and
    `scout.pick_board.STATE_DIR` to redirect all I/O into a tmp dir.
"""

from __future__ import annotations

import io
import json
import random
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

# ── Path bootstrap ────────────────────────────────────────────────
# Make scout/ importable regardless of where the bot is launched from.
# Mirrors the pattern antenna/bot.py uses for eye/ and scout/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "scout") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scout"))


# ── Helpers ──────────────────────────────────────────────────────


def _fmt_error(msg: str) -> str:
    """Format an error for Discord. Always code-block wrapped so the
    Discord formatting stays stable and monospace-aligned."""
    return f"```\nError: {msg}\n```"


def _fmt_usage(usage: str) -> str:
    """Format a usage hint. Not an error — the bot distinguishes these
    by caller intent, but the Discord output looks the same."""
    return f"```\nUsage: {usage}\n```"


def _safe_load_state() -> tuple[dict | None, str | None]:
    """Load pick_board state without crashing.

    pick_board.load_state() calls `sys.exit(1)` when the state file is
    missing. That's fine for a CLI but catastrophic for a long-running
    Discord bot. This wrapper returns `(state, error_msg)` where
    exactly one of the two is populated.
    """
    try:
        import pick_board as pb
    except ImportError as e:
        return None, f"pick_board module not importable: {e}"

    if not pb.STATE_FILE.exists():
        return (
            None,
            "No active draft. Run `pick_board.py setup <event> --team N --seed N` "
            "from the command line to initialize the board.",
        )
    try:
        return json.loads(pb.STATE_FILE.read_text()), None
    except (OSError, json.JSONDecodeError) as e:
        return None, f"state file unreadable: {e}"


def _save_state(state: dict) -> str | None:
    """Persist state. Returns None on success, error string on failure."""
    try:
        import pick_board as pb
        pb.STATE_DIR.mkdir(parents=True, exist_ok=True)
        pb.STATE_FILE.write_text(json.dumps(state, indent=2))
        return None
    except OSError as e:
        return f"failed to save state: {e}"


def _team_int(raw: Any) -> int | None:
    """Parse a team number from a Discord argument. Accepts '148',
    '#148', 'frc148' (case-insensitive). Returns None on failure."""
    if raw is None:
        return None
    s = str(raw).strip().lstrip("#").lower()
    if s.startswith("frc"):
        s = s[3:]
    if not s.isdigit():
        return None
    n = int(s)
    if not (1 <= n <= 99999):
        return None
    return n


def _format_rec_top10(picks: list[dict], state: dict, has_eye: bool) -> list[str]:
    """Format the top-10 pick list for Discord. Returns a list of
    monospaced lines ready to join with '\n'."""
    lines = []
    if has_eye:
        lines.append(
            f"{'#':>2} {'Team':>6} {'Name':>16} {'EPA':>6} "
            f"{'Floor':>6} {'Comp':>5} {'QF%':>5} {'EYE':>5} {'Score':>6}"
        )
        lines.append("─" * 62)
    else:
        lines.append(
            f"{'#':>2} {'Team':>6} {'Name':>18} {'EPA':>6} "
            f"{'Floor':>6} {'Comp':>5} {'QF%':>5} {'Score':>6}"
        )
        lines.append("─" * 58)

    for i, p in enumerate(picks[:10], 1):
        mc = f"{p.get('mc_win', 0) * 100:.0f}%" if p.get("mc_win", 0) > 0 else "  —"
        if has_eye:
            eye_s = f"{p.get('eye_score', 0):.0f}" if p.get("eye_conf", 0) > 0 else "  —"
            lines.append(
                f"{i:2d} {p['team']:6d} {p['name'][:16]:>16} {p['epa']:6.1f} "
                f"{p['floor']:6.1f} {p.get('comp_score', 0):5.0f} {mc:>5} "
                f"{eye_s:>5} {p['pick_score']:6.3f}"
            )
        else:
            lines.append(
                f"{i:2d} {p['team']:6d} {p['name'][:18]:>18} {p['epa']:6.1f} "
                f"{p['floor']:6.1f} {p.get('comp_score', 0):5.0f} {mc:>5} "
                f"{p['pick_score']:6.3f}"
            )
    return lines


# ── Commands ─────────────────────────────────────────────────────


def cmd_rec() -> str:
    """Show the current pick recommendation.

    Calls pick_board.recommend_pick(state) directly and formats the
    top 10 for Discord. Works both when it's our turn (headlined
    RECOMMENDATION) and when it's preview mode (other alliance's turn).
    """
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    try:
        picks = pb.recommend_pick(state)
    except Exception as e:  # pick_board bugs shouldn't hang the bot
        return _fmt_error(f"recommend_pick failed: {e}")

    if not picks:
        return _fmt_error(
            "no pick candidates — board may be empty or every team is "
            "taken/DNP. Check `!board` and `!dnp`."
        )

    pos, rd = pb.current_pick_position(state)
    our_seed = state.get("our_seed", 0)
    our_team = state.get("our_team", 0)
    is_our_turn = (rd == 1 and pos == our_seed) or (rd == 2 and pos == our_seed)

    alliances = pb.get_alliances(state)
    our_members = alliances.get(our_seed, [])
    our_epa = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in our_members)
    our_fuel = sum(state["teams"].get(str(t), {}).get("total_fuel", 0) for t in our_members)
    our_tower = sum(state["teams"].get(str(t), {}).get("total_tower", 0) for t in our_members)

    has_eye = any(p.get("eye_score", 0) > 0 for p in picks[:10])

    head = (
        "★ IT'S YOUR TURN (Round {rd})".format(rd=rd)
        if is_our_turn
        else f"Preview — Alliance {pos} picking next (Round {rd})"
    )
    top = picks[0]
    new_epa = our_epa + top["epa"]

    body_lines = [
        "**THE SCOUT — PICK RECOMMENDATION**",
        "```",
        head,
        f"Our alliance: {our_members} "
        f"(EPA {our_epa:.0f} | Fuel {our_fuel:.0f} | Tower {our_tower:.1f})",
        "",
    ]
    body_lines.extend(_format_rec_top10(picks, state, has_eye))
    body_lines.append("")
    body_lines.append(f"★ RECOMMENDATION: pick {top['team']} {top['name']}")
    body_lines.append(
        f"  Alliance EPA: {our_epa:.0f} → {new_epa:.0f} (+{top['epa']:.0f})"
    )
    body_lines.append(f"  Floor: {top['floor']:.1f} | Ceiling: {top['ceiling']:.1f}")
    if top.get("comp_reason"):
        body_lines.append(f"  Why: {top['comp_reason']}")
    if top.get("mc_win", 0) > 0:
        body_lines.append(f"  QF win probability: {top['mc_win']*100:.1f}%")
    body_lines.append("```")
    return "\n".join(body_lines)


def cmd_pick(alliance: str, team: str) -> str:
    """Record a pick: !pick <alliance#> <team#>.

    Validates input BEFORE touching state so bad arguments give a
    clean Usage: line instead of a subprocess traceback.
    """
    if not alliance or not team:
        return _fmt_usage("!pick <alliance#> <team#>  (e.g. !pick 1 148)")

    try:
        alliance_num = int(alliance)
    except (TypeError, ValueError):
        return _fmt_error(f"alliance must be an integer, got {alliance!r}")

    team_num = _team_int(team)
    if team_num is None:
        return _fmt_error(f"invalid team number: {team!r}")

    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    n_cap = len(state.get("captains", []))
    if not (1 <= alliance_num <= n_cap):
        return _fmt_error(
            f"alliance must be 1-{n_cap} (captains loaded in current state)"
        )
    if str(team_num) not in state.get("teams", {}):
        return _fmt_error(f"team {team_num} not found at this event")
    taken = pb.get_taken(state)
    if team_num in taken:
        return _fmt_error(f"team {team_num} already taken")

    rd = pb.current_round(state)

    # Push history for undo BEFORE mutating picks. Matches pick_board's
    # cmd_pick semantics.
    state.setdefault("history", []).append(json.dumps(state.get("picks", [])))
    state.setdefault("picks", []).append(
        {"alliance": alliance_num, "team": team_num, "round": rd}
    )

    save_err = _save_state(state)
    if save_err:
        return _fmt_error(save_err)

    td = state["teams"][str(team_num)]
    pos, new_rd = pb.current_pick_position(state)
    our_seed = state.get("our_seed", 0)
    our_turn_next = (
        (new_rd == 1 and pos == our_seed) or (new_rd == 2 and pos == our_seed)
    )

    lines = [
        "```",
        f"✓ RECORDED: Alliance {alliance_num} picks {team_num} "
        f"{td.get('name', '?')} (EPA {td.get('epa', 0):.1f}) [R{rd}]",
    ]
    if our_turn_next:
        lines.append(
            f"★ IT'S YOUR TURN! Alliance {our_seed} picks next (Round {new_rd})"
        )
        lines.append("Run !rec for recommendation")
    else:
        lines.append(f"Next: Alliance {pos} picks (Round {new_rd})")
    lines.append("```")
    return "\n".join(lines)


def cmd_board() -> str:
    """Show the full pick board — top-20 projected entries + alliances."""
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    try:
        board = pb.project_board(state)
    except Exception as e:
        return _fmt_error(f"project_board failed: {e}")

    pos, rd = pb.current_pick_position(state)
    our_team = state.get("our_team", 0)
    our_seed = state.get("our_seed", 0)
    our_data = state.get("teams", {}).get(str(our_team), {})
    alliances = pb.get_alliances(state)

    lines = [
        "**THE SCOUT — PICK BOARD**",
        "```",
        f"{state.get('event_key', '?')} | Team {our_team} | Alliance {our_seed}",
        f"Round {rd}, Alliance {pos} picking next",
        f"Our EPA: {our_data.get('epa', 0):.1f} | Floor: {our_data.get('floor', 0):.1f}",
        "─" * 72,
        f"{'#':>3} {'Team':>6} {'Name':>20} {'EPA':>7} {'Floor':>7} {'Status':>14}",
        "─" * 72,
    ]
    for entry in board[:20]:
        status = entry.get("status", "")
        marker = ">>" if "YOUR" in status else "  "
        lines.append(
            f"{marker}{entry['pick_order']:3d} {entry['team']:6d} "
            f"{entry['name'][:20]:>20} {entry['epa']:7.1f} {entry['floor']:7.1f} "
            f"{status:>14}"
        )

    lines.append("")
    lines.append("CURRENT ALLIANCES:")
    for a in sorted(alliances.keys()):
        members = alliances[a]
        cap = members[0]
        picks = members[1:]
        epa_total = sum(
            state["teams"].get(str(t), {}).get("epa", 0) for t in members
        )
        tag = " ← US" if a == our_seed else ""
        pick_str = (
            ", ".join(
                f"{t} ({state['teams'].get(str(t), {}).get('epa', 0):.0f})"
                for t in picks
            )
            if picks
            else "—"
        )
        cap_epa = state["teams"].get(str(cap), {}).get("epa", 0)
        lines.append(
            f"A{a}: {cap} ({cap_epa:.0f}) + {pick_str} = {epa_total:.0f}{tag}"
        )
    lines.append("```")
    return "\n".join(lines)


def cmd_undo() -> str:
    """Undo the most recent pick. Reads from state.history."""
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    history = state.get("history", [])
    if not history:
        return "```\nNothing to undo — history is empty.\n```"

    try:
        prev = json.loads(history.pop())
    except (TypeError, ValueError) as e:
        return _fmt_error(f"corrupt history entry: {e}")

    picks = state.get("picks", [])
    removed = picks[-1] if picks else None
    state["picks"] = prev
    state["history"] = history

    save_err = _save_state(state)
    if save_err:
        return _fmt_error(save_err)

    if removed:
        return (
            f"```\n✓ Undid: Alliance {removed['alliance']} "
            f"pick of {removed['team']}\n```"
        )
    return "```\n✓ Undo complete\n```"


def cmd_dnp(team: str = "") -> str:
    """Toggle Do Not Pick for a team. With no arg, shows the DNP list."""
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    dnp = state.setdefault("dnp", [])
    teams_db = state.get("teams", {})

    if not team:
        if not dnp:
            return (
                "```\nNo teams on DNP list.\n"
                "Usage: !dnp <team#>   (toggles on/off)\n```"
            )
        lines = ["```", f"DO NOT PICK LIST ({len(dnp)} teams):"]
        for t in dnp:
            td = teams_db.get(str(t), {})
            name = str(td.get("name", "?"))[:25]
            epa = td.get("epa", 0)
            lines.append(f"  {t:5d}  {name}  (EPA {epa:.1f})")
        lines.append("")
        lines.append("To remove: !dnp <team#>")
        lines.append("```")
        return "\n".join(lines)

    team_num = _team_int(team)
    if team_num is None:
        return _fmt_error(f"invalid team number: {team!r}")
    if str(team_num) not in teams_db:
        return _fmt_error(f"team {team_num} not found at this event")

    td = teams_db[str(team_num)]
    if team_num in dnp:
        dnp.remove(team_num)
        verb = "removed from"
    else:
        dnp.append(team_num)
        verb = "added to"

    state["dnp"] = dnp
    save_err = _save_state(state)
    if save_err:
        return _fmt_error(save_err)

    return (
        f"```\n✓ {team_num} {td.get('name', '?')} {verb} DNP list "
        f"(now {len(dnp)} on list)\n```"
    )


def cmd_alliances() -> str:
    """Show all alliances with EPA totals."""
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    alliances = pb.get_alliances(state)
    our_seed = state.get("our_seed", 0)
    teams_db = state.get("teams", {})

    lines = [
        "**ALLIANCES** — " + state.get("event_key", "?"),
        "```",
    ]
    for a in sorted(alliances.keys()):
        members = alliances[a]
        epa_total = sum(teams_db.get(str(t), {}).get("epa", 0) for t in members)
        sd_sq = sum(teams_db.get(str(t), {}).get("sd", 0) ** 2 for t in members)
        sd_total = sd_sq ** 0.5
        floor_total = epa_total - 1.5 * sd_total
        tag = " ← US" if a == our_seed else ""
        member_str = " + ".join(
            f"{t} ({str(teams_db.get(str(t), {}).get('name', ''))[:12]}, "
            f"{teams_db.get(str(t), {}).get('epa', 0):.0f})"
            for t in members
        )
        lines.append(f"A{a}{tag}:")
        lines.append(f"  {member_str}")
        lines.append(
            f"  EPA {epa_total:.0f} | Floor {floor_total:.0f} | SD {sd_total:.0f}"
        )
        lines.append("")
    lines.append("```")
    return "\n".join(lines)


def cmd_sim(n_sims_raw: str = "5000") -> str:
    """Run a Monte Carlo playoff simulation.

    pick_board.sim_playoffs prints to stdout directly, so we capture
    its output via redirect_stdout. This is the one command where
    parsing the CLI output is acceptable because the data model is
    tightly coupled to the print format and extracting the simulation
    core would be a separate refactor.
    """
    try:
        n_sims = int(n_sims_raw) if n_sims_raw else 5000
    except (TypeError, ValueError):
        return _fmt_error(f"n_sims must be an integer, got {n_sims_raw!r}")
    n_sims = max(100, min(n_sims, 50000))  # bound for sanity

    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    random.seed(42)  # reproducible
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            pb.sim_playoffs(state, n_sims)
    except Exception as e:
        return _fmt_error(f"sim_playoffs failed: {e}")

    out = buf.getvalue().strip()
    if not out:
        return _fmt_error("sim_playoffs returned empty output")
    return f"**PLAYOFF SIM ({n_sims:,} sims)**\n```\n{out}\n```"


def cmd_captains() -> str:
    """Predict which initial captains get picked up by higher seeds
    and who backfills into captain slots.

    pick_board.predict_captains returns a 2-tuple
    `(predictions, final_captains)`. Each `predictions` entry is a
    dict with keys {alliance, captain, r1_pick, pick_type, pick_epa,
    captain_epa}, optionally augmented with declined / decline_reason
    when an invited captain turns down the invite.
    """
    state, err = _safe_load_state()
    if err:
        return _fmt_error(err)

    import pick_board as pb

    try:
        result = pb.predict_captains(state)
    except Exception as e:
        return _fmt_error(f"predict_captains failed: {e}")

    # Support both the current 2-tuple return and a defensive
    # "predictions-only" fallback in case the upstream signature
    # changes out from under us.
    if isinstance(result, tuple) and len(result) == 2:
        predictions, final_captains = result
    else:
        predictions, final_captains = result, []

    teams_db = state.get("teams", {})
    by_rank = sorted(
        teams_db.values(), key=lambda x: x.get("qual_rank", 99)
    )
    initial_captains = [t["team"] for t in by_rank[:8]]

    lines = [
        "**PREDICTED CAPTAIN PICKS**",
        f"_{state.get('event_key', '?')}_",
        "```",
        "R1 predictions (greedy EPA, captain-invite aware):",
    ]
    for p in predictions:
        alliance = p.get("alliance", "?")
        captain = p.get("captain", "?")
        r1_pick = p.get("r1_pick", "?")
        pick_type = p.get("pick_type", "?")
        pick_epa = p.get("pick_epa", 0)
        tag = " ← CAPTAIN PICKED" if pick_type == "captain" else ""
        lines.append(
            f"  A{alliance}: {captain} picks {r1_pick} (EPA {pick_epa:.1f}){tag}"
        )
        if "decline_reason" in p:
            lines.append(f"    ⚠ {p['decline_reason']}")

    if final_captains:
        lines.append("")
        lines.append("Projected final captains after R1:")
        for i, cap in enumerate(final_captains[:8], 1):
            td = teams_db.get(str(cap), {})
            initial = initial_captains[i - 1] if i - 1 < len(initial_captains) else None
            flag = " *" if initial != cap else ""
            name = str(td.get("name", "?"))[:18]
            epa = td.get("epa", 0)
            lines.append(
                f"  A{i}: {cap}{flag} {name} (EPA {epa:.1f})"
            )
        lines.append("")
        lines.append("* = changed from initial qual-rank captain list")
    lines.append("```")
    return "\n".join(lines)


def cmd_lookup(team: str) -> str:
    """Look up a team's current EPA + recent history.

    Network-bound — hits Statbotics. The bot layer wraps this in
    asyncio.to_thread so the event loop doesn't block.
    """
    if not team:
        return _fmt_usage("!lookup <team_number>")
    team_num = _team_int(team)
    if team_num is None:
        return _fmt_error(f"invalid team number: {team!r}")

    try:
        from statbotics_client import (
            epa_trend,
            get_team_events_in_year,
            get_team_year,
        )
    except ImportError as e:
        return _fmt_error(f"statbotics_client not importable: {e}")

    try:
        year = 2025
        epa = get_team_year(team_num, year)
        events = get_team_events_in_year(team_num, year)
        trend = epa_trend(events)
    except Exception as e:
        return _fmt_error(f"statbotics lookup failed: {e}")

    lines = [
        f"**TEAM {team_num}** ({year})",
        "```",
        f"EPA Total:   {epa.epa_total:6.1f}  (rank #{epa.epa_rank})",
        f"EPA Auto:    {epa.epa_auto:6.1f}  ({epa.auto_pct:.0f}%)",
        f"EPA Teleop:  {epa.epa_teleop:6.1f}  ({epa.teleop_pct:.0f}%)",
        f"EPA Endgame: {epa.epa_endgame:6.1f}  ({epa.endgame_pct:.0f}%)",
        f"Record: {epa.wins}-{epa.losses}-{epa.ties} ({epa.winrate:.0%})",
        f"Trend: {trend}",
        f"Events: {len(events)}",
    ]
    if events:
        lines.append("")
        lines.append("EVENT HISTORY:")
        for e in events[:8]:
            lines.append(
                f"  {e.event:14s}  EPA={e.epa_total:6.1f}  "
                f"(a={e.epa_auto:.0f} t={e.epa_teleop:.0f} e={e.epa_endgame:.0f})"
            )
    lines.append("```")
    return "\n".join(lines)


def cmd_brief(event_key: str = "") -> str:
    """Show the most recent synthesis brief for an event.

    Reads from workers/.state/briefs/brief_<event>.json (the shape
    synthesis_worker.write_brief produces). Gracefully handles the
    "Anthropic key not provisioned yet" case.
    """
    if not event_key:
        state, _ = _safe_load_state()
        if state:
            event_key = state.get("event_key", "")
    if not event_key:
        return _fmt_usage("!brief [<event_key>]  (or set via pick_board setup)")

    brief_path = (
        _REPO_ROOT / "workers" / ".state" / "briefs" / f"brief_{event_key}.json"
    )
    if not brief_path.exists():
        return _fmt_error(
            f"no brief yet for {event_key}. "
            "Synthesis worker may not have run, or the Anthropic key "
            "isn't provisioned yet (see GATE_2_HANDOFF §8)."
        )
    try:
        data = json.loads(brief_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return _fmt_error(f"brief file unreadable: {e}")

    if data.get("dry_run"):
        return (
            "```\nLatest brief is a DRY-RUN stub — Anthropic key not "
            "active yet. Run scripts/provision_anthropic_key.sh to "
            "enable real briefs.\n```"
        )

    gen_at = data.get("generated_at", "?")
    our_team = data.get("our_team", "?")
    summary = (data.get("summary") or "").strip()
    top_picks = data.get("top_picks") or []
    model = data.get("model", "?")

    lines = [
        f"**STRATEGIC BRIEF — {event_key}**",
        f"_generated {gen_at} · team {our_team} · model `{model}`_",
        "",
        summary if summary else "_(no summary)_",
    ]
    if top_picks:
        lines.append("")
        lines.append("**Top picks:**")
        for t in top_picks[:8]:
            lines.append(f"  • {t}")
    return "\n".join(lines)


def cmd_preview(team: str) -> str:
    """Show a pre-event excerpt for an opponent team at the current
    event. Wraps scout/pre_event_report.py for a single team."""
    if not team:
        return _fmt_usage("!preview <team_number>")
    team_num = _team_int(team)
    if team_num is None:
        return _fmt_error(f"invalid team number: {team!r}")

    state, err = _safe_load_state()
    event_key = state.get("event_key", "") if state else ""
    if err or not event_key:
        return _fmt_error(
            "no active event. Initialize the pick board first "
            "(`pick_board.py setup <event> --team N --seed N`)"
        )

    try:
        from pre_event_report import build_report_for_team
    except ImportError:
        # Fallback: use the current pick_board state for an EPA snapshot
        td = state.get("teams", {}).get(str(team_num))
        if not td:
            return _fmt_error(f"team {team_num} not in event {event_key}")
        return (
            f"```\nTeam {team_num} {td.get('name', '?')}\n"
            f"EPA: {td.get('epa', 0):.1f} | Floor: {td.get('floor', 0):.1f} "
            f"| Ceiling: {td.get('ceiling', 0):.1f}\n"
            f"Auto {td.get('epa_auto', 0):.1f} | "
            f"Teleop {td.get('epa_teleop', 0):.1f} | "
            f"Endgame {td.get('epa_endgame', 0):.1f}\n"
            f"Qual rank: {td.get('qual_rank', '?')}  ({td.get('qual_record', '?')})\n"
            f"(pre_event_report module not available — showing live "
            f"state snapshot)\n```"
        )

    try:
        report = build_report_for_team(event_key, team_num)
    except Exception as e:
        return _fmt_error(f"pre_event_report failed: {e}")
    if not report:
        return _fmt_error(f"no pre-event report available for team {team_num}")
    return f"**PREVIEW — {team_num}**\n```\n{report[:1800]}\n```"
