#!/usr/bin/env python3
"""
The Engine — Statbotics API Client
Team 2950 — The Devastators

Direct REST client for Statbotics v3 API with local JSON caching.
Does NOT use the statbotics Python package (it's often out of date).

Statbotics API docs: https://api.statbotics.io/v3/
No API key required — public data, reasonable rate limits.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass

try:
    import requests
except ImportError:
    raise ImportError("pip install requests")

BASE_URL = "https://api.statbotics.io/v3"
CACHE_DIR = Path(__file__).parent / ".cache" / "statbotics"
CACHE_TTL_S = 3600  # 1 hour default


@dataclass
class TeamEPA:
    """EPA breakdown for a team in a season."""
    team: int = 0
    year: int = 0
    epa_total: float = 0.0
    epa_auto: float = 0.0
    epa_teleop: float = 0.0
    epa_endgame: float = 0.0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    winrate: float = 0.0
    epa_rank: int = 0
    country_rank: int = 0
    epa_max: float = 0.0       # peak EPA during season
    epa_recent: float = 0.0    # EPA from most recent event
    n_events: int = 0

    @property
    def auto_pct(self) -> float:
        return self.epa_auto / self.epa_total * 100 if self.epa_total else 0

    @property
    def teleop_pct(self) -> float:
        return self.epa_teleop / self.epa_total * 100 if self.epa_total else 0

    @property
    def endgame_pct(self) -> float:
        return self.epa_endgame / self.epa_total * 100 if self.epa_total else 0


@dataclass
class TeamEventEPA:
    """EPA for a specific team at a specific event."""
    team: int = 0
    event: str = ""
    epa_total: float = 0.0
    epa_auto: float = 0.0
    epa_teleop: float = 0.0
    epa_endgame: float = 0.0
    epa_total_start: float = 0.0   # EPA at start of event
    epa_total_end: float = 0.0     # EPA at end of event


# ─── Raw API ───


def _cache_path(endpoint: str) -> Path:
    safe = endpoint.strip("/").replace("/", "_").replace("?", "_").replace("&", "_")
    return CACHE_DIR / f"{safe}.json"


def _get(endpoint: str, ttl: int = CACHE_TTL_S):
    """GET from Statbotics API with local caching."""
    cp = _cache_path(endpoint)
    if cp.exists():
        age = time.time() - cp.stat().st_mtime
        if age < ttl:
            return json.loads(cp.read_text())

    resp = requests.get(f"{BASE_URL}{endpoint}", timeout=15)
    resp.raise_for_status()
    data = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data))
    return data


# ─── Team-Year queries ───


def get_team_year(team: int, year: int) -> TeamEPA:
    """Get a team's season-level EPA breakdown."""
    data = _get(f"/team_year/{team}/{year}")
    record = data.get("record", {})
    epa = data.get("epa", {})

    breakdown = epa.get("breakdown", {})
    stats = epa.get("stats", {})
    ranks = epa.get("ranks", {})

    return TeamEPA(
        team=team,
        year=year,
        epa_total=epa.get("total_points", {}).get("mean", 0) or 0,
        epa_auto=breakdown.get("auto_points", 0) or 0,
        epa_teleop=breakdown.get("teleop_points", 0) or 0,
        epa_endgame=breakdown.get("endgame_points", breakdown.get("barge_points", 0)) or 0,
        wins=record.get("season", {}).get("wins", 0),
        losses=record.get("season", {}).get("losses", 0),
        ties=record.get("season", {}).get("ties", 0),
        winrate=record.get("season", {}).get("winrate", 0) or 0,
        epa_rank=ranks.get("total", {}).get("rank", 0) or 0,
        country_rank=data.get("country_epa_rank", 0) or 0,
        epa_max=stats.get("max", 0) or 0,
    )


def get_team_event(team: int, event_key: str) -> TeamEventEPA:
    """Get a team's EPA at a specific event."""
    data = _get(f"/team_event/{team}/{event_key}")
    return parse_event_team(data)


def get_event_teams(event_key: str) -> list[dict]:
    """Get all team-event EPA data for an event (paginated)."""
    results = []
    offset = 0
    while True:
        data = _get(f"/team_events?event={event_key}&limit=100&offset={offset}")
        if not data:
            break
        results.extend(data)
        if len(data) < 100:
            break
        offset += 100
        time.sleep(0.2)
    return results


def parse_event_team(data: dict) -> TeamEventEPA:
    """Parse a team-event dict from the bulk endpoint."""
    epa = data.get("epa", {})
    breakdown = epa.get("breakdown", {})
    stats = epa.get("stats", {})
    return TeamEventEPA(
        team=data.get("team", 0),
        event=data.get("event", ""),
        epa_total=epa.get("total_points", {}).get("mean", 0) or 0,
        epa_auto=breakdown.get("auto_points", 0) or 0,
        epa_teleop=breakdown.get("teleop_points", 0) or 0,
        epa_endgame=breakdown.get("endgame_points", breakdown.get("barge_points", 0)) or 0,
        epa_total_start=stats.get("start", 0) or 0,
        epa_total_end=stats.get("pre_champs", stats.get("max", 0)) or 0,
    )


# ─── Multi-event trend analysis ───


def get_team_events_in_year(team: int, year: int) -> list[TeamEventEPA]:
    """Get a team's EPA at each event in a season (for trend analysis)."""
    data = _get(f"/team_events?team={team}&year={year}&limit=20")
    if not isinstance(data, list):
        return []
    results = []
    for item in data:
        results.append(parse_event_team(item))
    return results


def epa_trend(events: list[TeamEventEPA]) -> str:
    """Classify EPA trend across events: improving, declining, stable."""
    if len(events) < 2:
        return "insufficient_data"
    epas = [e.epa_total for e in events if e.epa_total > 0]
    if len(epas) < 2:
        return "insufficient_data"
    delta = epas[-1] - epas[0]
    pct = abs(delta) / epas[0] * 100 if epas[0] else 0
    if pct < 10:
        return "stable"
    return "improving" if delta > 0 else "declining"


def epa_drop_pct(events: list[TeamEventEPA]) -> float:
    """% change in EPA from first to last event. Negative = dropped."""
    epas = [e.epa_total for e in events if e.epa_total > 0]
    if len(epas) < 2:
        return 0.0
    return (epas[-1] - epas[0]) / epas[0] * 100 if epas[0] else 0.0


# ─── Cache management ───


def clear_cache():
    """Remove all cached Statbotics responses."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        print(f"Cleared Statbotics cache ({CACHE_DIR})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python statbotics_client.py team <number> <year>")
        print("  python statbotics_client.py event <event_key>")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "team" and len(sys.argv) >= 4:
        team = int(sys.argv[2])
        year = int(sys.argv[3])
        epa = get_team_year(team, year)
        print(f"Team {epa.team} ({epa.year})")
        print(f"  EPA Total:   {epa.epa_total:.1f}")
        print(f"  EPA Auto:    {epa.epa_auto:.1f} ({epa.auto_pct:.0f}%)")
        print(f"  EPA Teleop:  {epa.epa_teleop:.1f} ({epa.teleop_pct:.0f}%)")
        print(f"  EPA Endgame: {epa.epa_endgame:.1f} ({epa.endgame_pct:.0f}%)")
        print(f"  Record: {epa.wins}-{epa.losses}-{epa.ties} ({epa.winrate:.1%})")
        print(f"  Rank: #{epa.epa_rank}")

    elif cmd == "event" and len(sys.argv) >= 3:
        event_key = sys.argv[2]
        print(f"Fetching EPA data for {event_key}...")
        teams = get_event_teams(event_key)
        epas = [parse_event_team(t) for t in teams]
        epas.sort(key=lambda e: e.epa_total, reverse=True)
        print(f"Found {len(epas)} teams:")
        for i, e in enumerate(epas[:20]):
            print(f"  {i+1:3d}. {e.team:5d}  EPA={e.epa_total:6.1f}  "
                  f"(auto={e.epa_auto:.1f} teleop={e.epa_teleop:.1f} end={e.epa_endgame:.1f})")
