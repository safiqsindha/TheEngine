#!/usr/bin/env python3
"""
The Engine — Live Scout Discord Push (D1)
Team 2950 — The Devastators

Thin wrapper over the Discord webhook API used by every Live Scout
worker that needs to ping humans:

  - Mode A "heads-up" alerts       (workers/mode_a.py)
  - Mode C anomaly alerts          (workers/mode_c_anomaly.py)
  - Mode C event-end digest        (workers/mode_c_event_end.py)

Design goals:
  - **Rate limited.** Discord webhooks 429 aggressively if you post more
    than a couple messages per second on the same webhook URL. We track
    last-post time per webhook URL in a module-level dict and sleep just
    enough to keep a minimum interval between posts.
  - **Idempotent.** Cron ticks retry on failure; we must never
    double-post the same alert. Callers pass a `dedupe_key`; the seen
    set is persisted through the same StateBackend abstraction every
    other Live Scout worker uses (`get_discord_dedupe_backend()`).
  - **Testable.** The actual HTTP call is injectable via `_post_fn`, so
    unit tests never touch the network. The clock is also injectable so
    rate-limit tests don't need `time.sleep()`.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §D1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

# Path bootstrap so we can import the state_backend factory whether the
# module is run as a script or imported as workers.discord_push.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─── Tunables ───

DEFAULT_MIN_INTERVAL_S = 1.5      # Discord webhook rate-limit floor
MAX_DEDUPE_KEYS = 5000            # cap so the seen set doesn't grow forever


# ─── Module-level rate-limit state ───
# Maps webhook URL → last post timestamp (float). In-memory only — cron
# ticks get fresh state per invocation, which is fine because tick
# frequency is lower than the rate limit anyway.
_LAST_POST_AT: dict[str, float] = {}


def _reset_rate_limit_state() -> None:
    """Test helper — drop all in-memory rate limit state."""
    _LAST_POST_AT.clear()


# ─── Dedupe state helpers ───


def _load_seen(backend) -> set[str]:
    data = backend.read() or {}
    seen = data.get("seen", [])
    if isinstance(seen, list):
        return set(seen)
    return set()


def _save_seen(backend, seen: set[str]) -> None:
    # Cap size — keep the most recent MAX_DEDUPE_KEYS entries. We don't
    # track timestamps, so we just truncate arbitrarily on overflow.
    if len(seen) > MAX_DEDUPE_KEYS:
        seen = set(list(seen)[-MAX_DEDUPE_KEYS:])
    backend.write({"seen": sorted(seen)})


# ─── Message formatters ───


def format_heads_up(
    match: Any,
    opponent_team: int,
    breakdown_event: str,
) -> dict[str, Any]:
    """Build the Discord payload for a Mode A heads-up alert.

    `match` is a LiveMatch instance (duck-typed here so this module
    doesn't force a scout/ import at module load).
    """
    match_key = getattr(match, "match_key", "?")
    red = getattr(match, "red_teams", [])
    blue = getattr(match, "blue_teams", [])
    content = (
        f"**Heads-up: {match_key}** — opponent **{opponent_team}** "
        f"detected in {breakdown_event}"
    )
    return {
        "content": content,
        "embeds": [
            {
                "title": f"Live Scout Heads-up — {match_key}",
                "description": (
                    f"Red: {', '.join(str(t) for t in red)}\n"
                    f"Blue: {', '.join(str(t) for t in blue)}\n"
                    f"Opponent: **{opponent_team}**\n"
                    f"Event: {breakdown_event}"
                ),
                "color": 0xFFB300,  # amber
            }
        ],
    }


def format_anomaly(
    team: int,
    event_key: str,
    match_key: str,
    score: int,
    reason: str,
) -> dict[str, Any]:
    """Build the Discord payload for a Mode C anomaly alert."""
    content = (
        f"**Anomaly: {match_key}** — {team} at `{event_key}` hit "
        f"{score} ({reason})"
    )
    return {
        "content": content,
        "embeds": [
            {
                "title": f"Mode C Anomaly — {match_key}",
                "description": (
                    f"Team: **{team}**\n"
                    f"Event: `{event_key}`\n"
                    f"Match: `{match_key}`\n"
                    f"Score: **{score}**\n"
                    f"Reason: {reason}"
                ),
                "color": 0xE53935,  # red
            }
        ],
    }


def format_event_end_digest(
    event_key: str,
    top_three: list[dict[str, Any]],
    match_count: int,
) -> dict[str, Any]:
    """Build the Discord payload for the Mode C event-end digest."""
    lines = []
    for i, team in enumerate(top_three, start=1):
        num = team.get("team", "?")
        avg = team.get("avg_score", 0.0)
        lines.append(f"{i}. **{num}** — avg score {avg:.1f}")
    top_block = "\n".join(lines) if lines else "(no qualifying teams)"

    content = (
        f"**Event digest: `{event_key}`** — {match_count} matches processed"
    )
    return {
        "content": content,
        "embeds": [
            {
                "title": f"Mode C Event End — {event_key}",
                "description": f"**Top 3**\n{top_block}\n\nMatches: {match_count}",
                "color": 0x1E88E5,  # blue
            }
        ],
    }


# ─── Core post() ───


def _default_post_fn(url: str, json_payload: dict[str, Any]) -> Any:
    """Default network call — real requests.post. Imported lazily so the
    test suite runs without `requests` being importable at collection time."""
    import requests  # noqa: WPS433
    return requests.post(url, json=json_payload, timeout=10)


def post(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    dedupe_key: Optional[str] = None,
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    _post_fn: Callable[[str, dict[str, Any]], Any] = _default_post_fn,
    _clock: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], None] = time.sleep,
    _dedupe_backend: Any = None,
) -> bool:
    """Post `payload` to a Discord webhook URL.

    Args:
        webhook_url: Discord webhook URL. Empty string is a no-op (returns
            False) so callers can safely pass `os.environ.get("DISCORD_WEBHOOK_URL")`
            in dev where the env var is unset.
        payload: Discord message body (see format_* helpers).
        dedupe_key: Optional idempotency key. If provided and already in
            the persisted seen-set, returns False without calling the
            network. Only added to the seen-set on successful POST.
        min_interval_s: Minimum seconds between posts to the same webhook
            URL. Default 1.5s to stay under Discord's soft rate limit.
        _post_fn: Injection point for the HTTP call. Tests pass a stub.
        _clock: Injection point for monotonic time (rate-limit tests).
        _sleep: Injection point for sleep (rate-limit tests).
        _dedupe_backend: Injection point for the dedupe StateBackend.
            Default is `get_discord_dedupe_backend()`.

    Returns:
        True if a POST was made AND the response looked successful.
        False on empty URL, dedupe hit, or network failure.
    """
    if not webhook_url:
        return False

    # ─── Dedupe check (before rate limit — avoids needless sleeps) ───
    backend = _dedupe_backend
    seen: Optional[set[str]] = None
    if dedupe_key is not None:
        if backend is None:
            from workers.state_backend import get_discord_dedupe_backend
            backend = get_discord_dedupe_backend()
        seen = _load_seen(backend)
        if dedupe_key in seen:
            return False

    # ─── Rate limit: sleep to keep min interval between posts per URL ───
    now = _clock()
    last = _LAST_POST_AT.get(webhook_url)
    if last is not None:
        gap = now - last
        if gap < min_interval_s:
            _sleep(min_interval_s - gap)
            now = _clock()

    # ─── Fire ───
    try:
        resp = _post_fn(webhook_url, payload)
    except Exception:
        # Network error — don't poison dedupe state.
        return False

    _LAST_POST_AT[webhook_url] = now

    # Accept any 2xx. Duck-type the response so test stubs can return a
    # simple object with `.status_code`.
    status = getattr(resp, "status_code", None)
    if status is None or not (200 <= int(status) < 300):
        return False

    # Successful — commit dedupe key.
    if dedupe_key is not None and seen is not None:
        seen.add(dedupe_key)
        _save_seen(backend, seen)

    return True


# ─── CLI ───


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout Discord push helper")
    parser.add_argument("--test", action="store_true",
                        help="Post a synthetic message to $DISCORD_WEBHOOK_URL")
    parser.add_argument("--kind", default="heads_up",
                        choices=["heads_up", "anomaly", "digest"],
                        help="Which message shape to synthesize in --test mode")
    parser.add_argument("--debug", action="store_true",
                        help="Print the payload instead of posting it")
    args = parser.parse_args(argv)

    if not args.test:
        parser.print_help()
        return 0

    if args.kind == "heads_up":
        class _StubMatch:
            match_key = "2026txbel_qm32"
            red_teams = [2950, 1234, 5678]
            blue_teams = [148, 254, 1678]
        payload = format_heads_up(_StubMatch(), 254, "2026txbel")
    elif args.kind == "anomaly":
        payload = format_anomaly(
            team=254, event_key="2026txdal",
            match_key="2026txdal_qm12", score=218, reason="z-score 3.4",
        )
    else:
        payload = format_event_end_digest(
            event_key="2026txdal",
            top_three=[
                {"team": 254, "avg_score": 145.3},
                {"team": 2056, "avg_score": 138.9},
                {"team": 1678, "avg_score": 132.1},
            ],
            match_count=72,
        )

    if args.debug:
        print(json.dumps(payload, indent=2))
        return 0

    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        print("  DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return 1

    ok = post(url, payload, dedupe_key=f"cli-test:{args.kind}")
    print(f"  posted: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
