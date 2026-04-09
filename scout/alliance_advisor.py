#!/usr/bin/env python3
"""
The Engine — Alliance Selection Advisor
Team 2950 — The Devastators

Combines EPA data + complementarity analysis + Monte Carlo simulation
to produce a ranked pick list for alliance selection.

Usage:
  python3 alliance_advisor.py <event_key> --team 2950
  python3 alliance_advisor.py <event_key> --team 2950 --sims 2000
  python3 alliance_advisor.py <event_key> --team 2950 --json
"""

import json
import math
import random
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from statbotics_client import get_event_teams, parse_event_team, TeamEventEPA

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# COMPLEMENTARITY SCORING
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PickCandidate:
    """A candidate for alliance selection."""
    team: int = 0
    name: str = ""
    epa_total: float = 0.0
    epa_auto: float = 0.0
    epa_teleop: float = 0.0
    epa_endgame: float = 0.0
    epa_sd: float = 0.0     # scoring standard deviation (consistency)

    # Complementarity
    complementarity_score: float = 0.0
    complementarity_reasoning: str = ""

    # Monte Carlo
    sim_win_rate: float = 0.0
    sim_avg_margin: float = 0.0

    # Combined
    pick_score: float = 0.0
    pick_rank: int = 0


def complementarity(us: TeamEventEPA, them: TeamEventEPA,
                    event_avg: float) -> tuple[float, str]:
    """
    Score how well a candidate complements our team.

    Key insight: a partner strong where we're weak is better than a
    partner strong where we're already strong (diminishing returns).

    Returns (score 0-100, reasoning string).
    """
    if event_avg <= 0:
        event_avg = 1.0

    reasons = []
    score = 0.0

    # Normalize EPAs to event average
    us_auto_pct = us.epa_auto / event_avg if event_avg else 0
    us_teleop_pct = us.epa_teleop / event_avg if event_avg else 0
    us_endgame_pct = us.epa_endgame / event_avg if event_avg else 0

    them_auto_pct = them.epa_auto / event_avg if event_avg else 0
    them_teleop_pct = them.epa_teleop / event_avg if event_avg else 0
    them_endgame_pct = them.epa_endgame / event_avg if event_avg else 0

    # Auto complementarity: bonus if they're strong where we're weak
    auto_gap = max(0, them_auto_pct - us_auto_pct)
    auto_score = min(30, auto_gap * 30)
    score += auto_score
    if them.epa_auto > us.epa_auto * 1.3:
        reasons.append(f"Strong auto ({them.epa_auto:.1f}) covers our gap ({us.epa_auto:.1f})")

    # Teleop complementarity
    teleop_gap = max(0, them_teleop_pct - us_teleop_pct)
    teleop_score = min(35, teleop_gap * 25)
    score += teleop_score
    if them.epa_teleop > us.epa_teleop * 1.2:
        reasons.append(f"Strong teleop ({them.epa_teleop:.1f}) boosts alliance scoring")

    # Endgame reliability bonus: both teams having endgame is valuable
    if them.epa_endgame > 3 and us.epa_endgame > 0:
        endgame_bonus = min(20, them.epa_endgame * 2)
        score += endgame_bonus
        reasons.append(f"Reliable endgame ({them.epa_endgame:.1f})")
    elif them.epa_endgame > 5 and us.epa_endgame <= 0:
        endgame_bonus = min(25, them.epa_endgame * 2.5)
        score += endgame_bonus
        reasons.append(f"Endgame ({them.epa_endgame:.1f}) covers our weakness")

    # Raw EPA floor: don't pick a "complementary" team that's actually bad
    raw_bonus = min(15, them.epa_total / event_avg * 10)
    score += raw_bonus

    # Cap at 100
    score = min(100, score)

    reasoning = "; ".join(reasons) if reasons else "Average complementarity"
    return round(score, 1), reasoning


# ═══════════════════════════════════════════════════════════════════
# MONTE CARLO MATCH SIMULATION
# ═══════════════════════════════════════════════════════════════════

def simulate_match(alliance_epas: list[float], alliance_sds: list[float],
                   opponent_epas: list[float], opponent_sds: list[float]) -> bool:
    """Simulate one match. Returns True if alliance wins."""
    alliance_score = sum(
        max(0, random.gauss(epa, sd))
        for epa, sd in zip(alliance_epas, alliance_sds)
    )
    opponent_score = sum(
        max(0, random.gauss(epa, sd))
        for epa, sd in zip(opponent_epas, opponent_sds)
    )
    return alliance_score > opponent_score


def simulate_playoff(our_alliance: list[TeamEventEPA],
                     opponent_pool: list[TeamEventEPA],
                     n_sims: int = 1000) -> tuple[float, float]:
    """
    Simulate a playoff bracket.

    For simplicity, we simulate best-of-3 matches against the average
    of the top 8 opponents (representing a typical playoff opponent).

    Returns (win_rate, avg_margin).
    """
    # Our alliance EPAs and SDs
    a_epas = [t.epa_total for t in our_alliance]
    # Use ~30% of EPA as a rough standard deviation
    a_sds = [max(3, t.epa_total * 0.25) for t in our_alliance]

    # Average top-8 opponent alliance (3 teams)
    top_opponents = sorted(opponent_pool, key=lambda t: t.epa_total, reverse=True)[:8]
    if not top_opponents:
        return 0.5, 0.0

    # Pick 3 random opponents per sim from the top 8
    wins = 0
    margins = []

    for _ in range(n_sims):
        opp = random.sample(top_opponents, min(3, len(top_opponents)))
        o_epas = [t.epa_total for t in opp]
        o_sds = [max(3, t.epa_total * 0.25) for t in opp]

        # Best of 3
        match_wins = 0
        match_margin = 0
        for _ in range(3):
            a_score = sum(max(0, random.gauss(e, s)) for e, s in zip(a_epas, a_sds))
            o_score = sum(max(0, random.gauss(e, s)) for e, s in zip(o_epas, o_sds))
            match_margin += a_score - o_score
            if a_score > o_score:
                match_wins += 1

        if match_wins >= 2:
            wins += 1
        margins.append(match_margin / 3)

    win_rate = wins / n_sims
    avg_margin = sum(margins) / len(margins)
    return win_rate, avg_margin


# ═══════════════════════════════════════════════════════════════════
# ADVISOR
# ═══════════════════════════════════════════════════════════════════

def rank_picks(event_key: str, our_team: int,
               n_sims: int = 1000) -> list[PickCandidate]:
    """Generate ranked pick list for alliance selection."""
    print(f"  Fetching EPA data for {event_key}...")
    raw_teams = get_event_teams(event_key)
    if not raw_teams:
        print(f"  No data for {event_key}")
        return []

    all_epas = [parse_event_team(t) for t in raw_teams]
    epa_values = [e.epa_total for e in all_epas if e.epa_total > 0]
    event_avg = sum(epa_values) / len(epa_values) if epa_values else 1

    # Find our team
    us = None
    for e in all_epas:
        if e.team == our_team:
            us = e
            break
    if not us:
        print(f"  Team {our_team} not found at {event_key}")
        return []

    print(f"  Our EPA: {us.epa_total:.1f} (auto={us.epa_auto:.1f} teleop={us.epa_teleop:.1f} end={us.epa_endgame:.1f})")
    print(f"  Event avg: {event_avg:.1f}, {len(all_epas)} teams")

    # Score every other team
    candidates = []
    for team_epa in all_epas:
        if team_epa.team == our_team or team_epa.team == 0:
            continue

        c = PickCandidate(
            team=team_epa.team,
            name=next((t.get("team_name", "") for t in raw_teams
                       if t.get("team") == team_epa.team), ""),
            epa_total=team_epa.epa_total,
            epa_auto=team_epa.epa_auto,
            epa_teleop=team_epa.epa_teleop,
            epa_endgame=team_epa.epa_endgame,
        )

        # Complementarity score
        c.complementarity_score, c.complementarity_reasoning = complementarity(
            us, team_epa, event_avg
        )

        candidates.append(c)

    # Monte Carlo simulation for top candidates
    candidates.sort(key=lambda c: c.epa_total, reverse=True)
    sim_pool = candidates[:20]  # Only simulate top 20 by raw EPA

    print(f"\n  Running Monte Carlo simulation ({n_sims} sims per candidate)...")
    opponent_pool = [e for e in all_epas if e.team != our_team]

    for c in sim_pool:
        # Create alliance: us + candidate + a placeholder average 3rd pick
        avg_3rd = TeamEventEPA(
            epa_total=event_avg * 0.8,
            epa_auto=event_avg * 0.2,
            epa_teleop=event_avg * 0.5,
            epa_endgame=event_avg * 0.1,
        )
        partner = next((e for e in all_epas if e.team == c.team), avg_3rd)
        alliance = [us, partner, avg_3rd]

        # Remove our alliance from opponent pool
        opp_pool = [e for e in opponent_pool if e.team != c.team]
        c.sim_win_rate, c.sim_avg_margin = simulate_playoff(
            alliance, opp_pool, n_sims
        )

    # Combined pick score: weighted mix of EPA, complementarity, and simulated win rate
    for c in candidates:
        epa_norm = c.epa_total / event_avg if event_avg else 0
        comp_norm = c.complementarity_score / 100.0
        sim_norm = c.sim_win_rate  # already 0-1

        # Weights: EPA matters most but complementarity breaks ties
        c.pick_score = (epa_norm * 0.45 + comp_norm * 0.25 + sim_norm * 0.30) * 100

    # Final ranking by combined score
    candidates.sort(key=lambda c: c.pick_score, reverse=True)
    for rank, c in enumerate(candidates, 1):
        c.pick_rank = rank

    return candidates


def display_picks(candidates: list[PickCandidate], our_team: int,
                  event_key: str, top_n: int = 15):
    """Display the ranked pick list."""
    if not candidates:
        print("No candidates to display.")
        return

    print(f"\n{'═' * 70}")
    print(f"  THE SCOUT — ALLIANCE SELECTION ADVISOR")
    print(f"  Event: {event_key}  |  Our team: {our_team}")
    print(f"{'═' * 70}")

    show = candidates[:top_n]
    print(f"\n  TOP {len(show)} PICKS (combined EPA + complementarity + sim win rate)")
    print(f"  {'─' * 65}")

    for c in show:
        sim_str = f"win={c.sim_win_rate:.0%}" if c.sim_win_rate > 0 else "no sim"
        print(f"\n  #{c.pick_rank:2d} TEAM {c.team:5d} {c.name}")
        print(f"      EPA: {c.epa_total:5.1f}  (auto={c.epa_auto:.1f}  teleop={c.epa_teleop:.1f}  end={c.epa_endgame:.1f})")
        print(f"      Complementarity: {c.complementarity_score:.0f}/100 — {c.complementarity_reasoning}")
        print(f"      Sim: {sim_str}, avg margin {c.sim_avg_margin:+.1f}")
        print(f"      PICK SCORE: {c.pick_score:.1f}")

    # Quick comparison: raw EPA rank vs pick rank (show value of complementarity)
    by_epa = sorted(candidates, key=lambda c: c.epa_total, reverse=True)
    reranked = []
    for c in show:
        epa_rank = next(i for i, x in enumerate(by_epa, 1) if x.team == c.team)
        if epa_rank != c.pick_rank:
            reranked.append((c, epa_rank))

    if reranked:
        print(f"\n  {'─' * 65}")
        print(f"  COMPLEMENTARITY IMPACT (teams re-ranked vs pure EPA):")
        for c, epa_rank in reranked[:8]:
            direction = "↑" if c.pick_rank < epa_rank else "↓"
            diff = abs(epa_rank - c.pick_rank)
            print(f"    {c.team:5d}: EPA #{epa_rank} → Pick #{c.pick_rank} ({direction}{diff})")

    print(f"\n{'═' * 70}\n")


def save_picks(candidates: list[PickCandidate], event_key: str, our_team: int):
    """Save pick list as JSON."""
    out = BASE_DIR / f"picks_{event_key}_{our_team}.json"
    with open(out, "w") as f:
        json.dump({
            "event": event_key,
            "our_team": our_team,
            "picks": [asdict(c) for c in candidates],
        }, f, indent=2)
    print(f"  Pick list saved: {out}")
    return out


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("The Scout — Alliance Selection Advisor")
        print()
        print("Usage:")
        print("  python3 alliance_advisor.py <event_key> --team <number>")
        print("  python3 alliance_advisor.py <event_key> --team 2950 --sims 2000")
        print("  python3 alliance_advisor.py <event_key> --team 2950 --top 20")
        return

    event_key = sys.argv[1]
    our_team = None
    n_sims = 1000
    top_n = 15
    json_output = False

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1])
            i += 2
        elif args[i] == "--sims" and i + 1 < len(args):
            n_sims = int(args[i + 1])
            i += 2
        elif args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        else:
            i += 1

    if not our_team:
        print("Error: --team is required")
        return

    candidates = rank_picks(event_key, our_team, n_sims=n_sims)

    if json_output:
        save_picks(candidates, event_key, our_team)
    else:
        display_picks(candidates, our_team, event_key, top_n=top_n)
        save_picks(candidates, event_key, our_team)


if __name__ == "__main__":
    main()
