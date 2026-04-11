#!/usr/bin/env python3
"""
The Engine — Live Scout Synthesis Prompt Builder (Phase 2 T3 S1)
Team 2950 — The Devastators

The synthesis worker (workers/synthesis_worker.py) calls Anthropic's
Opus once per night to produce a `BriefDocument` — the "end of qual
day" strategic brief that tells the mentor staff which teams to scout
further, which upcoming opponents to worry about, and what pick order
to consider going into alliance selection.

This module is the *pure* half of that pipeline:
  - `SynthesisInputs`   — everything Opus needs, collected from state
  - `collect_synthesis_inputs(state, event_key, our_team, ...)`
  - `build_synthesis_prompt(inputs) -> (system_prompt, user_prompt)`

Both functions are deterministic, have no network I/O, and take only
plain dicts from `state["teams"]` / `state["live_matches"]`. Tests
construct state fixtures directly instead of hitting pick_board.py.

The output format is a (system, user) pair ready to drop into
`client.messages.create(system=..., messages=[{"role": "user", ...}])`.

Schema reference: LIVE_SCOUT_PHASE2_REMAINING.md §T3 S1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Input aggregation ───


@dataclass
class SynthesisInputs:
    """Everything the synthesis prompt needs, pre-collected from state.

    Built by `collect_synthesis_inputs`; consumed by `build_synthesis_prompt`.
    Keep this dataclass JSON-serializable so tests can diff it cleanly.
    """

    event_key: str
    our_team: int
    top_teams: list[dict]              # top-N by real_avg_score (fallback: epa)
    recent_matches: list[dict]         # last-N LiveMatches by match_num
    next_opponent_matches: list[dict]  # upcoming matches involving our_team
    dnp: list[int] = field(default_factory=list)
    captains: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key,
            "our_team": int(self.our_team),
            "top_teams": list(self.top_teams),
            "recent_matches": list(self.recent_matches),
            "next_opponent_matches": list(self.next_opponent_matches),
            "dnp": list(self.dnp),
            "captains": list(self.captains),
        }


def _team_rank_score(team: dict) -> float:
    """Stable ranking score for top_teams selection.

    Prefers cross-match `real_avg_score` (written by recompute_team_aggregates
    after live matches land). Falls back to the Statbotics EPA when no live
    matches exist yet. Breakers: real_sd desc (lower variance wins).
    """
    ras = team.get("real_avg_score")
    if ras is not None:
        return float(ras)
    return float(team.get("epa", 0.0) or 0.0)


def _rank_key(team: dict) -> tuple[float, float, int]:
    """Tuple sort key — rank score desc, SD asc, team number asc (stable).

    Returns values in "sort ascending wins" form so callers can use
    `sorted(..., key=_rank_key)` with no reverse flag.
    """
    score = _team_rank_score(team)
    sd = float(team.get("real_sd") or team.get("sd") or 0.0)
    # Lower SD is better (less variance), so keep as-is for ascending.
    # But we want HIGHEST score first — negate score so ascending works.
    return (-score, sd, int(team.get("team", 0) or 0))


def _live_match_sort_key(record: dict) -> tuple[int, int]:
    """Sort live matches by (comp_level_rank, match_num)."""
    level = record.get("comp_level", "qm")
    level_rank = {"qm": 0, "qf": 1, "sf": 2, "f": 3}.get(level, 9)
    return (level_rank, int(record.get("match_num", 0) or 0))


def collect_synthesis_inputs(
    state: dict[str, Any],
    event_key: str,
    our_team: int,
    *,
    top_n: int = 24,
    recent_n: int = 10,
) -> SynthesisInputs:
    """Walk state and produce a SynthesisInputs ready for prompt building.

    Args:
        state: pick_board state dict (from load_state()).
        event_key: TBA event key for scoping.
        our_team: Our FRC team number (e.g. 2950). Used to select
            upcoming opponent matches.
        top_n: Cap on top_teams — used to keep prompt size bounded.
        recent_n: Cap on recent_matches.

    Returns:
        SynthesisInputs — all four fields populated. No network I/O.
    """
    teams_db = state.get("teams") or {}
    live_matches = state.get("live_matches") or {}

    # ─── top_teams ───
    # Include every team we have data on; rank by _rank_key; cap to top_n.
    teams_list: list[dict] = []
    for _, td in teams_db.items():
        if not isinstance(td, dict):
            continue
        teams_list.append(dict(td))
    teams_ranked = sorted(teams_list, key=_rank_key)
    top_teams = teams_ranked[: max(0, top_n)]

    # ─── recent_matches ───
    # Filter to the scoped event_key and emit only the non-bulky fields
    # Opus actually needs. Cap to the last `recent_n` by sort key.
    recent: list[dict] = []
    scoped = [
        r for r in live_matches.values()
        if isinstance(r, dict) and r.get("event_key") == event_key
    ]
    scoped.sort(key=_live_match_sort_key)
    for r in scoped[-max(0, recent_n):]:
        recent.append({
            "match_key": r.get("match_key", ""),
            "comp_level": r.get("comp_level", ""),
            "match_num": int(r.get("match_num", 0) or 0),
            "red_teams": list(r.get("red_teams") or []),
            "blue_teams": list(r.get("blue_teams") or []),
            "red_score": r.get("red_score"),
            "blue_score": r.get("blue_score"),
            "winning_alliance": r.get("winning_alliance"),
        })

    # ─── next_opponent_matches ───
    # Any match in state that lists our_team on either alliance AND that
    # has no score yet (both scores None). Sorted by match_num so Opus
    # reads them in chronological order.
    upcoming: list[dict] = []
    for r in scoped:
        if r.get("red_score") is not None or r.get("blue_score") is not None:
            continue
        red = r.get("red_teams") or []
        blue = r.get("blue_teams") or []
        if our_team not in red and our_team not in blue:
            continue
        our_alliance = "red" if our_team in red else "blue"
        opponents = list(blue if our_alliance == "red" else red)
        partners = [t for t in (red if our_alliance == "red" else blue) if t != our_team]
        upcoming.append({
            "match_key": r.get("match_key", ""),
            "match_num": int(r.get("match_num", 0) or 0),
            "our_alliance": our_alliance,
            "partners": partners,
            "opponents": opponents,
        })
    upcoming.sort(key=lambda m: m.get("match_num", 0))

    return SynthesisInputs(
        event_key=event_key,
        our_team=int(our_team),
        top_teams=top_teams,
        recent_matches=recent,
        next_opponent_matches=upcoming,
        dnp=list(state.get("dnp") or []),
        captains=list(state.get("captains") or []),
    )


# ─── Prompt assembly ───


_SYSTEM_PROMPT = """\
You are the strategic scout for FRC Team 2950 — The Devastators.
You are analyzing live scouting data from an ongoing FRC competition.
Your job is to produce a concise end-of-day strategic brief that the
team's drive coach, scouting lead, and mentor staff will read before
the next day's matches (or before alliance selection).

Write in crisp, actionable prose. Avoid generic praise. Cite teams by
number. When you recommend a pick order or a defensive matchup, tie it
to specific data points from the inputs (e.g., real_avg_score,
streak = HOT/COLD, recent match scores, upcoming opponent quality).

Required sections in your brief, in this order:

  1. Headline (one sentence): the single most important thing to know.
  2. Top picks (ranked): 5-8 teams sorted by who we should pick first
     if we are a captain. For each team give a one-sentence rationale.
  3. Watch list: 3-5 teams who might be underrated or trending up/down
     since the last brief.
  4. Upcoming matches: our team's upcoming matches with a short take on
     each opponent alliance's threat level and what we should do.
  5. Risks: any anomalies, injuries, defensive specialists, or pick-board
     blowups we should brace for.

Keep the whole brief under ~400 words. Output plain text, not markdown
headers. Separate sections with blank lines.
"""


def _format_team_line(team: dict) -> str:
    """One-line summary of a team for the user prompt."""
    number = team.get("team", "?")
    name = team.get("name", "")
    ras = team.get("real_avg_score")
    epa = team.get("epa", 0.0) or 0.0
    sd = team.get("real_sd") or team.get("sd", 0.0) or 0.0
    streak = team.get("streak", "") or ""
    rank = team.get("qual_rank", "?")
    record = team.get("qual_record", "")
    score_part = f"live={ras:.1f}" if ras is not None else f"epa={epa:.1f}"
    parts = [
        f"#{number}",
        f"({name})" if name else "",
        f"rank={rank}",
        record,
        score_part,
        f"sd={float(sd):.1f}",
    ]
    if streak:
        parts.append(f"[{streak}]")
    return " ".join(p for p in parts if p)


def _format_match_line(match: dict) -> str:
    red = "/".join(str(t) for t in match.get("red_teams", []))
    blue = "/".join(str(t) for t in match.get("blue_teams", []))
    rs = match.get("red_score")
    bs = match.get("blue_score")
    if rs is None or bs is None:
        scoreline = "(pending)"
    else:
        scoreline = f"{rs}-{bs} {match.get('winning_alliance', 'tie') or 'tie'}"
    return f"  {match.get('match_key', '?')}: RED[{red}] vs BLUE[{blue}] → {scoreline}"


def _format_upcoming_line(match: dict) -> str:
    partners = "/".join(str(t) for t in match.get("partners", []))
    opponents = "/".join(str(t) for t in match.get("opponents", []))
    return (
        f"  {match.get('match_key', '?')} [{match.get('our_alliance', '?')}]"
        f"  partners: {partners}  vs opponents: {opponents}"
    )


def build_synthesis_prompt(inputs: SynthesisInputs) -> tuple[str, str]:
    """Produce (system_prompt, user_prompt) ready for Anthropic.

    The system prompt is a constant — see `_SYSTEM_PROMPT`. The user
    prompt is a plaintext dump of `inputs` laid out in a human- and
    LLM-friendly way. We deliberately avoid JSON for the top-level so
    Opus doesn't waste tokens reformatting; nested arrays stay as short
    lists.
    """
    lines: list[str] = []
    lines.append(f"EVENT: {inputs.event_key}")
    lines.append(f"OUR TEAM: {inputs.our_team}")
    if inputs.captains:
        lines.append("CAPTAINS (current): " + ", ".join(str(c) for c in inputs.captains))
    if inputs.dnp:
        lines.append("DO NOT PICK: " + ", ".join(str(t) for t in inputs.dnp))
    lines.append("")

    lines.append(f"TOP {len(inputs.top_teams)} TEAMS (ranked):")
    if inputs.top_teams:
        for t in inputs.top_teams:
            lines.append(f"  {_format_team_line(t)}")
    else:
        lines.append("  (no team data yet)")
    lines.append("")

    lines.append(f"RECENT {len(inputs.recent_matches)} MATCHES:")
    if inputs.recent_matches:
        for m in inputs.recent_matches:
            lines.append(_format_match_line(m))
    else:
        lines.append("  (no live matches yet)")
    lines.append("")

    lines.append(f"UPCOMING MATCHES FOR #{inputs.our_team}:")
    if inputs.next_opponent_matches:
        for m in inputs.next_opponent_matches:
            lines.append(_format_upcoming_line(m))
    else:
        lines.append("  (none scheduled in state)")
    lines.append("")

    lines.append(
        "Produce the end-of-day brief described in the system prompt. "
        "Every recommendation must cite a team number and a data point "
        "from the tables above."
    )

    user_prompt = "\n".join(lines)
    return _SYSTEM_PROMPT, user_prompt


# ─── Debug helper ───


def dump_inputs_json(inputs: SynthesisInputs) -> str:
    """Pretty-printed JSON dump — useful for CLI --debug and test fixtures."""
    return json.dumps(inputs.to_dict(), indent=2, sort_keys=True)
