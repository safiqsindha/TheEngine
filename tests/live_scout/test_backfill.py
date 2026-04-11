"""Tests for workers/backfill.py — W6 / Gate 5 backfill worker.

All tests are hermetic: no network, no real TBA, no real mode_b, no
PaddleOCR, no Azure SDK. The `events_fetcher` and `mode_b_runner`
callables are injected as stubs; the state backend factory is
redirected to a tmp_path so writes land under a sandbox directory.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.backfill import (  # noqa: E402
    BackfillResult,
    _format_summary_table,
    is_fit_event,
    run_backfill,
)
from workers.state_backend import (  # noqa: E402
    LocalFileBackend,
    get_backfill_backend,
)


# ─── Fixtures / fakes ───


@dataclass
class FakeModeBResult:
    """Mirrors the shape of the real ModeBResult (forward-compat)."""
    event_key: str
    matches_processed: int = 0
    matches_skipped: int = 0


def _fit_event(key: str, *, name: str = "", code: str = "") -> dict[str, Any]:
    """TBA-shape event dict for a FIT event (district metadata set)."""
    return {
        "key": key,
        "name": name or f"Event {key}",
        "event_code": code or key.replace("2025", "").replace("2026", ""),
        "district": {"abbreviation": "fit", "key": f"{key[:4]}fit"},
    }


def _non_fit_event(key: str, district_abbr: str = "ne") -> dict[str, Any]:
    return {
        "key": key,
        "name": f"Event {key}",
        "event_code": key,
        "district": {"abbreviation": district_abbr, "key": f"{key[:4]}{district_abbr}"},
    }


def _backfill_factory(root: Path):
    """Build a state_factory override that writes under a tmp root."""
    def factory(*, event_key: str, season: int) -> LocalFileBackend:
        local_path = root / str(season) / f"{event_key}.json"
        return LocalFileBackend(local_path)
    return factory


# ─── is_fit_event ───


def test_is_fit_event_via_district_abbreviation():
    assert is_fit_event({"district": {"abbreviation": "fit", "key": "2025fit"}})


def test_is_fit_event_via_district_key():
    assert is_fit_event({"district": {"abbreviation": "", "key": "2025fit"}})


def test_is_fit_event_rejects_non_fit_district():
    assert not is_fit_event({"district": {"abbreviation": "ne", "key": "2025ne"}})


def test_is_fit_event_fallback_substring_on_name():
    assert is_fit_event({"name": "FIT District Belton Event", "district": None})


def test_is_fit_event_rejects_unrelated_event():
    assert not is_fit_event({"key": "2025mndu", "name": "Duluth", "district": None})


# ─── Event filtering through run_backfill ───


def test_run_backfill_filters_non_fit_events(tmp_path):
    """Mix FIT + non-FIT events; only FIT events should be processed."""
    events = [
        _fit_event("2025txbel"),
        _non_fit_event("2025mndu"),
        _fit_event("2025txdri"),
        _non_fit_event("2025casj", district_abbr="chs"),
    ]
    calls: list[str] = []

    def stub_mode_b(**kwargs):
        calls.append(kwargs["event_key"])
        return FakeModeBResult(event_key=kwargs["event_key"], matches_processed=5)

    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    assert sorted(calls) == ["2025txbel", "2025txdri"]
    assert result.events_total == 2
    assert sorted(result.events_succeeded) == ["2025txbel", "2025txdri"]
    assert result.events_failed == []
    assert result.matches_processed == 10


def test_run_backfill_respects_only_events_filter(tmp_path):
    events = [
        _fit_event("2025txbel"),
        _fit_event("2025txdri"),
        _fit_event("2025txdal"),
        _fit_event("2025txhou"),
        _fit_event("2025txaus"),
    ]
    calls: list[str] = []

    def stub_mode_b(**kwargs):
        calls.append(kwargs["event_key"])
        return FakeModeBResult(event_key=kwargs["event_key"], matches_processed=1)

    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        only_events=["2025txbel"],
        state_factory=_backfill_factory(tmp_path),
    )

    assert calls == ["2025txbel"]
    assert result.events_total == 1
    assert result.events_succeeded == ["2025txbel"]


# ─── Successful + failing event handling ───


def test_run_backfill_successful_event_records_match_counts(tmp_path):
    events = [_fit_event("2025txbel")]

    def stub_mode_b(**kwargs):
        return FakeModeBResult(
            event_key=kwargs["event_key"],
            matches_processed=82,
            matches_skipped=4,
        )

    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    assert result.events_succeeded == ["2025txbel"]
    assert result.matches_processed == 82
    assert result.matches_skipped == 4


def test_run_backfill_failing_event_is_captured_and_loop_continues(tmp_path):
    """A mode_b error on one event must NOT abort the whole run."""
    events = [
        _fit_event("2025txbel"),
        _fit_event("2025txdri"),
        _fit_event("2025txdal"),
    ]

    def stub_mode_b(**kwargs):
        ek = kwargs["event_key"]
        if ek == "2025txdri":
            raise RuntimeError("VOD not found")
        return FakeModeBResult(event_key=ek, matches_processed=10)

    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    assert sorted(result.events_succeeded) == ["2025txbel", "2025txdal"]
    assert len(result.events_failed) == 1
    failed_key, reason = result.events_failed[0]
    assert failed_key == "2025txdri"
    assert "VOD not found" in reason
    assert result.matches_processed == 20  # 10 + 10, failed event contributes 0


def test_run_backfill_passes_through_comp_levels_and_deps(tmp_path):
    """Verify we call mode_b with the default (qm, qf, sf, f) tuple and
    propagate frame_resolver + ocr through untouched."""
    seen: dict[str, Any] = {}
    sentinel_resolver = object()
    sentinel_ocr = object()

    def stub_mode_b(**kwargs):
        seen.update(kwargs)
        return FakeModeBResult(event_key=kwargs["event_key"], matches_processed=1)

    run_backfill(
        season=2025,
        events_fetcher=lambda s: [_fit_event("2025txbel")],
        mode_b_runner=stub_mode_b,
        frame_resolver=sentinel_resolver,
        ocr=sentinel_ocr,
        state_factory=_backfill_factory(tmp_path),
    )

    assert seen["event_key"] == "2025txbel"
    assert seen["comp_levels"] == ("qm", "qf", "sf", "f")
    assert seen["frame_resolver"] is sentinel_resolver
    assert seen["ocr"] is sentinel_ocr
    # State dict passed in MUST be fresh, not shared — verify via identity
    assert isinstance(seen["state"], dict)


def test_run_backfill_uses_fresh_state_per_event(tmp_path):
    """The state dict passed to mode_b must be a fresh empty dict per
    event — no cross-contamination via a shared reference."""
    captured: list[int] = []

    def stub_mode_b(**kwargs):
        state = kwargs["state"]
        captured.append(id(state))
        # Mutate the state so we can detect if it leaks across events
        state["touched_by"] = kwargs["event_key"]
        return FakeModeBResult(event_key=kwargs["event_key"])

    events = [_fit_event("2025txbel"), _fit_event("2025txdri")]

    run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    # Two distinct state objects
    assert len(set(captured)) == 2


# ─── Backfill backend isolation ───


def test_get_backfill_backend_local_round_trip(tmp_path, monkeypatch):
    """Round-trip through a backfill backend and verify the file lands
    at the expected path shape."""
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    local_path = tmp_path / "backfill" / "2025" / "2025txbel.json"
    backend = get_backfill_backend(
        event_key="2025txbel",
        season=2025,
        local_path=local_path,
    )
    backend.write({"event_key": "2025txbel", "live_matches": {"qm1": {"ok": True}}})

    assert local_path.exists()
    data = json.loads(local_path.read_text())
    assert data["event_key"] == "2025txbel"


def test_get_backfill_backend_isolates_events(tmp_path, monkeypatch):
    """Two different events must land in different files with no
    cross-contamination."""
    monkeypatch.delenv("STATE_BACKEND", raising=False)

    a_path = tmp_path / "2025" / "2025txbel.json"
    b_path = tmp_path / "2025" / "2025txdri.json"
    a = get_backfill_backend(event_key="2025txbel", season=2025, local_path=a_path)
    b = get_backfill_backend(event_key="2025txdri", season=2025, local_path=b_path)

    a.write({"who": "belton"})
    b.write({"who": "dripping springs"})

    assert a.read() == {"who": "belton"}
    assert b.read() == {"who": "dripping springs"}
    assert a_path.exists() and b_path.exists()
    # Completely different files
    assert a_path.resolve() != b_path.resolve()


def test_run_backfill_writes_to_per_event_files(tmp_path):
    """End-to-end: after run_backfill, each successful event has its own
    file on disk, and failed events have no file."""
    events = [
        _fit_event("2025txbel"),
        _fit_event("2025txdri"),
    ]

    def stub_mode_b(**kwargs):
        ek = kwargs["event_key"]
        # Mutate the provided state so we can verify it's what got written
        kwargs["state"]["event_key"] = ek
        kwargs["state"]["marker"] = f"processed-{ek}"
        return FakeModeBResult(event_key=ek, matches_processed=2)

    run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    bel = tmp_path / "2025" / "2025txbel.json"
    dri = tmp_path / "2025" / "2025txdri.json"
    assert bel.exists() and dri.exists()
    assert json.loads(bel.read_text())["marker"] == "processed-2025txbel"
    assert json.loads(dri.read_text())["marker"] == "processed-2025txdri"


def test_run_backfill_does_not_write_on_event_failure(tmp_path):
    """If mode_b raises for an event, NO file should be written for it."""
    events = [_fit_event("2025txdri")]

    def stub_mode_b(**kwargs):
        raise RuntimeError("boom")

    run_backfill(
        season=2025,
        events_fetcher=lambda s: events,
        mode_b_runner=stub_mode_b,
        state_factory=_backfill_factory(tmp_path),
    )

    target = tmp_path / "2025" / "2025txdri.json"
    assert not target.exists()


# ─── Empty season ───


def test_run_backfill_empty_season_is_not_an_error(tmp_path):
    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: [],
        mode_b_runner=lambda **kw: FakeModeBResult(event_key=""),
        state_factory=_backfill_factory(tmp_path),
    )
    assert result.events_total == 0
    assert result.events_succeeded == []
    assert result.events_failed == []
    assert result.matches_processed == 0


def test_run_backfill_all_non_fit_empty_result(tmp_path):
    """Events exist but none are FIT; result should be empty, not an error."""
    result = run_backfill(
        season=2025,
        events_fetcher=lambda s: [_non_fit_event("2025mndu")],
        mode_b_runner=lambda **kw: FakeModeBResult(event_key=""),
        state_factory=_backfill_factory(tmp_path),
    )
    assert result.events_total == 0
    assert result.events_succeeded == []


# ─── Summary formatting ───


def test_format_summary_table_contains_key_fields():
    result = BackfillResult(
        season=2025,
        events_total=3,
        events_succeeded=["2025txbel", "2025txdri"],
        events_failed=[("2025txdal", "VOD not found")],
        matches_processed=82,
        matches_skipped=0,
    )
    out = _format_summary_table(result)
    assert "season 2025" in out
    assert "2025txbel" in out
    assert "2025txdal" in out
    assert "VOD not found" in out
    assert "Matches processed: 82" in out


# ─── CLI smoke ───


def test_cli_help_returns_zero():
    """`python -m workers.backfill --help` must exit 0 with no side effects."""
    proc = subprocess.run(
        [sys.executable, "-m", "workers.backfill", "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "backfill" in proc.stdout.lower()
    assert "--season" in proc.stdout
