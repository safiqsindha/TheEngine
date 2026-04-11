"""Tests for workers/mode_b.py — W3 Mode B backfill worker (Gate 3).

Mirrors the offline / DI test pattern from test_mode_a.py: the TBA
matches fetcher, frame resolver, and OverlayOCR are all stubs so this
test file never loads PaddleOCR, ffmpeg, yt-dlp, or hls_pull.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eye"))
sys.path.insert(0, str(ROOT / "scout"))

from workers.mode_b import (  # noqa: E402
    ModeBResult,
    _comp_level_match_key,
    find_missing_matches,
    make_directory_pattern_resolver,
    process_match,
    resolve_match_video_id,
    run_mode_b,
)


# ─── Fixtures ───


def _tba_match(
    *,
    comp_level: str = "qm",
    match_number: int,
    set_number: Optional[int] = None,
    red_teams: Optional[list[int]] = None,
    blue_teams: Optional[list[int]] = None,
    videos: Optional[list[dict[str, Any]]] = None,
    actual_time: int = 1_700_000_000,
) -> dict[str, Any]:
    red_teams = red_teams if red_teams is not None else [2950, 1234, 5678]
    blue_teams = blue_teams if blue_teams is not None else [148, 254, 1678]
    out: dict[str, Any] = {
        "comp_level": comp_level,
        "match_number": match_number,
        "set_number": set_number,
        "actual_time": actual_time,
        "alliances": {
            "red": {
                "team_keys": [f"frc{t}" for t in red_teams],
                "score": -1,
            },
            "blue": {
                "team_keys": [f"frc{t}" for t in blue_teams],
                "score": -1,
            },
        },
    }
    if videos is not None:
        out["videos"] = videos
    return out


class FakeOCR:
    """OverlayOCR stand-in — same pattern as test_mode_a.FakeOCR."""

    def __init__(self, by_path: dict[str, dict[str, Any]]):
        self._by_path = by_path

    def read_breakdown_screen(self, frame_path: str) -> dict[str, Any]:
        return self._by_path.get(str(frame_path), {"is_breakdown": False})


class CleanupSentinel:
    """A cleanup handle that records whether the worker closed it.

    Used to prove `process_match` honors the finally-block cleanup path
    even when OCR raises mid-run.
    """

    def __init__(self):
        self.closed = False
        # process_match's finally block only runs cleanup for Path cleanup
        # handles — which this sentinel pretends to be via a property.


class SentinelDir:
    """A fake cleanup dir: mode_b's finally block only calls shutil.rmtree
    on Path instances that report as dirs. We create a real tmp dir so we
    can observe that the worker cleaned it up."""

    def __init__(self, tmp_path: Path):
        self.path = tmp_path / "sentinel_dir"
        self.path.mkdir()
        (self.path / "placeholder.txt").write_text("x")

    @property
    def cleaned(self) -> bool:
        return not self.path.exists()


# ─── _comp_level_match_key ───


def test_comp_level_match_key_qm():
    m = _tba_match(match_number=32)
    assert _comp_level_match_key("2026txbel", m) == "2026txbel_qm32"


def test_comp_level_match_key_quarterfinal():
    m = _tba_match(comp_level="qf", match_number=1, set_number=2)
    assert _comp_level_match_key("2026txbel", m) == "2026txbel_qf2m1"


def test_comp_level_match_key_semifinal():
    m = _tba_match(comp_level="sf", match_number=3, set_number=1)
    assert _comp_level_match_key("2026txbel", m) == "2026txbel_sf1m3"


def test_comp_level_match_key_final():
    m = _tba_match(comp_level="f", match_number=2, set_number=1)
    assert _comp_level_match_key("2026txbel", m) == "2026txbel_f1m2"


def test_comp_level_match_key_missing_comp_level_returns_none():
    assert _comp_level_match_key("2026txbel", {"match_number": 1}) is None


def test_comp_level_match_key_missing_match_number_returns_none():
    assert _comp_level_match_key("2026txbel", {"comp_level": "qm"}) is None


def test_comp_level_match_key_non_int_match_number_returns_none():
    m = _tba_match(match_number=32)
    m["match_number"] = "potato"
    assert _comp_level_match_key("2026txbel", m) is None


def test_comp_level_match_key_zero_match_number_returns_none():
    m = _tba_match(match_number=0)
    assert _comp_level_match_key("2026txbel", m) is None


def test_comp_level_match_key_bad_set_number_returns_none():
    m = _tba_match(comp_level="qf", match_number=1)
    m["set_number"] = "banana"
    assert _comp_level_match_key("2026txbel", m) is None


def test_comp_level_match_key_playoff_without_set_number_returns_none():
    """build_match_key raises ValueError when a playoff lacks set_num."""
    m = _tba_match(comp_level="qf", match_number=1, set_number=None)
    assert _comp_level_match_key("2026txbel", m) is None


# ─── find_missing_matches ───


def test_find_missing_matches_skips_existing_live_matches_keys():
    matches = [
        _tba_match(match_number=30),
        _tba_match(match_number=31),
        _tba_match(match_number=32),
    ]
    state = {"live_matches": {"2026txbel_qm31": {"match_key": "2026txbel_qm31"}}}
    missing = find_missing_matches(matches, state, "2026txbel")
    nums = [m["match_number"] for m in missing]
    assert nums == [30, 32]


def test_find_missing_matches_preserves_order():
    matches = [_tba_match(match_number=n) for n in (10, 5, 8, 3)]
    missing = find_missing_matches(matches, {"live_matches": {}}, "2026txbel")
    assert [m["match_number"] for m in missing] == [10, 5, 8, 3]


def test_find_missing_matches_filters_by_comp_levels_default_qm_only():
    matches = [
        _tba_match(match_number=30),
        _tba_match(comp_level="qf", match_number=1, set_number=1),
        _tba_match(match_number=31),
    ]
    missing = find_missing_matches(matches, {"live_matches": {}}, "2026txbel")
    assert [m["comp_level"] for m in missing] == ["qm", "qm"]


def test_find_missing_matches_comp_levels_override_allows_playoffs():
    matches = [
        _tba_match(match_number=30),
        _tba_match(comp_level="qf", match_number=1, set_number=1),
        _tba_match(comp_level="sf", match_number=1, set_number=1),
        _tba_match(comp_level="f", match_number=1, set_number=1),
    ]
    missing = find_missing_matches(
        matches, {"live_matches": {}}, "2026txbel",
        comp_levels=("qm", "qf", "sf", "f"),
    )
    assert [m["comp_level"] for m in missing] == ["qm", "qf", "sf", "f"]


def test_find_missing_matches_skips_unparseable_entries():
    matches = [
        _tba_match(match_number=30),
        {"comp_level": "qm"},  # missing match_number
        _tba_match(match_number=31),
    ]
    missing = find_missing_matches(matches, {"live_matches": {}}, "2026txbel")
    assert [m["match_number"] for m in missing] == [30, 31]


def test_find_missing_matches_handles_empty_state():
    matches = [_tba_match(match_number=30), _tba_match(match_number=31)]
    missing = find_missing_matches(matches, {}, "2026txbel")
    assert len(missing) == 2


# ─── resolve_match_video_id ───


def test_resolve_match_video_id_first_youtube_key():
    m = _tba_match(match_number=1, videos=[
        {"type": "youtube", "key": "abc123"},
        {"type": "youtube", "key": "def456"},
    ])
    assert resolve_match_video_id(m) == "abc123"


def test_resolve_match_video_id_no_videos_field_returns_none():
    m = _tba_match(match_number=1)
    assert resolve_match_video_id(m) is None


def test_resolve_match_video_id_empty_videos_returns_none():
    m = _tba_match(match_number=1, videos=[])
    assert resolve_match_video_id(m) is None


def test_resolve_match_video_id_none_videos_returns_none():
    m = _tba_match(match_number=1)
    m["videos"] = None
    assert resolve_match_video_id(m) is None


def test_resolve_match_video_id_skips_non_youtube_entries():
    m = _tba_match(match_number=1, videos=[
        {"type": "tba", "key": "xyz"},
        {"type": "youtube", "key": "real_key"},
    ])
    assert resolve_match_video_id(m) == "real_key"


def test_resolve_match_video_id_skips_missing_key():
    m = _tba_match(match_number=1, videos=[
        {"type": "youtube"},
        {"type": "youtube", "key": ""},
        {"type": "youtube", "key": "good"},
    ])
    assert resolve_match_video_id(m) == "good"


def test_resolve_match_video_id_skips_malformed_entries():
    m = _tba_match(match_number=1, videos=[
        "not a dict",
        None,
        {"type": "youtube", "key": "good"},
    ])
    assert resolve_match_video_id(m) == "good"


# ─── make_directory_pattern_resolver ───


def test_directory_pattern_resolver_qm_pattern(tmp_path):
    event = "2026txbel"
    frames_dir = tmp_path / event / "qm32" / "frames"
    frames_dir.mkdir(parents=True)
    f1 = frames_dir / "frame_001.jpg"
    f2 = frames_dir / "frame_002.jpg"
    f1.write_bytes(b"")
    f2.write_bytes(b"")

    pattern = str(tmp_path / "{event}" / "{match_short}" / "frames")
    resolver = make_directory_pattern_resolver(pattern, event_key=event)

    result = resolver(_tba_match(match_number=32))
    assert result is not None
    frames, source_id, cleanup = result
    assert [p.name for p in frames] == ["frame_001.jpg", "frame_002.jpg"]
    assert source_id == str(frames_dir)
    assert cleanup is None  # on-disk cached frames shouldn't be cleaned up


def test_directory_pattern_resolver_playoff_pattern(tmp_path):
    event = "2026txbel"
    frames_dir = tmp_path / event / "qf2m1" / "frames"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_001.jpg").write_bytes(b"")

    pattern = str(tmp_path / "{event}" / "{match_short}" / "frames")
    resolver = make_directory_pattern_resolver(pattern, event_key=event)

    m = _tba_match(comp_level="qf", match_number=1, set_number=2)
    result = resolver(m)
    assert result is not None
    frames, _, _ = result
    assert len(frames) == 1


def test_directory_pattern_resolver_missing_dir_returns_none(tmp_path):
    pattern = str(tmp_path / "{event}" / "{match_short}" / "frames")
    resolver = make_directory_pattern_resolver(pattern, event_key="2026txbel")
    assert resolver(_tba_match(match_number=99)) is None


def test_directory_pattern_resolver_empty_dir_returns_none(tmp_path):
    event = "2026txbel"
    frames_dir = tmp_path / event / "qm5" / "frames"
    frames_dir.mkdir(parents=True)
    # directory exists but contains no frame_*.jpg

    pattern = str(tmp_path / "{event}" / "{match_short}" / "frames")
    resolver = make_directory_pattern_resolver(pattern, event_key=event)
    assert resolver(_tba_match(match_number=5)) is None


def test_directory_pattern_resolver_playoff_without_set_returns_none(tmp_path):
    pattern = str(tmp_path / "{event}" / "{match_short}" / "frames")
    resolver = make_directory_pattern_resolver(pattern, event_key="2026txbel")
    m = _tba_match(comp_level="qf", match_number=1, set_number=None)
    assert resolver(m) is None


# ─── process_match ───


def _make_frames(tmp_path: Path, n: int = 2) -> list[Path]:
    out = []
    for i in range(n):
        p = tmp_path / f"frame_{i + 1:04d}.jpg"
        p.write_bytes(b"")
        out.append(p)
    return out


def test_process_match_processed_path(tmp_path):
    frames = _make_frames(tmp_path)
    ocr = FakeOCR({
        str(frames[1]): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
        },
    })
    m = _tba_match(match_number=32)

    def resolver(_m):
        return frames, "vod_xyz", None

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=m,
        frame_resolver=resolver,
        ocr=ocr,
    )
    assert status == "processed"
    assert live_match is not None
    assert live_match.match_key == "2026txbel_qm32"
    assert live_match.red_score == 88
    assert live_match.blue_score == 72
    assert live_match.source_tier == "vod"  # Mode B always tags vod
    assert live_match.source_video_id == "vod_xyz"


def test_process_match_skipped_no_video(tmp_path):
    m = _tba_match(match_number=32)

    def resolver(_m):
        return None

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=m,
        frame_resolver=resolver,
        ocr=FakeOCR({}),
    )
    assert live_match is None
    assert status == "skipped_no_video"


def test_process_match_skipped_no_breakdown(tmp_path):
    frames = _make_frames(tmp_path)
    m = _tba_match(match_number=32)

    def resolver(_m):
        return frames, "vod_xyz", None

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=m,
        frame_resolver=resolver,
        ocr=FakeOCR({}),  # nothing matches
    )
    assert live_match is None
    assert status == "skipped_no_breakdown"


def test_process_match_resolver_exception_surfaces_as_error(tmp_path):
    m = _tba_match(match_number=32)

    def resolver(_m):
        raise RuntimeError("boom")

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=m,
        frame_resolver=resolver,
        ocr=FakeOCR({}),
    )
    assert live_match is None
    assert status.startswith("error:resolver:")
    assert "boom" in status


def test_process_match_cleanup_honored_on_success(tmp_path):
    frames = _make_frames(tmp_path)
    sentinel = SentinelDir(tmp_path)
    ocr = FakeOCR({
        str(frames[1]): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
        },
    })

    def resolver(_m):
        return frames, "vod_xyz", sentinel.path

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=_tba_match(match_number=32),
        frame_resolver=resolver,
        ocr=ocr,
    )
    assert status == "processed"
    assert sentinel.cleaned, "cleanup dir should have been rmtree'd"


def test_process_match_cleanup_honored_on_ocr_error(tmp_path):
    """Even when the OCR pipeline raises mid-run, the finally block must
    close the cleanup handle."""
    frames = _make_frames(tmp_path)
    sentinel = SentinelDir(tmp_path)

    class ExplodingOCR:
        def read_breakdown_screen(self, frame_path):
            raise RuntimeError("ocr failed hard")

    def resolver(_m):
        return frames, "vod_xyz", sentinel.path

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=_tba_match(match_number=32),
        frame_resolver=resolver,
        ocr=ExplodingOCR(),
    )
    assert live_match is None
    assert status.startswith("error:ocr:")
    assert sentinel.cleaned, "cleanup dir should still be removed after error"


def test_process_match_writes_to_state_when_provided(tmp_path):
    frames = _make_frames(tmp_path)
    ocr = FakeOCR({
        str(frames[1]): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
        },
    })
    m = _tba_match(match_number=32)

    def resolver(_m):
        return frames, "vod_xyz", None

    state = {
        "event_key": "2026txbel",
        "live_matches": {},
        "teams": {},
    }

    live_match, status = process_match(
        event_key="2026txbel",
        tba_match=m,
        frame_resolver=resolver,
        ocr=ocr,
        state=state,
    )
    assert status == "processed"
    assert "2026txbel_qm32" in state["live_matches"]
    assert state["live_matches"]["2026txbel_qm32"]["source_tier"] == "vod"


# ─── run_mode_b orchestrator ───


def _ok_resolver(frames: list[Path]):
    def _r(_m):
        return frames, "vod_xyz", None
    return _r


def _ok_ocr(frames: list[Path]) -> FakeOCR:
    """An OCR mock that resolves the breakdown on the last frame."""
    return FakeOCR({
        str(frames[-1]): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
        },
    })


def test_run_mode_b_all_existing_skipped(tmp_path):
    """If every match in TBA is already in state, none are processed."""
    frames = _make_frames(tmp_path)
    matches = [
        _tba_match(match_number=30),
        _tba_match(match_number=31),
        _tba_match(match_number=32),
    ]
    state = {
        "event_key": "2026txbel",
        "live_matches": {
            "2026txbel_qm30": {"match_key": "2026txbel_qm30"},
            "2026txbel_qm31": {"match_key": "2026txbel_qm31"},
            "2026txbel_qm32": {"match_key": "2026txbel_qm32"},
        },
        "teams": {},
    }

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )

    assert result.processed == []
    assert sorted(result.skipped_existing) == [
        "2026txbel_qm30", "2026txbel_qm31", "2026txbel_qm32",
    ]
    assert result.skipped_no_video == []
    assert result.skipped_no_breakdown == []
    assert result.errors == []
    assert result.total_seen == 3


def test_run_mode_b_mix_of_existing_and_missing(tmp_path):
    """Missing matches should land in `processed` with source_tier='vod'."""
    frames = _make_frames(tmp_path)
    matches = [
        _tba_match(match_number=30),
        _tba_match(match_number=31),
        _tba_match(match_number=32),
    ]
    state = {
        "event_key": "2026txbel",
        "live_matches": {
            "2026txbel_qm31": {
                "event_key": "2026txbel",
                "match_key": "2026txbel_qm31",
                "comp_level": "qm",
                "match_num": 31,
            },
        },
        "teams": {},
    }

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )

    assert sorted(result.processed) == ["2026txbel_qm30", "2026txbel_qm32"]
    assert result.skipped_existing == ["2026txbel_qm31"]
    # State was mutated — new records carry source_tier='vod'
    for k in ("2026txbel_qm30", "2026txbel_qm32"):
        assert k in state["live_matches"]
        assert state["live_matches"][k]["source_tier"] == "vod"


def test_run_mode_b_idempotent_second_run_all_skipped(tmp_path):
    """Running twice with the same state — second run is all-skipped."""
    frames = _make_frames(tmp_path)
    matches = [
        _tba_match(match_number=30),
        _tba_match(match_number=31),
    ]
    state = {
        "event_key": "2026txbel",
        "live_matches": {},
        "teams": {},
    }

    first = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )
    assert sorted(first.processed) == ["2026txbel_qm30", "2026txbel_qm31"]
    assert first.skipped_existing == []

    second = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )
    assert second.processed == []
    assert sorted(second.skipped_existing) == [
        "2026txbel_qm30", "2026txbel_qm31",
    ]


def test_run_mode_b_comp_levels_filter(tmp_path):
    """Default is qm only — playoffs should be ignored."""
    frames = _make_frames(tmp_path)
    matches = [
        _tba_match(match_number=30),
        _tba_match(comp_level="qf", match_number=1, set_number=1),
        _tba_match(comp_level="sf", match_number=1, set_number=1),
        _tba_match(match_number=31),
    ]
    state = {"event_key": "2026txbel", "live_matches": {}, "teams": {}}

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )
    assert sorted(result.processed) == ["2026txbel_qm30", "2026txbel_qm31"]
    # comp_levels filter kept playoffs out of the census entirely
    assert result.total_seen == 2


def test_run_mode_b_comp_levels_override_processes_playoffs(tmp_path):
    frames = _make_frames(tmp_path)
    matches = [
        _tba_match(comp_level="qf", match_number=1, set_number=1),
        _tba_match(comp_level="f", match_number=1, set_number=1),
    ]
    state = {"event_key": "2026txbel", "live_matches": {}, "teams": {}}

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
        comp_levels=("qm", "qf", "sf", "f"),
    )
    assert sorted(result.processed) == ["2026txbel_f1m1", "2026txbel_qf1m1"]


def test_run_mode_b_matches_fetcher_exception_captured(tmp_path):
    def bad_fetcher(ek):
        raise RuntimeError("TBA down")

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=bad_fetcher,
        frame_resolver=_ok_resolver([]),
        ocr=FakeOCR({}),
        state=None,
    )
    assert result.processed == []
    assert len(result.errors) == 1
    key, msg = result.errors[0]
    assert key == "__fetch__"
    assert "TBA down" in msg


def test_run_mode_b_skipped_no_video(tmp_path):
    frames = _make_frames(tmp_path)
    matches = [_tba_match(match_number=30)]

    def resolver(_m):
        return None

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=resolver,
        ocr=_ok_ocr(frames),
        state=None,
    )
    assert result.skipped_no_video == ["2026txbel_qm30"]
    assert result.processed == []


def test_run_mode_b_skipped_no_breakdown(tmp_path):
    frames = _make_frames(tmp_path)
    matches = [_tba_match(match_number=30)]

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=FakeOCR({}),  # OCR finds nothing
        state=None,
    )
    assert result.skipped_no_breakdown == ["2026txbel_qm30"]
    assert result.processed == []


def test_run_mode_b_aggregates_recomputed_only_when_processed(tmp_path):
    """recompute_team_aggregates should update teams when we wrote matches,
    and should be a no-op when nothing new was written."""
    frames = _make_frames(tmp_path)
    # 3+ matches for 2950 so _aggregate_scores produces non-empty output
    matches = [
        _tba_match(match_number=i, red_teams=[2950, 1234, 5678],
                   blue_teams=[148, 254, 1678])
        for i in (30, 31, 32)
    ]
    state = {
        "event_key": "2026txbel",
        "live_matches": {},
        "teams": {
            str(t): {"team": t, "name": f"T{t}", "epa": 50.0, "sd": 10.0}
            for t in [2950, 1234, 5678, 148, 254, 1678]
        },
    }

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )
    assert len(result.processed) == 3
    # 3 matches is the aggregation threshold — real_sd should now exist
    assert "real_sd" in state["teams"]["2950"]
    assert state["teams"]["2950"]["match_count"] == 3

    # Second run adds nothing — aggregates should not be recomputed but
    # the existing values should still be there (no-op path)
    prior_sd = state["teams"]["2950"]["real_sd"]
    result2 = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=state,
    )
    assert result2.processed == []
    assert state["teams"]["2950"]["real_sd"] == prior_sd


def test_run_mode_b_no_state_still_reports(tmp_path):
    """Mode B without a state dict still produces a complete result."""
    frames = _make_frames(tmp_path)
    matches = [_tba_match(match_number=30), _tba_match(match_number=31)]

    result = run_mode_b(
        event_key="2026txbel",
        matches_fetcher=lambda ek: matches,
        frame_resolver=_ok_resolver(frames),
        ocr=_ok_ocr(frames),
        state=None,
    )
    # Nothing was in state → everything treated as missing → everything processed
    assert sorted(result.processed) == ["2026txbel_qm30", "2026txbel_qm31"]
    assert result.skipped_existing == []


def test_mode_b_result_to_dict_shape():
    r = ModeBResult()
    r.processed.append("a")
    r.skipped_existing.append("b")
    r.errors.append(("c", "msg"))
    d = r.to_dict()
    assert d["processed"] == ["a"]
    assert d["skipped_existing"] == ["b"]
    assert d["errors"] == [("c", "msg")]
    assert d["total_seen"] == 3


# ─── Integration test: replay cached PaddleOCR fixture through Mode B ───
#
# Mirrors tests/scout/test_mode_a_integration.py — reuses the same
# wpzeax_ocr_cache.json fixture via _CachedOverlayOCR. Verifies Mode B
# can backfill 2026txdri_qm32 end-to-end with source_tier='vod' from a
# stub frame-resolver (no real frames needed — _CachedOverlayOCR keys
# off `Path(frame_path).name`), and that a second run is idempotent.

import json  # noqa: E402

from overlay_ocr import _parse_breakdown  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OCR_CACHE_PATH = FIXTURES_DIR / "wpzeax_ocr_cache.json"

# Source frame dimensions (see test_mode_a_integration.py)
FRAME_WIDTH = 640
FRAME_HEIGHT = 360


class _CachedOverlayOCR:
    """Drop-in OverlayOCR that replays a frozen OCR snapshot, same as the
    adapter in test_mode_a_integration.py. Keyed by Path.name, so the
    frame paths we pass in don't need to exist on disk."""

    def __init__(self, cache: dict[str, list[dict[str, Any]]]):
        self._cache = cache

    def read_breakdown_screen(self, frame_path: str) -> dict[str, Any]:
        name = Path(frame_path).name
        dets = self._cache.get(name)
        if dets is None:
            return {}
        results = [(d["bbox"], d["text"], d["conf"]) for d in dets]
        return _parse_breakdown(results, FRAME_WIDTH, FRAME_HEIGHT)

    def is_transition_screen(self, frame_path: str) -> bool:
        return False


def _load_ocr_cache() -> dict[str, list[dict[str, Any]]]:
    if not OCR_CACHE_PATH.exists():
        pytest.skip(f"OCR cache fixture missing: {OCR_CACHE_PATH}")
    return json.loads(OCR_CACHE_PATH.read_text())


def _cached_frame_paths(cache: dict) -> list[Path]:
    """Fabricate Path objects keyed to the fixture entries. They don't
    need to exist on disk — _CachedOverlayOCR only reads `.name`."""
    # Use a deterministic parent dir so paths are stable in errors
    parent = Path("/fake-mode-b-frames")
    return [parent / name for name in sorted(cache.keys())]


def _fake_event_matches_txdri(event_key: str) -> list[dict[str, Any]]:
    """TBA stub returning the single qm32 match at 2026txdri that the
    cached OCR fixture covers. Includes a videos entry so the
    resolve_match_video_id() lookup in the resolver is exercised."""
    return [
        {
            "comp_level": "qm",
            "match_number": 32,
            "set_number": None,
            "actual_time": 1_700_000_000,
            "videos": [{"type": "youtube", "key": "WpzeaX1vgeQ"}],
            "alliances": {
                "red": {
                    "team_keys": ["frc4364", "frc9311", "frc10032"],
                    "score": -1,
                },
                "blue": {
                    "team_keys": ["frc2950", "frc3035", "frc7521"],
                    "score": -1,
                },
            },
        }
    ]


def test_mode_b_integration_backfills_qm32_from_cached_ocr():
    """End-to-end Mode B backfill: TBA stub → stub frame resolver →
    cached OCR → build_live_match_from_ocr → state['live_matches'].

    Verifies source_tier='vod' and full field fidelity against the same
    golden record used by test_mode_a_integration.py."""
    cache = _load_ocr_cache()
    frames = _cached_frame_paths(cache)
    ocr = _CachedOverlayOCR(cache)

    state = {
        "event_key": "2026txdri",
        "live_matches": {},
        "teams": {},
    }

    def frame_resolver(tba_match):
        # Provenance field points at the VOD id from TBA videos, matching
        # the way make_tba_video_resolver would report it.
        return frames, "WpzeaX1vgeQ", None

    result = run_mode_b(
        event_key="2026txdri",
        matches_fetcher=_fake_event_matches_txdri,
        frame_resolver=frame_resolver,
        ocr=ocr,
        state=state,
    )

    # The one qm32 match was missing → should be processed
    assert result.processed == ["2026txdri_qm32"]
    assert result.skipped_existing == []
    assert result.errors == []

    # State was populated
    assert "2026txdri_qm32" in state["live_matches"]
    persisted = state["live_matches"]["2026txdri_qm32"]
    assert persisted["red_teams"] == [4364, 9311, 10032]
    assert persisted["blue_teams"] == [2950, 3035, 7521]
    assert persisted["red_score"] == 42
    assert persisted["blue_score"] == 151
    assert persisted["winning_alliance"] == "blue"
    assert persisted["timer_state"] == "post"
    assert persisted["source_video_id"] == "WpzeaX1vgeQ"
    assert persisted["source_tier"] == "vod"


def test_mode_b_integration_second_run_is_idempotent():
    """After Mode B has backfilled qm32, a second identical run should
    skip it entirely — the pick_board state must not grow."""
    cache = _load_ocr_cache()
    frames = _cached_frame_paths(cache)
    ocr = _CachedOverlayOCR(cache)

    state = {
        "event_key": "2026txdri",
        "live_matches": {},
        "teams": {},
    }

    def frame_resolver(_tba_match):
        return frames, "WpzeaX1vgeQ", None

    first = run_mode_b(
        event_key="2026txdri",
        matches_fetcher=_fake_event_matches_txdri,
        frame_resolver=frame_resolver,
        ocr=ocr,
        state=state,
    )
    assert first.processed == ["2026txdri_qm32"]
    snapshot = dict(state["live_matches"]["2026txdri_qm32"])

    second = run_mode_b(
        event_key="2026txdri",
        matches_fetcher=_fake_event_matches_txdri,
        frame_resolver=frame_resolver,
        ocr=ocr,
        state=state,
    )
    assert second.processed == []
    assert second.skipped_existing == ["2026txdri_qm32"]
    # State record unchanged
    assert state["live_matches"]["2026txdri_qm32"] == snapshot
