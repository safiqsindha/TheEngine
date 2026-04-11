#!/usr/bin/env python3
"""
The Engine — Live Scout Synthesis Worker (Phase 2 T3)
Team 2950 — The Devastators

Calls Anthropic's Opus once per night to produce a `BriefDocument` —
the end-of-qual-day strategic brief the mentor staff reads before the
next competition day or before alliance selection.

Pipeline:
  1. Load pick_board state (from get_pick_board_backend())
  2. Build a SynthesisInputs (scout/synthesis_prompt.py)
  3. Build the (system, user) prompt pair
  4. Call Anthropic Messages API (lazy-imported)
  5. Parse the response into a BriefDocument
  6. Persist the brief via get_brief_backend(event_key)

Injection points (all for tests):
  - `client`     — anything with a `messages.create(...)` method that
                    returns an object whose `.content[0].text` is the
                    assistant's text. Defaults to `anthropic.Anthropic()`.
  - `state`      — pass a plain dict to bypass pick_board loading.
  - `brief_backend` — pass a LocalFileBackend or mock to bypass the
                    env-driven factory.

Dry-run mode: set `SYNTHESIS_DRY_RUN=true` or pass `--dry-run` to skip
the API call entirely. The worker still builds inputs and the prompt
but writes a placeholder response so Bicep can deploy the cron job
before the Anthropic API key is in Key Vault.

Schema reference: LIVE_SCOUT_PHASE2_REMAINING.md §T3.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ─── Path bootstrap so we can import from sibling top-level packages ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scout"))

from synthesis_prompt import (  # noqa: E402
    SynthesisInputs,
    build_synthesis_prompt,
    collect_synthesis_inputs,
)


DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 2000


# ─── Result types ───


@dataclass
class BriefDocument:
    """One end-of-day strategic brief. Persisted to get_brief_backend()."""

    event_key: str
    generated_at: int                                    # unix epoch
    our_team: int
    model: str                                           # model that produced this brief
    summary: str                                         # the full brief text
    top_picks: list[int] = field(default_factory=list)   # parsed out of the brief if possible
    pick_rationale: dict[str, str] = field(default_factory=dict)  # team -> one-liner
    raw_response: str = ""                               # full text as returned from the API
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key,
            "generated_at": int(self.generated_at),
            "our_team": int(self.our_team),
            "model": self.model,
            "summary": self.summary,
            "top_picks": list(self.top_picks),
            "pick_rationale": {str(k): v for k, v in self.pick_rationale.items()},
            "raw_response": self.raw_response,
            "dry_run": bool(self.dry_run),
        }


@dataclass
class SynthesisWorkerResult:
    """Counts from one synthesis worker run."""

    processed: bool = False
    brief: Optional[BriefDocument] = None
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": bool(self.processed),
            "brief": self.brief.to_dict() if self.brief is not None else None,
            "errors": list(self.errors),
            "dry_run": bool(self.dry_run),
        }


# ─── Anthropic client wiring ───


def _default_anthropic_client():
    """Lazy-import `anthropic` and construct a client from env.

    Returns None if the SDK is not installed OR no API key is set so
    that the synthesis worker can still run in dry-run mode on a box
    that hasn't been provisioned yet.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=api_key)


def call_anthropic(
    system_prompt: str,
    user_prompt: str,
    *,
    client,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Make one Messages API call and return the raw assistant text.

    Caller is responsible for the client (inject a fake in tests). The
    Anthropic SDK returns a `Message` object with `.content` being a list
    of content blocks; we concatenate the `.text` of each text block.
    """
    if client is None:
        raise RuntimeError(
            "call_anthropic requires a non-None client; pass one or "
            "run with dry_run=True to skip the API."
        )
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # `message.content` is a list of typed blocks. Concatenate text blocks.
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts)


# ─── Response parsing ───


_LIST_MARKER_RE = re.compile(r"^(?:\d+[.)\]]\s*|[-*•]\s*)")
_HASH_TEAM_RE = re.compile(r"#(\d{1,5})(?!\d)")
_BARE_TEAM_RE = re.compile(r"(?<!\d)(\d{1,5})(?!\d)")
_TOP_PICKS_HEADER_RE = re.compile(
    r"(?im)^\s*(?:\d+\.\s*)?(?:top\s*picks?|pick\s*order)\b.*$"
)
_WATCH_LIST_HEADER_RE = re.compile(
    r"(?im)^\s*(?:\d+\.\s*)?(?:watch\s*list|upcoming)\b.*$"
)


def parse_brief_response(text: str) -> tuple[list[int], dict[str, str]]:
    """Extract a top-picks list + rationale dict from the brief text.

    Tolerates messy output — Opus may produce bullets, numbered lists,
    or prose. We look for a "Top picks" section header and then scrape
    the first team number out of each non-empty line until we hit a
    blank line or the next section header.

    Never raises. Returns ([], {}) if no top picks could be parsed.
    """
    if not text:
        return [], {}

    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _TOP_PICKS_HEADER_RE.match(line):
            start = i + 1
            break
    if start is None:
        return [], {}

    top_picks: list[int] = []
    rationale: dict[str, str] = {}
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if top_picks:
                break  # stop at the first blank line after we've collected something
            continue
        if _WATCH_LIST_HEADER_RE.match(line):
            break
        # Strip leading list marker ("1. ", "2)", "- ", "• ") so the
        # first captured number is the team, not the list index.
        cleaned = _LIST_MARKER_RE.sub("", stripped)

        # Prefer #NNN form; fall back to a standalone number.
        m = _HASH_TEAM_RE.search(cleaned)
        num = None
        rest_start = 0
        while True:
            if m is None:
                break
            candidate = int(m.group(1))
            if 1 <= candidate <= 99999 and candidate not in top_picks:
                num = candidate
                rest_start = m.end()
                break
            m = _HASH_TEAM_RE.search(cleaned, m.end())

        if num is None:
            m = _BARE_TEAM_RE.search(cleaned)
            while m is not None:
                candidate = int(m.group(1))
                if 1 <= candidate <= 99999 and candidate not in top_picks:
                    num = candidate
                    rest_start = m.end()
                    break
                m = _BARE_TEAM_RE.search(cleaned, m.end())

        if num is None:
            continue
        top_picks.append(num)
        rest = cleaned[rest_start:].lstrip(" -:—–\t")
        if rest:
            rationale[str(num)] = rest

    return top_picks, rationale


# ─── Orchestrator ───


def run_synthesis_worker(
    *,
    event_key: str,
    our_team: int,
    state: Optional[dict[str, Any]] = None,
    brief_backend=None,
    client=None,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    dry_run: bool = False,
    top_n: int = 24,
    recent_n: int = 10,
    now_fn=time.time,
) -> SynthesisWorkerResult:
    """End-to-end synthesis worker pass.

    Loads state, builds the prompt, calls Anthropic (or dry-runs),
    parses the response into a BriefDocument, and persists it.
    """
    result = SynthesisWorkerResult(dry_run=dry_run)

    # 1. State
    if state is None:
        try:
            from workers.state_backend import get_pick_board_backend
            pb = get_pick_board_backend()
            state = pb.read() or {}
        except Exception as e:
            result.errors.append(f"state_load:{e}")
            return result

    # 2. Inputs + prompt
    try:
        inputs = collect_synthesis_inputs(
            state, event_key, our_team,
            top_n=top_n, recent_n=recent_n,
        )
        system, user = build_synthesis_prompt(inputs)
    except Exception as e:
        result.errors.append(f"prompt_build:{e}")
        return result

    # 3. API call (or dry-run)
    if dry_run:
        raw = (
            "DRY_RUN — synthesis worker skipped the Anthropic API call.\n"
            "Top picks\n"
            "  (no live picks in dry-run mode)\n"
        )
        top_picks, rationale = [], {}
    else:
        if client is None:
            client = _default_anthropic_client()
        try:
            raw = call_anthropic(system, user, client=client, model=model)
        except Exception as e:
            result.errors.append(f"anthropic:{e}")
            return result
        top_picks, rationale = parse_brief_response(raw)

    brief = BriefDocument(
        event_key=event_key,
        generated_at=int(now_fn()),
        our_team=int(our_team),
        model=model,
        summary=raw,
        top_picks=top_picks,
        pick_rationale=rationale,
        raw_response=raw,
        dry_run=dry_run,
    )
    result.brief = brief

    # 4. Persist
    if brief_backend is None:
        try:
            from workers.state_backend import get_brief_backend
            brief_backend = get_brief_backend(event_key)
        except Exception as e:
            result.errors.append(f"brief_backend:{e}")
            return result
    try:
        brief_backend.write(brief.to_dict())
    except Exception as e:
        result.errors.append(f"brief_write:{e}")
        return result

    result.processed = True
    return result


# ─── CLI ───


def _format_result(event_key: str, our_team: int, result: SynthesisWorkerResult) -> str:
    dry = " [DRY-RUN]" if result.dry_run else ""
    lines = [
        f"  Synthesis worker — {event_key} / #{our_team}{dry}",
        f"  {'─' * 60}",
        f"  Processed : {result.processed}",
    ]
    if result.brief is not None:
        b = result.brief
        lines.append(f"  Model     : {b.model}")
        lines.append(f"  Top picks : {b.top_picks}")
        lines.append(f"  Summary   : ({len(b.summary)} chars)")
    if result.errors:
        lines.append("")
        lines.append("  Errors:")
        for msg in result.errors[:10]:
            lines.append(f"    {msg}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout synthesis worker (Phase 2 T3)")
    parser.add_argument("--event", required=True, help="TBA event key (e.g. 2026txbel)")
    parser.add_argument("--our-team", type=int, required=True,
                        help="Our team number (used to select upcoming opponent matches)")
    parser.add_argument("--model", default=os.environ.get(
        "SYNTHESIS_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL,
    ))
    parser.add_argument("--top-n", type=int, default=24)
    parser.add_argument("--recent-n", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip the Anthropic API call; still build + persist a brief")
    parser.add_argument("--debug", action="store_true",
                        help="Print the brief JSON to stdout")
    args = parser.parse_args(argv)

    env_dry_run = os.environ.get("SYNTHESIS_DRY_RUN", "").lower() in {"1", "true", "yes"}
    dry_run = args.dry_run or env_dry_run

    result = run_synthesis_worker(
        event_key=args.event,
        our_team=args.our_team,
        model=args.model,
        dry_run=dry_run,
        top_n=args.top_n,
        recent_n=args.recent_n,
    )

    print(_format_result(args.event, args.our_team, result))

    if args.debug and result.brief is not None:
        print()
        print(json.dumps(result.brief.to_dict(), indent=2, sort_keys=True))

    return 0 if result.processed else 1


if __name__ == "__main__":
    sys.exit(main())
