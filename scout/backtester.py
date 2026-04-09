#!/usr/bin/env python3
"""
The Engine — Historical Backtester
Team 2950 — The Devastators

Tests pick_board.py recommendations against actual alliance selections
at past events. Measures how often the algorithm's #1 pick matches
what the winning alliances actually chose.

Usage:
  # Backtest against all 2026 FIT district events
  python3 backtester.py 2026fit

  # Single event
  python3 backtester.py --event 2026txbel

  # Both years
  python3 backtester.py 2025fit 2026fit
"""

import json
import sys
import time
from pathlib import Path
from dataclasses import dataclass

from statbotics_client import get_event_teams
from tba_client import (
    event_alliances as tba_alliances,
    event_rankings,
    district_events,
)
from pick_board import (
    _parse_team, _blank_state, recommend_pick, predict_captains,
    get_alliances, get_available,
)
from dataclasses import asdict

CACHE_DIR = Path(__file__).parent / ".cache" / "backtest"


@dataclass
class EventResult:
    event_key: str
    event_name: str
    n_teams: int
    # Per alliance: did our rec match actual R1 pick?
    alliance_results: list  # [{seed, captain, actual_r1, rec_r1, rec_rank, match}]
    # Captain prediction accuracy
    captain_pred_correct: int
    captain_pred_total: int


def load_event_data(event_key: str) -> dict:
    """Load EPA + TBA alliance data for an event."""
    raw = get_event_teams(event_key)
    if not raw:
        return None

    teams_db = {}
    for t in raw:
        td = _parse_team(t)
        teams_db[str(td.team)] = asdict(td)

    actual_alliances = tba_alliances(event_key)
    if not actual_alliances:
        return None

    return {
        "teams_db": teams_db,
        "actual_alliances": actual_alliances,
    }


def extract_actual_picks(alliances_data: list) -> list:
    """Extract actual alliance picks from TBA alliance data.
    Returns list of {seed, captain, picks: [team#]}."""
    results = []
    for i, a in enumerate(alliances_data):
        picks = a.get("picks", [])
        if not picks:
            continue
        captain = int(picks[0].replace("frc", ""))
        pick_teams = [int(p.replace("frc", "")) for p in picks[1:]]
        results.append({
            "seed": i + 1,
            "captain": captain,
            "picks": pick_teams,
        })
    return results


def backtest_event(event_key: str, verbose: bool = False) -> EventResult:
    """Run the pick recommendation algorithm for each alliance at an event
    and compare against actual picks."""

    data = load_event_data(event_key)
    if not data:
        return None

    teams_db = data["teams_db"]
    actual = extract_actual_picks(data["actual_alliances"])

    if len(actual) < 8:
        return None

    # Determine captains from actual data
    captains = [a["captain"] for a in actual]

    # Build state as if we were each alliance in turn
    alliance_results = []

    for alliance_data in actual:
        seed = alliance_data["seed"]
        captain = alliance_data["captain"]
        actual_r1 = alliance_data["picks"][0] if alliance_data["picks"] else None

        if not actual_r1:
            continue

        # Build state: set up as this alliance, with all previous picks recorded
        state = _blank_state()
        state["event_key"] = event_key
        state["our_team"] = captain
        state["our_seed"] = seed
        state["captains"] = list(captains)
        state["teams"] = teams_db

        # Record all picks before this alliance's R1 pick
        for prev in actual:
            if prev["seed"] < seed and prev["picks"]:
                state["picks"].append({
                    "alliance": prev["seed"],
                    "team": prev["picks"][0],
                    "round": 1,
                })

        # Get recommendation
        recs = recommend_pick(state)

        rec_r1 = recs[0]["team"] if recs else None
        # Where did the actual pick rank in our recommendations?
        rec_rank = None
        for i, r in enumerate(recs):
            if r["team"] == actual_r1:
                rec_rank = i + 1
                break

        match = (rec_r1 == actual_r1)

        result = {
            "seed": seed,
            "captain": captain,
            "actual_r1": actual_r1,
            "rec_r1": rec_r1,
            "rec_rank": rec_rank,
            "match": match,
        }
        alliance_results.append(result)

        if verbose:
            symbol = "✓" if match else "✗"
            rank_str = f"(ranked #{rec_rank})" if rec_rank else "(not in top 15)"
            actual_td = teams_db.get(str(actual_r1), {})
            rec_td = teams_db.get(str(rec_r1), {})
            print(f"    A{seed}: {symbol} Rec {rec_r1} (EPA {rec_td.get('epa', 0):.1f}) "
                  f"| Actual {actual_r1} (EPA {actual_td.get('epa', 0):.1f}) {rank_str}")

    # Captain prediction accuracy
    state_for_pred = _blank_state()
    state_for_pred["event_key"] = event_key
    state_for_pred["our_team"] = captains[0]
    state_for_pred["our_seed"] = 1
    state_for_pred["captains"] = list(captains)
    state_for_pred["teams"] = teams_db

    try:
        predictions, _ = predict_captains(state_for_pred)
        cap_correct = 0
        cap_total = 0
        for pred in predictions:
            a_seed = pred["alliance"]
            pred_pick = pred["r1_pick"]
            actual_pick = actual[a_seed - 1]["picks"][0] if actual[a_seed - 1]["picks"] else None
            cap_total += 1
            if pred_pick == actual_pick:
                cap_correct += 1
    except Exception:
        cap_correct, cap_total = 0, 0

    return EventResult(
        event_key=event_key,
        event_name=event_key,
        n_teams=len(teams_db),
        alliance_results=alliance_results,
        captain_pred_correct=cap_correct,
        captain_pred_total=cap_total,
    )


def backtest_district(district_key: str, verbose: bool = False):
    """Backtest all events in a district."""
    events = district_events(district_key)
    # Filter to regular district events only
    district_evts = [e for e in events
                     if e.get("event_type", 0) in (0, 1, 2, 5)
                     and "cmp" not in e["key"]]

    print(f"\n  BACKTESTER — {district_key.upper()}")
    print(f"  {len(district_evts)} district events")
    print(f"  {'─' * 70}")

    all_results = []
    total_matches = 0
    total_picks = 0
    total_top3 = 0
    total_top5 = 0
    total_cap_correct = 0
    total_cap_total = 0

    for evt in sorted(district_evts, key=lambda e: e.get("start_date", "")):
        key = evt["key"]
        name = evt.get("short_name", evt.get("name", key))

        print(f"\n  {key} ({name})")

        try:
            result = backtest_event(key, verbose=verbose)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        if not result:
            print(f"    SKIP: No alliance data")
            continue

        time.sleep(0.3)  # Rate limit

        matches = sum(1 for r in result.alliance_results if r["match"])
        picks = len(result.alliance_results)
        top3 = sum(1 for r in result.alliance_results
                   if r["rec_rank"] and r["rec_rank"] <= 3)
        top5 = sum(1 for r in result.alliance_results
                   if r["rec_rank"] and r["rec_rank"] <= 5)

        total_matches += matches
        total_picks += picks
        total_top3 += top3
        total_top5 += top5
        total_cap_correct += result.captain_pred_correct
        total_cap_total += result.captain_pred_total

        exact_pct = matches / picks * 100 if picks else 0
        top3_pct = top3 / picks * 100 if picks else 0
        cap_pct = (result.captain_pred_correct / result.captain_pred_total * 100
                   if result.captain_pred_total else 0)

        print(f"    Exact match: {matches}/{picks} ({exact_pct:.0f}%) | "
              f"Top 3: {top3}/{picks} ({top3_pct:.0f}%) | "
              f"Captain pred: {result.captain_pred_correct}/{result.captain_pred_total} ({cap_pct:.0f}%)")

        all_results.append(result)

    # Summary
    if total_picks > 0:
        print(f"\n  {'═' * 70}")
        print(f"  SUMMARY — {district_key.upper()} ({len(all_results)} events)")
        print(f"  {'─' * 70}")
        print(f"  Exact #1 match:  {total_matches}/{total_picks} "
              f"({total_matches/total_picks*100:.1f}%)")
        print(f"  In top 3:        {total_top3}/{total_picks} "
              f"({total_top3/total_picks*100:.1f}%)")
        print(f"  In top 5:        {total_top5}/{total_picks} "
              f"({total_top5/total_picks*100:.1f}%)")
        if total_cap_total:
            print(f"  Captain predict:  {total_cap_correct}/{total_cap_total} "
                  f"({total_cap_correct/total_cap_total*100:.1f}%)")
        print()

    return all_results


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    args = [a for a in args if a not in ("--verbose", "-v")]

    if not args:
        print(__doc__)
        return

    for arg in args:
        if arg.startswith("--event"):
            continue
        if arg.startswith("20") and "tx" in arg and len(arg) > 8:
            # Single event key
            print(f"\n  BACKTESTER — {arg}")
            print(f"  {'─' * 70}")
            result = backtest_event(arg, verbose=True)
            if result:
                matches = sum(1 for r in result.alliance_results if r["match"])
                picks = len(result.alliance_results)
                top3 = sum(1 for r in result.alliance_results
                           if r["rec_rank"] and r["rec_rank"] <= 3)
                print(f"\n  Exact: {matches}/{picks} | Top 3: {top3}/{picks} | "
                      f"Captain: {result.captain_pred_correct}/{result.captain_pred_total}")
        elif "fit" in arg or "fim" in arg or "fma" in arg:
            backtest_district(arg, verbose=verbose)
        else:
            # Try as event key
            print(f"\n  BACKTESTER — {arg}")
            result = backtest_event(arg, verbose=True)
            if result:
                matches = sum(1 for r in result.alliance_results if r["match"])
                picks = len(result.alliance_results)
                print(f"\n  Exact: {matches}/{picks}")


if __name__ == "__main__":
    main()
