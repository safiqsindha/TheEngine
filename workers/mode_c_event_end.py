#!/usr/bin/env python3
"""
The Engine — Live Scout Mode C Event-End Worker (W5)
Team 2950 — The Devastators

Fires once per event, after TBA reports the event as complete. Walks
every qualification match at the event, ensures our `live_matches`
state has an OCR-processed record for each one (reusing the Mode B
pipeline, which is idempotent), then writes a compact digest blob and
pings Discord with top-3 teams + match count.

Phase 1 scope (strict):
  - **OCR only.** No T2 vision (cycle counts / climb / defense), no T3
    Opus synthesis ("alliance brief"). Those are Phase 2. This worker
    stubs the synthesis hook with a TODO; see `_build_alliance_brief_stub`.
  - **Digest is small and boring.** Top 3 by `real_avg_score` from
    pick_board's recomputed aggregates, plus per-team match keys.

Trigger detection ("event status flipped to complete") is out of scope
for Phase 1 — this worker takes `event_key` as input and trusts the
caller (cron job or human) to only launch it on completed events.

Persistence:
  - Digest blob: one JSON per event via `get_digest_backend(event_key)`.
  - Discord dedupe: handled inside `discord_push.post()`.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W5.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scout"))

from workers import discord_push  # noqa: E402


# ─── Result dataclass ───


@dataclass
class ModeCEventEndResult:
    """What run_mode_c_event_end returns."""
    event_key: str
    digest_path: str = ""
    posted: bool = False
    match_count: int = 0
    top_three: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


# ─── Pure logic ───


def _team_played_at_event(
    team_entry: dict[str, Any],
    event_live_match_keys: set[str],
) -> bool:
    """True if any of the team's live_match_keys belong to this event."""
    keys = set(team_entry.get("live_match_keys", []) or [])
    return bool(keys & event_live_match_keys)


def compute_top_three(
    state: dict[str, Any],
    event_key: str,
) -> list[dict[str, Any]]:
    """Return the top 3 teams at `event_key` by `real_avg_score`.

    Pulls from state['teams'] (populated by recompute_team_aggregates)
    and only counts teams who actually played at this event in the
    live_matches dict.

    Ties on avg_score are broken by team number ascending for
    determinism. Teams missing `real_avg_score` are skipped (they
    haven't played ≥3 matches).
    """
    live_matches = state.get("live_matches", {}) or {}
    event_match_keys = {
        mk for mk, m in live_matches.items()
        if m.get("event_key") == event_key
    }

    teams = state.get("teams", {}) or {}
    candidates: list[dict[str, Any]] = []
    for key, entry in teams.items():
        if not _team_played_at_event(entry, event_match_keys):
            continue
        avg = entry.get("real_avg_score")
        if avg is None:
            continue
        try:
            team_num = int(entry.get("team") or key)
        except (TypeError, ValueError):
            continue
        match_keys = sorted(
            mk for mk in (entry.get("live_match_keys") or [])
            if mk in event_match_keys
        )
        candidates.append({
            "team": team_num,
            "avg_score": float(avg),
            "match_count": entry.get("match_count", len(match_keys)),
            "match_keys": match_keys,
        })

    candidates.sort(key=lambda c: (-c["avg_score"], c["team"]))
    return candidates[:3]


def _build_alliance_brief_stub(team: dict[str, Any]) -> dict[str, Any]:
    """Placeholder alliance-brief shape — Phase 2 T3 replaces this.

    Returns a dict with the team's match list and average. The Opus
    synthesis call will slot in here in Phase 2.
    """
    # TODO: T3 synthesis (Phase 2) — call Anthropic Opus advisor with
    # this team's full LiveMatch history and produce a strategic brief.
    return {
        "team": team["team"],
        "avg_score": team["avg_score"],
        "match_keys": team.get("match_keys", []),
        "brief": "",  # Phase 2 will populate this via the Opus advisor.
    }


def build_digest(
    state: dict[str, Any],
    event_key: str,
) -> dict[str, Any]:
    """Construct the digest blob payload for `event_key`."""
    live_matches = state.get("live_matches", {}) or {}
    event_matches = {
        mk: m for mk, m in live_matches.items()
        if m.get("event_key") == event_key
    }
    top = compute_top_three(state, event_key)
    alliance_briefs = [_build_alliance_brief_stub(t) for t in top]

    return {
        "event_key": event_key,
        "match_count": len(event_matches),
        "top_three": top,
        "alliance_briefs": alliance_briefs,
        # TODO: T3 synthesis (Phase 2) — fold Opus advisor output here.
        "phase_2_synthesis": None,
    }


# ─── Default I/O ───


def _default_event_matches(event_key: str) -> list[dict[str, Any]]:
    """Default TBA match fetcher."""
    from tba_client import event_matches
    return event_matches(event_key)


def _default_run_mode_b(**kwargs) -> Any:
    """Default Mode B invocation — wired to workers.mode_b.run_mode_b (W3).

    Lazy import so importing this module does not pull in PaddleOCR or
    the rest of the OCR stack until something actually triggers a
    backfill pass.
    """
    from workers.mode_b import run_mode_b
    return run_mode_b(**kwargs)


# ─── Orchestrator ───


def run_mode_c_event_end(
    *,
    event_key: str,
    state: Optional[dict[str, Any]] = None,
    matches_fetcher: Callable[[str], list[dict[str, Any]]] = _default_event_matches,
    run_mode_b: Callable[..., Any] = _default_run_mode_b,
    post_fn: Callable[..., bool] = discord_push.post,
    webhook_url: Optional[str] = None,
    digest_backend: Any = None,
    persist: bool = True,
) -> ModeCEventEndResult:
    """End-to-end event-end pipeline.

    Args:
        event_key: TBA event key, e.g. "2025txdas".
        state: Pick-board state dict. If None, loaded from
            `get_pick_board_backend()` and written back at the end.
        matches_fetcher: (event_key) -> list[tba_match_dict]. Used only
            for the match count fallback when live_matches is empty.
        run_mode_b: Injectable Mode B runner. Default is a no-op (W3
            doesn't exist yet in Gate 4 order).
        post_fn: Discord push callable.
        webhook_url: Discord webhook URL. Empty string → skip posting.
            None → read DISCORD_WEBHOOK_URL. `--no-discord` passes "".
        digest_backend: Injection point for tests. Default is
            `get_digest_backend(event_key)`.
        persist: If True and state was loaded from the backend, writes
            the updated pick-board back at the end.

    Returns:
        ModeCEventEndResult with the digest path, top-3, and post status.
    """
    result = ModeCEventEndResult(event_key=event_key)

    # ─── Load state ───
    pick_board_backend = None
    if state is None:
        from workers.state_backend import get_pick_board_backend
        pick_board_backend = get_pick_board_backend()
        state = pick_board_backend.read() or {}

    # ─── Ensure live_matches covers every match at this event ───
    try:
        run_mode_b(event_key=event_key, state=state)
    except Exception as e:
        result.error = f"mode_b: {e}"
        return result

    # ─── Build digest ───
    try:
        digest = build_digest(state, event_key)
    except Exception as e:
        result.error = f"digest: {e}"
        return result
    result.match_count = digest["match_count"]
    result.top_three = digest["top_three"]

    # ─── Persist digest ───
    if digest_backend is None:
        from workers.state_backend import get_digest_backend
        digest_backend = get_digest_backend(event_key)
    try:
        digest_backend.write(digest)
    except Exception as e:
        result.error = f"digest_write: {e}"
        return result
    # LocalFileBackend exposes `.path`; AzureBlobBackend does not.
    result.digest_path = str(getattr(digest_backend, "path", digest_backend.name))

    # ─── Discord push ───
    if webhook_url is None:
        import os
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")

    if webhook_url:
        try:
            payload = discord_push.format_event_end_digest(
                event_key=event_key,
                top_three=digest["top_three"],
                match_count=digest["match_count"],
            )
            result.posted = bool(post_fn(
                webhook_url,
                payload,
                dedupe_key=f"event_end:{event_key}",
            ))
        except Exception as e:
            result.error = f"discord: {e}"

    # ─── Persist pick-board ───
    if persist and pick_board_backend is not None:
        try:
            pick_board_backend.write(state)
        except Exception as e:
            result.error = (result.error or "") + f" pick_board_write: {e}"

    return result


# ─── CLI ───


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout Mode C event-end worker")
    parser.add_argument("--event", required=True, help="TBA event key")
    parser.add_argument("--no-discord", action="store_true",
                        help="Skip Discord post (still writes digest)")
    parser.add_argument("--debug", action="store_true",
                        help="Print the digest JSON without persisting")
    args = parser.parse_args(argv)

    webhook = "" if args.no_discord else None

    result = run_mode_c_event_end(
        event_key=args.event,
        webhook_url=webhook,
        persist=not args.debug,
    )

    print(f"  event:        {result.event_key}")
    print(f"  match_count:  {result.match_count}")
    print(f"  top_three:    {[t['team'] for t in result.top_three]}")
    print(f"  digest_path:  {result.digest_path}")
    print(f"  posted:       {result.posted}")
    if result.error:
        print(f"  error:        {result.error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
