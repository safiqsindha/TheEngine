"""Tests for workers/vision_worker.py — Phase 2 T2 V3.

Hermetic: uses FakeYOLOModel and an in-memory frame resolver. No
filesystem I/O for frames, no Azure, no PaddleOCR.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eye"))
sys.path.insert(0, str(ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402
from vision_yolo import FakeYOLOModel, VisionEvent, VisionYolo  # noqa: E402
from workers.vision_worker import (  # noqa: E402
    VisionWorkerResult,
    find_unprocessed_matches,
    process_match_vision,
    run_vision_worker,
)


# ─── Helpers ───


def _live_match(match_short: str = "qm32", match_num: int = 32, **overrides):
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
        source_video_id="abc123",
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


def _ev(**overrides):
    base = dict(
        frame_idx=0,
        event_type="cycle",
        team_num=2950,
        confidence=0.9,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )
    base.update(overrides)
    return VisionEvent(**base)


def _scripted_yolo(events):
    """Build a VisionYolo whose fake model returns `events` for any frame."""
    class _Model:
        def __init__(self, evs):
            self._evs = evs

        def infer(self, _frame_path):
            return list(self._evs)
    return VisionYolo(model=_Model(events))


def _stub_resolver(frames=None, video_id="vid", cleanup=None):
    """A FrameResolver that always returns the same fake frames."""
    if frames is None:
        frames = [Path("frame_0001.jpg"), Path("frame_0002.jpg")]

    def _r(_tba_match):
        return frames, video_id, cleanup

    return _r


def _empty_resolver():
    def _r(_tba_match):
        return None
    return _r


# ─── find_unprocessed_matches ───


def test_find_unprocessed_skips_already_processed():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    b["vision_events"] = [{"event_type": "cycle"}]
    state = _state_with(a, b)
    out = find_unprocessed_matches(state, event_key="2026txbel")
    assert [r["match_key"] for r in out] == ["2026txbel_qm1"]


def test_find_unprocessed_force_returns_all():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    b["vision_events"] = [{"event_type": "cycle"}]
    state = _state_with(a, b)
    out = find_unprocessed_matches(state, event_key="2026txbel", force=True)
    keys = sorted(r["match_key"] for r in out)
    assert keys == ["2026txbel_qm1", "2026txbel_qm2"]


def test_find_unprocessed_filters_by_event_key():
    a = _live_match("qm1", 1)
    b = _live_match(
        "qm1", 1,
        event_key="2026txdri",
        match_key="2026txdri_qm1",
    )
    state = _state_with(a, b)
    out = find_unprocessed_matches(state, event_key="2026txbel")
    assert [r["match_key"] for r in out] == ["2026txbel_qm1"]


def test_find_unprocessed_only_match_key_overrides_filters():
    a = _live_match("qm1", 1)
    a["vision_events"] = [{"event_type": "cycle"}]  # would normally be skipped
    state = _state_with(a)
    out = find_unprocessed_matches(state, only_match_key="2026txbel_qm1")
    assert len(out) == 1
    assert out[0]["match_key"] == "2026txbel_qm1"


def test_find_unprocessed_only_match_key_no_match_returns_empty():
    a = _live_match("qm1", 1)
    state = _state_with(a)
    assert find_unprocessed_matches(state, only_match_key="2026txbel_qm99") == []


# ─── process_match_vision ───


def test_process_match_vision_writes_typed_fields():
    record = _live_match("qm32", 32)
    assert record["vision_events"] == []
    events = [
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=148, event_type="climb_success"),
    ]
    vision = _scripted_yolo(events)
    # Resolver returns one frame so vision.infer_frames is called once
    resolver = _stub_resolver(frames=[Path("frame_0001.jpg")])

    mutated, status = process_match_vision(
        record=record, frame_resolver=resolver, vision=vision
    )
    assert status == "processed"
    assert mutated is record  # mutated in place
    assert record["cycle_counts"] == {"2950": 2}
    assert record["climb_results"] == {"148": "success"}
    assert len(record["vision_events"]) == 3
    assert record["vision_events"][0]["event_type"] == "cycle"


def test_process_match_vision_skip_no_frames():
    record = _live_match("qm32", 32)
    resolver = _empty_resolver()
    vision = _scripted_yolo([_ev()])
    _, status = process_match_vision(
        record=record, frame_resolver=resolver, vision=vision
    )
    assert status == "skipped_no_frames"
    # Record untouched
    assert record["vision_events"] == []


def test_process_match_vision_skip_no_events():
    record = _live_match("qm32", 32)
    resolver = _stub_resolver()
    vision = _scripted_yolo([])  # YOLO returns nothing
    _, status = process_match_vision(
        record=record, frame_resolver=resolver, vision=vision
    )
    assert status == "skipped_no_events"
    assert record["vision_events"] == []


def test_process_match_vision_resolver_exception_returns_error():
    record = _live_match("qm32", 32)

    def _bad_resolver(_):
        raise RuntimeError("kaboom")

    vision = _scripted_yolo([_ev()])
    _, status = process_match_vision(
        record=record, frame_resolver=_bad_resolver, vision=vision
    )
    assert status.startswith("error:resolver:")


def test_process_match_vision_bad_record_shape():
    record = {"match_key": "broken", "comp_level": None, "match_num": None}
    vision = _scripted_yolo([_ev()])
    _, status = process_match_vision(
        record=record, frame_resolver=_stub_resolver(), vision=vision
    )
    assert status == "error:bad_record_shape"


def test_process_match_vision_cleans_up_temp_dir(tmp_path):
    """If the resolver returns a cleanup Path that's a directory, it
    must be removed after the worker is done with the frames."""
    cleanup_dir = tmp_path / "frames_temp"
    cleanup_dir.mkdir()
    (cleanup_dir / "frame_0001.jpg").write_bytes(b"")

    record = _live_match("qm32", 32)
    resolver = _stub_resolver(
        frames=[cleanup_dir / "frame_0001.jpg"],
        cleanup=cleanup_dir,
    )
    vision = _scripted_yolo([_ev()])

    _, status = process_match_vision(
        record=record, frame_resolver=resolver, vision=vision
    )
    assert status == "processed"
    assert not cleanup_dir.exists()


# ─── run_vision_worker ───


def test_run_vision_worker_processes_all_unprocessed():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    state = _state_with(a, b)

    vision = _scripted_yolo([_ev(event_type="cycle", team_num=2950)])
    resolver = _stub_resolver(frames=[Path("frame_0001.jpg")])

    result = run_vision_worker(
        event_key="2026txbel",
        state=state,
        frame_resolver=resolver,
        vision=vision,
    )
    assert sorted(result.processed) == ["2026txbel_qm1", "2026txbel_qm2"]
    assert result.skipped_existing == []
    assert state["live_matches"]["2026txbel_qm1"]["cycle_counts"] == {"2950": 1}
    assert state["live_matches"]["2026txbel_qm2"]["cycle_counts"] == {"2950": 1}


def test_run_vision_worker_records_existing_in_census():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    b["vision_events"] = [{"event_type": "cycle"}]
    state = _state_with(a, b)

    vision = _scripted_yolo([_ev()])
    resolver = _stub_resolver()

    result = run_vision_worker(
        event_key="2026txbel",
        state=state,
        frame_resolver=resolver,
        vision=vision,
    )
    assert result.processed == ["2026txbel_qm1"]
    assert result.skipped_existing == ["2026txbel_qm2"]
    assert result.total_seen == 2


def test_run_vision_worker_force_reprocesses():
    a = _live_match("qm1", 1)
    a["vision_events"] = [{"event_type": "cycle", "team_num": 9999, "frame_idx": 0,
                           "confidence": 0.5, "bbox": [0, 0, 1, 1]}]
    a["cycle_counts"] = {"9999": 5}  # stale data
    state = _state_with(a)

    vision = _scripted_yolo([_ev(team_num=2950, event_type="cycle")])
    resolver = _stub_resolver(frames=[Path("frame_0001.jpg")])

    result = run_vision_worker(
        event_key="2026txbel",
        state=state,
        frame_resolver=resolver,
        vision=vision,
        force=True,
    )
    assert result.processed == ["2026txbel_qm1"]
    assert state["live_matches"]["2026txbel_qm1"]["cycle_counts"] == {"2950": 1}


def test_run_vision_worker_only_match_key_targets_one():
    a = _live_match("qm1", 1)
    b = _live_match("qm2", 2)
    state = _state_with(a, b)

    vision = _scripted_yolo([_ev()])
    resolver = _stub_resolver()

    result = run_vision_worker(
        only_match_key="2026txbel_qm2",
        state=state,
        frame_resolver=resolver,
        vision=vision,
    )
    assert result.processed == ["2026txbel_qm2"]
    # Only-match-key mode does not census the rest of the event
    assert result.skipped_existing == []
    # qm1 is untouched
    assert state["live_matches"]["2026txbel_qm1"]["vision_events"] == []


def test_run_vision_worker_reports_no_frames():
    a = _live_match("qm1", 1)
    state = _state_with(a)
    vision = _scripted_yolo([_ev()])

    result = run_vision_worker(
        event_key="2026txbel",
        state=state,
        frame_resolver=_empty_resolver(),
        vision=vision,
    )
    assert result.skipped_no_frames == ["2026txbel_qm1"]
    assert result.processed == []


def test_run_vision_worker_default_vision_is_fake():
    """When no vision is injected, run_vision_worker uses VisionYolo(model_name='fake')
    which returns no events for every frame — so every match lands in skipped_no_events."""
    a = _live_match("qm1", 1)
    state = _state_with(a)

    result = run_vision_worker(
        event_key="2026txbel",
        state=state,
        frame_resolver=_stub_resolver(),
    )
    assert result.skipped_no_events == ["2026txbel_qm1"]
    assert result.processed == []


def test_run_vision_worker_result_to_dict_round_trip():
    result = VisionWorkerResult(
        processed=["a"],
        skipped_existing=["b"],
        skipped_no_frames=["c"],
        skipped_no_events=["d"],
        errors=[("e", "boom")],
    )
    d = result.to_dict()
    assert d["total_seen"] == 5
    assert d["processed"] == ["a"]
    assert d["errors"] == [("e", "boom")]
