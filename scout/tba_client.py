#!/usr/bin/env python3
"""
The Engine — The Blue Alliance API Client
Team 2950 — The Devastators

Thin wrapper around TBA v3 API with local JSON caching.
No external dependencies beyond stdlib + requests.

Env: TBA_API_KEY (get from thebluealliance.com/account)
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError("pip install requests")

BASE_URL = "https://www.thebluealliance.com/api/v3"
CACHE_DIR = Path(__file__).parent / ".cache" / "tba"
CACHE_TTL_S = 3600  # 1 hour default


def _api_key() -> str:
    key = os.environ.get("TBA_API_KEY", "")
    if not key:
        key_file = Path(__file__).parent / ".tba_key"
        if key_file.exists():
            key = key_file.read_text().strip()
    if not key:
        raise RuntimeError(
            "TBA_API_KEY not set. Get one at thebluealliance.com/account "
            "and export TBA_API_KEY=<key> or put it in scout/.tba_key"
        )
    return key


def _cache_path(endpoint: str) -> Path:
    safe = endpoint.strip("/").replace("/", "_")
    return CACHE_DIR / f"{safe}.json"


def _get(endpoint: str, ttl: int = CACHE_TTL_S):
    """GET from TBA with local caching."""
    cp = _cache_path(endpoint)
    if cp.exists():
        age = time.time() - cp.stat().st_mtime
        if age < ttl:
            return json.loads(cp.read_text())

    headers = {"X-TBA-Auth-Key": _api_key()}
    resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data))
    return data


# ─── Event-level queries ───


def event_teams(event_key: str) -> list[dict]:
    """All teams at an event. Returns list of team dicts."""
    return _get(f"/event/{event_key}/teams")


def event_team_keys(event_key: str) -> list[str]:
    """Team keys (e.g. 'frc2950') at an event."""
    return _get(f"/event/{event_key}/teams/keys")


def event_matches(event_key: str) -> list[dict]:
    """All matches at an event."""
    return _get(f"/event/{event_key}/matches")


def event_rankings(event_key: str) -> dict:
    """Qualification rankings at an event."""
    return _get(f"/event/{event_key}/rankings")


def event_oprs(event_key: str) -> dict:
    """OPRs, DPRs, CCWMs for an event."""
    return _get(f"/event/{event_key}/oprs")


def event_alliances(event_key: str) -> list:
    """Alliance selections (the 8 alliances picked during alliance selection).
    Returns list of alliance dicts with picks and status."""
    return _get(f"/event/{event_key}/alliances")


def event_coprs(event_key: str) -> dict:
    """Component OPRs — per-scoring-category OPR breakdown."""
    return _get(f"/event/{event_key}/coprs")


def event_predictions(event_key: str) -> dict:
    """TBA's match predictions for the event."""
    return _get(f"/event/{event_key}/predictions")


def event_playoff_advancement(event_key: str) -> dict:
    """Playoff advancement details."""
    return _get(f"/event/{event_key}/playoff_advancement")


def event_insights(event_key: str) -> dict:
    """Event insights (qual + playoff aggregates)."""
    return _get(f"/event/{event_key}/insights")


def event_district_points(event_key: str) -> dict:
    """District points earned at this event."""
    return _get(f"/event/{event_key}/district_points")


def event_info(event_key: str) -> dict:
    """Event metadata (name, location, dates)."""
    return _get(f"/event/{event_key}")


# ─── Match-level queries ───


def match_detail(match_key: str) -> dict:
    """Full match detail including score_breakdown."""
    return _get(f"/match/{match_key}")


# ─── District queries ───


def district_rankings(district_key: str) -> list:
    """District rankings (e.g. '2026fit' for FIT district)."""
    return _get(f"/district/{district_key}/rankings")


def district_events(district_key: str) -> list:
    """Events in a district."""
    return _get(f"/district/{district_key}/events")


# ─── Team-level queries ───


def team_info(team_key: str) -> dict:
    """Team metadata (name, location, rookie year)."""
    return _get(f"/team/{team_key}")


def team_events(team_key: str, year: int) -> list[dict]:
    """Events a team is attending/attended in a year."""
    return _get(f"/team/{team_key}/events/{year}")


def team_event_matches(team_key: str, event_key: str) -> list[dict]:
    """A team's matches at a specific event."""
    return _get(f"/team/{team_key}/event/{event_key}/matches")


def team_event_status(team_key: str, event_key: str) -> dict:
    """A team's status at an event (rank, record, alliance)."""
    return _get(f"/team/{team_key}/event/{event_key}/status")


# ─── Helpers ───


def team_number(key: str) -> int:
    """Extract team number from 'frc2950' key format."""
    return int(key.replace("frc", ""))


def team_key(number: int) -> str:
    """Convert team number to 'frc2950' key format."""
    return f"frc{number}"


def extract_match_scores(match: dict) -> dict:
    """Extract alliance scores from a match dict."""
    alliances = match.get("alliances", {})
    return {
        "red": alliances.get("red", {}).get("score", 0),
        "blue": alliances.get("blue", {}).get("score", 0),
        "red_teams": alliances.get("red", {}).get("team_keys", []),
        "blue_teams": alliances.get("blue", {}).get("team_keys", []),
        "comp_level": match.get("comp_level", ""),
        "match_number": match.get("match_number", 0),
        "winning_alliance": match.get("winning_alliance", ""),
    }


def team_record_at_event(team_key: str, matches: list[dict]) -> dict:
    """Calculate W-L-T for a team from a match list."""
    wins, losses, ties = 0, 0, 0
    scores = []
    for m in matches:
        if m.get("comp_level") != "qm":
            continue
        alliances = m.get("alliances", {})
        for color in ("red", "blue"):
            if team_key in alliances.get(color, {}).get("team_keys", []):
                score = alliances[color].get("score", 0)
                scores.append(score)
                winner = m.get("winning_alliance", "")
                if winner == color:
                    wins += 1
                elif winner == "":
                    ties += 1
                else:
                    losses += 1
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "scores": scores,
        "avg_score": sum(scores) / len(scores) if scores else 0,
    }


def clear_cache():
    """Remove all cached TBA responses."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        print(f"Cleared TBA cache ({CACHE_DIR})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python tba_client.py <event_key>")
        print("  e.g. python tba_client.py 2025miket")
        sys.exit(0)

    event_key = sys.argv[1]
    print(f"Fetching teams for {event_key}...")
    teams = event_teams(event_key)
    print(f"Found {len(teams)} teams:")
    for t in sorted(teams, key=lambda t: t.get("team_number", 0)):
        print(f"  {t['team_number']:5d}  {t.get('nickname', '')}")
