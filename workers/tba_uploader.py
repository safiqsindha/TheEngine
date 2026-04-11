#!/usr/bin/env python3
"""
The Engine — Live Scout TBA Uploader Worker (Phase 2 U3)
Team 2950 — The Devastators

The TBA uploader is a follow-on worker that publishes match-video links
back to The Blue Alliance. Mode A / Mode B / the backfill worker all
stamp a `source_video_id` on each LiveMatch when they successfully
OCR'd a breakdown screen. This worker walks `state['live_matches']`,
finds records with a `source_video_id` that haven't been uploaded yet,
and POSTs them to TBA Trusted v1.

Pipeline:
  1. Load pick_board state
  2. Filter live_matches → ones with `source_video_id` and no `tba_uploaded`
  3. For each, call `scout.tba_writer.TbaWriter.add_match_video`
  4. On success (including "already exists"), set `tba_uploaded=True`
     on the record so future cron ticks skip it
  5. Save state (only if anything changed)

Idempotency is enforced three ways:
  - The `tba_uploaded` flag on the LiveMatch (set by this worker)
  - TBA's own "already exists" response (if a retry slipped through)
  - The writer treats "already exists" as success, so a duplicate POST
    is cheap and safe

Source-tier rules: this worker doesn't care about source_tier. Mode A's
live feeds and Mode B's VOD backfill both get uploaded. Mode C anomaly
records aren't skipped because they still carry the original video id.

Dry-run mode: set `TBA_UPLOADER_DRY_RUN=true` in the env or pass `--dry-run`.
The worker still iterates state and marks records as "would have uploaded"
in the result, but the writer's dry-run short-circuit prevents any real POST.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md Phase 2 §U3.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ─── Path bootstrap ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scout"))

from tba_writer import TbaWriter, TbaWriteResponse  # noqa: E402


# ─── Result type ───


@dataclass
class TbaUploadResult:
    """Counts from one TBA uploader run, same shape as ModeBResult."""

    processed: list[str] = field(default_factory=list)              # match_keys successfully POSTed
    already_uploaded: list[str] = field(default_factory=list)       # TBA said already_exists
    skipped_already_marked: list[str] = field(default_factory=list) # tba_uploaded already True
    skipped_no_video: list[str] = field(default_factory=list)       # no source_video_id on record
    errors: list[tuple[str, str]] = field(default_factory=list)     # (match_key, message)
    dry_run: bool = False

    @property
    def total_seen(self) -> int:
        return (
            len(self.processed)
            + len(self.already_uploaded)
            + len(self.skipped_already_marked)
            + len(self.skipped_no_video)
            + len(self.errors)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": list(self.processed),
            "already_uploaded": list(self.already_uploaded),
            "skipped_already_marked": list(self.skipped_already_marked),
            "skipped_no_video": list(self.skipped_no_video),
            "errors": list(self.errors),
            "total_seen": self.total_seen,
            "dry_run": bool(self.dry_run),
        }


# ─── Pure logic ───


def _looks_like_real_video_id(video_id: str) -> bool:
    """Filter out the frame-dir provenance strings Mode B writes when
    it reads from a cached frames directory. We only want to push actual
    YouTube video keys to TBA.

    YouTube video keys are 11 chars of [A-Za-z0-9_-]. Frame-dir strings
    contain slashes. Reject anything with a slash or suspicious length.
    """
    if not video_id:
        return False
    if "/" in video_id or "\\" in video_id:
        return False
    # Loose YouTube id check — 11 chars is the canonical length but
    # we don't want to brittle-match here. Reject only obvious non-ids.
    if len(video_id) < 5 or len(video_id) > 32:
        return False
    return True


def find_pending_uploads(
    state: dict[str, Any],
    *,
    event_key: Optional[str] = None,
    only_match_key: Optional[str] = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Return LiveMatch records that need a TBA upload.

    Selection rules mirror vision_worker.find_unprocessed_matches:
      - `only_match_key` is a targeted replay (ignores every other filter)
      - `event_key` restricts by event prefix
      - `force=False` skips records already marked `tba_uploaded=True`
    """
    out: list[dict[str, Any]] = []
    matches = state.get("live_matches") or {}

    for key, record in matches.items():
        if only_match_key is not None:
            if key == only_match_key:
                out.append(record)
            continue
        if event_key is not None and record.get("event_key") != event_key:
            continue
        if not force and record.get("tba_uploaded"):
            continue
        out.append(record)
    return out


def upload_one_match(
    record: dict[str, Any],
    *,
    writer: TbaWriter,
) -> tuple[str, Optional[TbaWriteResponse]]:
    """POST one LiveMatch's video to TBA.

    Returns (status, response) where status is one of:
        "processed"              — TBA accepted the upload (200)
        "already_uploaded"       — TBA said "already exists"
        "skipped_no_video"       — record has no usable source_video_id
        "error:<message>"        — writer returned a non-ok response
    """
    event_key = record.get("event_key")
    match_key = record.get("match_key")
    source_video_id = record.get("source_video_id", "")

    if not event_key or not match_key:
        return "error:missing_keys", None
    if not _looks_like_real_video_id(source_video_id):
        return "skipped_no_video", None

    resp = writer.add_match_video(
        event_key=event_key,
        match_key=match_key,
        video_key=source_video_id,
    )

    if resp.status == "ok":
        return "processed", resp
    if resp.status == "already_exists":
        return "already_uploaded", resp
    return f"error:{resp.status}", resp


# ─── Top-level orchestrator ───


def run_tba_uploader(
    *,
    state: dict[str, Any],
    writer: TbaWriter,
    event_key: Optional[str] = None,
    only_match_key: Optional[str] = None,
    force: bool = False,
) -> TbaUploadResult:
    """End-to-end uploader pass over a pick_board state dict.

    Mutates records in place to set `tba_uploaded=True` on success
    (including "already exists"). The caller is responsible for
    persisting the state dict after this call.
    """
    candidates = find_pending_uploads(
        state,
        event_key=event_key,
        only_match_key=only_match_key,
        force=force,
    )
    candidate_keys = {c.get("match_key") for c in candidates}

    result = TbaUploadResult(dry_run=writer.dry_run)

    matches = state.get("live_matches") or {}
    if only_match_key is None:
        for key, record in matches.items():
            if event_key is not None and record.get("event_key") != event_key:
                continue
            if key in candidate_keys:
                continue
            # Already marked uploaded; skip per census.
            result.skipped_already_marked.append(key)

    for record in candidates:
        match_key = record.get("match_key", "<unknown>")
        try:
            status, resp = upload_one_match(record, writer=writer)
        except Exception as e:
            result.errors.append((match_key, f"orchestrator:{e}"))
            continue

        if status == "processed":
            record["tba_uploaded"] = True
            result.processed.append(match_key)
        elif status == "already_uploaded":
            record["tba_uploaded"] = True
            result.already_uploaded.append(match_key)
        elif status == "skipped_no_video":
            result.skipped_no_video.append(match_key)
        else:
            result.errors.append((match_key, status))

    return result


# ─── CLI ───


def _format_result(event_key: Optional[str], result: TbaUploadResult) -> str:
    label = event_key or "<all events>"
    dry = " [DRY-RUN]" if result.dry_run else ""
    lines = [
        f"  TBA uploader — {label}{dry}",
        f"  {'─' * 60}",
        f"  Total seen             : {result.total_seen}",
        f"  Processed (new)        : {len(result.processed)}",
        f"  Already uploaded       : {len(result.already_uploaded)}",
        f"  Skipped (marked)       : {len(result.skipped_already_marked)}",
        f"  Skipped (no video)     : {len(result.skipped_no_video)}",
        f"  Errors                 : {len(result.errors)}",
    ]
    if result.errors:
        lines.append("")
        lines.append("  Errors:")
        for k, msg in result.errors[:10]:
            lines.append(f"    {k}  {msg}")
    return "\n".join(lines)


def _build_writer_from_env(dry_run: bool) -> TbaWriter:
    auth_id = os.environ.get("TBA_TRUSTED_AUTH_ID", "")
    auth_secret = os.environ.get("TBA_TRUSTED_AUTH_SECRET", "")
    if not auth_id:
        # Dry-run-only construction requires a placeholder auth_id but
        # accepts an empty secret. Fall back to placeholder when totally
        # unconfigured so the worker can still run in staging.
        auth_id = "unconfigured"
        dry_run = True
    return TbaWriter(
        auth_id=auth_id,
        auth_secret=auth_secret,
        dry_run=dry_run or not auth_secret,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout TBA uploader worker (Phase 2 U)")
    parser.add_argument("--event", default=None,
                        help="TBA event key (e.g. 2026txbel). Omit to process all events.")
    parser.add_argument("--match", default=None,
                        help="Specific match_key to upload")
    parser.add_argument("--force", action="store_true",
                        help="Re-upload even if tba_uploaded is already True")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would be uploaded; never POST to TBA")
    parser.add_argument("--debug", action="store_true",
                        help="Print result JSON, don't save pick_board state")
    args = parser.parse_args(argv)

    # Env-driven dry-run guard — Bicep sets TBA_UPLOADER_DRY_RUN=true by default
    env_dry_run = os.environ.get("TBA_UPLOADER_DRY_RUN", "").lower() in {"1", "true", "yes"}
    dry_run = args.dry_run or env_dry_run

    writer = _build_writer_from_env(dry_run)

    from pick_board import load_state
    state = load_state()

    result = run_tba_uploader(
        state=state,
        writer=writer,
        event_key=args.event,
        only_match_key=args.match,
        force=args.force,
    )

    print(_format_result(args.event, result))

    if args.debug:
        return 0

    if result.processed or result.already_uploaded:
        from pick_board import save_state
        save_state(state)
        print(f"\n  Wrote pick_board state with tba_uploaded flags on "
              f"{len(result.processed) + len(result.already_uploaded)} matches")
    else:
        print("\n  No new matches uploaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
