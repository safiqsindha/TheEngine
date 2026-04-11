"""Tests for workers/tba_uploader.py — Phase 2 U3.

Hermetic: uses FakeTbaWriter, no HTTP, no `requests` import.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402
from tba_writer import TbaWriteResponse  # noqa: E402
from workers.tba_uploader import (  # noqa: E402
    TbaUploadResult,
    _looks_like_real_video_id,
    find_pending_uploads,
    run_tba_uploader,
    upload_one_match,
)


# ─── Fake writer ───


class FakeTbaWriter:
    """Drop-in replacement for scout.tba_writer.TbaWriter.

    Configure with a dict `{video_key: TbaWriteResponse}` to script
    per-upload responses; default is a 200 OK for everything.
    """

    def __init__(self, *, responses=None, dry_run=False):
        self._responses = dict(responses or {})
        self.dry_run = dry_run
        self.calls = []  # list of (event_key, match_key, video_key)

    def add_match_video(self, *, event_key, match_key, video_key):
        self.calls.append((event_key, match_key, video_key))
        if video_key in self._responses:
            return self._responses[video_key]
        return TbaWriteResponse(status="ok", http_status=200, attempts=1)


# ─── Helpers ───


def _live_match(match_short="qm32", match_num=32, video_id="WpzeaX1vgeQ", **overrides):
    base = dict(
        event_key="2026txbel",
        match_key=f"2026txbel_{match_short}",
        match_num=match_num,
        comp_level="qm",
        red_teams=[2950, 1234, 5678],
        blue_teams=[148, 254, 1678],
        red_score=88,
        blue_score=72,
        winning_alliance="red",
        timer_state="post",
        source_video_id=video_id,
        source_tier="vod",
        confidence=0.97,
    )
    base.update(overrides)
    return LiveMatch(**base).to_dict()


def _state_with(*records):
    return {
        "live_matches": {r["match_key"]: r for r in records},
        "teams": {},
    }


# ─── _looks_like_real_video_id ───


@pytest.mark.parametrize("vid,expected", [
    ("WpzeaX1vgeQ", True),
    ("dQw4w9WgXcQ", True),
    ("", False),
    ("eye/.cache/WpzeaX1vgeQ/frames", False),   # frame dir path
    ("eye\\.cache\\foo", False),                # backslash path
    ("abc", False),                              # too short
    ("a" * 40, False),                           # too long
])
def test_looks_like_real_video_id(vid, expected):
    assert _looks_like_real_video_id(vid) is expected


# ─── find_pending_uploads ───


def test_find_pending_uploads_skips_marked():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    b["tba_uploaded"] = True
    state = _state_with(a, b)
    pending = find_pending_uploads(state, event_key="2026txbel")
    assert [r["match_key"] for r in pending] == ["2026txbel_qm1"]


def test_find_pending_uploads_force_ignores_marked():
    a = _live_match("qm1", 1)
    a["tba_uploaded"] = True
    state = _state_with(a)
    pending = find_pending_uploads(state, event_key="2026txbel", force=True)
    assert len(pending) == 1


def test_find_pending_uploads_filters_by_event_key():
    a = _live_match("qm1", 1)
    b = _live_match(
        "qm1", 1,
        event_key="2026txdri",
        match_key="2026txdri_qm1",
    )
    state = _state_with(a, b)
    pending = find_pending_uploads(state, event_key="2026txbel")
    assert [r["match_key"] for r in pending] == ["2026txbel_qm1"]


def test_find_pending_uploads_only_match_key_overrides():
    a = _live_match("qm1", 1)
    a["tba_uploaded"] = True
    state = _state_with(a)
    pending = find_pending_uploads(state, only_match_key="2026txbel_qm1")
    assert len(pending) == 1


# ─── upload_one_match ───


def test_upload_one_match_happy_path():
    record = _live_match("qm32", 32)
    writer = FakeTbaWriter()
    status, resp = upload_one_match(record, writer=writer)
    assert status == "processed"
    assert resp.ok
    assert writer.calls == [("2026txbel", "2026txbel_qm32", "WpzeaX1vgeQ")]


def test_upload_one_match_already_exists():
    record = _live_match("qm32", 32, video_id="abcdefghijk")
    writer = FakeTbaWriter(responses={
        "abcdefghijk": TbaWriteResponse(
            status="already_exists", http_status=400,
            body="already there", attempts=1,
        ),
    })
    status, _ = upload_one_match(record, writer=writer)
    assert status == "already_uploaded"


def test_upload_one_match_skipped_no_video_when_frame_dir_path():
    record = _live_match("qm32", 32, video_id="eye/.cache/foo/frames")
    writer = FakeTbaWriter()
    status, resp = upload_one_match(record, writer=writer)
    assert status == "skipped_no_video"
    assert resp is None
    assert writer.calls == []


def test_upload_one_match_error_passthrough():
    record = _live_match("qm32", 32, video_id="abcdefghijk")
    writer = FakeTbaWriter(responses={
        "abcdefghijk": TbaWriteResponse(
            status="error:http_500", http_status=500, attempts=3,
        ),
    })
    status, _ = upload_one_match(record, writer=writer)
    assert status == "error:error:http_500"


def test_upload_one_match_missing_keys():
    record = {"event_key": "", "match_key": "", "source_video_id": "abc"}
    writer = FakeTbaWriter()
    status, _ = upload_one_match(record, writer=writer)
    assert status == "error:missing_keys"


# ─── run_tba_uploader ───


def test_run_uploader_processes_all_pending():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    b = _live_match("qm2", 2, video_id="lmnopqrstuv")
    state = _state_with(a, b)
    writer = FakeTbaWriter()

    result = run_tba_uploader(
        state=state, writer=writer, event_key="2026txbel",
    )
    assert sorted(result.processed) == ["2026txbel_qm1", "2026txbel_qm2"]
    # Both records get the flag set
    assert state["live_matches"]["2026txbel_qm1"]["tba_uploaded"] is True
    assert state["live_matches"]["2026txbel_qm2"]["tba_uploaded"] is True


def test_run_uploader_already_exists_still_marks_flag():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    state = _state_with(a)
    writer = FakeTbaWriter(responses={
        "abcdefghijk": TbaWriteResponse(
            status="already_exists", http_status=400, attempts=1,
        ),
    })
    result = run_tba_uploader(
        state=state, writer=writer, event_key="2026txbel",
    )
    assert result.already_uploaded == ["2026txbel_qm1"]
    assert state["live_matches"]["2026txbel_qm1"]["tba_uploaded"] is True


def test_run_uploader_census_records_already_marked():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    b = _live_match("qm2", 2, video_id="lmnopqrstuv")
    b["tba_uploaded"] = True
    state = _state_with(a, b)

    result = run_tba_uploader(
        state=state, writer=FakeTbaWriter(), event_key="2026txbel",
    )
    assert result.processed == ["2026txbel_qm1"]
    assert result.skipped_already_marked == ["2026txbel_qm2"]


def test_run_uploader_skips_records_without_video():
    a = _live_match("qm1", 1, video_id="")
    a["source_video_id"] = ""  # already empty, belt + suspenders
    state = _state_with(a)
    result = run_tba_uploader(
        state=state, writer=FakeTbaWriter(), event_key="2026txbel",
    )
    assert result.skipped_no_video == ["2026txbel_qm1"]
    assert result.processed == []


def test_run_uploader_error_does_not_mark_flag():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    state = _state_with(a)
    writer = FakeTbaWriter(responses={
        "abcdefghijk": TbaWriteResponse(
            status="error:http_503", http_status=503, attempts=3,
        ),
    })
    result = run_tba_uploader(
        state=state, writer=writer, event_key="2026txbel",
    )
    assert result.errors
    assert state["live_matches"]["2026txbel_qm1"].get("tba_uploaded") is not True


def test_run_uploader_orchestrator_exception_is_caught():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    state = _state_with(a)

    class BoomWriter:
        dry_run = False

        def add_match_video(self, **kw):
            raise RuntimeError("kaboom")

    result = run_tba_uploader(
        state=state, writer=BoomWriter(), event_key="2026txbel",
    )
    assert len(result.errors) == 1
    assert "orchestrator:kaboom" in result.errors[0][1]


def test_run_uploader_only_match_key_is_targeted():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    b = _live_match("qm2", 2, video_id="lmnopqrstuv")
    state = _state_with(a, b)
    writer = FakeTbaWriter()

    result = run_tba_uploader(
        state=state, writer=writer, only_match_key="2026txbel_qm2",
    )
    assert result.processed == ["2026txbel_qm2"]
    assert result.skipped_already_marked == []  # census not done in only-match mode
    # qm1 untouched
    assert state["live_matches"]["2026txbel_qm1"].get("tba_uploaded") is not True


def test_run_uploader_dry_run_flag_propagates():
    a = _live_match("qm1", 1, video_id="abcdefghijk")
    state = _state_with(a)
    writer = FakeTbaWriter(dry_run=True, responses={
        "abcdefghijk": TbaWriteResponse(status="ok", http_status=0, dry_run=True),
    })
    result = run_tba_uploader(
        state=state, writer=writer, event_key="2026txbel",
    )
    assert result.dry_run is True


def test_result_to_dict_round_trip():
    result = TbaUploadResult(
        processed=["a"],
        already_uploaded=["b"],
        skipped_already_marked=["c"],
        skipped_no_video=["d"],
        errors=[("e", "boom")],
    )
    d = result.to_dict()
    assert d["total_seen"] == 5
    assert d["processed"] == ["a"]
    assert d["already_uploaded"] == ["b"]
    assert d["errors"] == [("e", "boom")]
