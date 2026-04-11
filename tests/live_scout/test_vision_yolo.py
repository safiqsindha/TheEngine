"""Tests for eye/vision_yolo.py — Phase 2 T2 V1.

VisionEvent dataclass + FakeYOLOModel + VisionYolo wrapper +
aggregate_cycle_counts / aggregate_climb_results helpers.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eye"))
sys.path.insert(0, str(ROOT / "scout"))

from vision_yolo import (  # noqa: E402
    FakeYOLOModel,
    VisionEvent,
    VisionYolo,
    _load_real_model,
    aggregate_climb_results,
    aggregate_cycle_counts,
)


# ─── VisionEvent ───


def _ev(**overrides):
    base = dict(
        frame_idx=0,
        event_type="cycle",
        team_num=2950,
        confidence=0.9,
        bbox=(10.0, 20.0, 110.0, 220.0),
    )
    base.update(overrides)
    return VisionEvent(**base)


def test_vision_event_constructs_and_serializes_round_trip():
    ev = _ev()
    d = ev.to_dict()
    assert d["event_type"] == "cycle"
    assert d["team_num"] == 2950
    assert d["bbox"] == [10.0, 20.0, 110.0, 220.0]
    rebuilt = VisionEvent.from_dict(d)
    assert rebuilt.to_dict() == d


def test_vision_event_allows_team_none():
    ev = _ev(team_num=None, event_type="defense")
    assert ev.team_num is None
    assert ev.to_dict()["team_num"] is None


def test_vision_event_rejects_invalid_event_type():
    with pytest.raises(ValueError, match="invalid event_type"):
        _ev(event_type="not_a_real_type")


def test_vision_event_rejects_confidence_out_of_range():
    with pytest.raises(ValueError, match="confidence out of range"):
        _ev(confidence=1.5)
    with pytest.raises(ValueError, match="confidence out of range"):
        _ev(confidence=-0.1)


def test_vision_event_rejects_team_num_out_of_range():
    with pytest.raises(ValueError, match="team_num out of range"):
        _ev(team_num=0)
    with pytest.raises(ValueError, match="team_num out of range"):
        _ev(team_num=100000)


def test_vision_event_rejects_bad_bbox_arity():
    with pytest.raises(ValueError, match="bbox must be 4-tuple"):
        VisionEvent(
            frame_idx=0,
            event_type="cycle",
            team_num=2950,
            confidence=0.9,
            bbox=(0.0, 0.0, 1.0),  # type: ignore[arg-type]
        )


# ─── FakeYOLOModel ───


def test_fake_yolo_returns_scripted_events_for_matching_filename():
    ev1 = _ev(frame_idx=1)
    ev2 = _ev(frame_idx=1, event_type="climb_attempt", team_num=148)
    model = FakeYOLOModel(scripted_events={"frame_0001.jpg": [ev1, ev2]})
    out = model.infer(Path("/some/dir/frame_0001.jpg"))
    assert out == [ev1, ev2]
    assert model.infer_calls == 1


def test_fake_yolo_returns_empty_list_for_unscripted_frame():
    model = FakeYOLOModel(scripted_events={"frame_0001.jpg": [_ev()]})
    assert model.infer(Path("frame_0099.jpg")) == []
    assert model.infer_calls == 1


def test_fake_yolo_default_constructor_returns_empty_lists():
    model = FakeYOLOModel()
    assert model.infer(Path("frame_0001.jpg")) == []


# ─── VisionYolo wrapper ───


def test_vision_yolo_uses_injected_model():
    fake = FakeYOLOModel(scripted_events={"frame_0001.jpg": [_ev()]})
    y = VisionYolo(model=fake)
    out = y.infer_frames([Path("frame_0001.jpg"), Path("frame_0002.jpg")])
    assert len(out) == 1
    assert out[0].event_type == "cycle"


def test_vision_yolo_default_fake_model():
    y = VisionYolo(model_name="fake")
    assert y.model_name == "fake"
    # Default fake has no scripted events.
    assert y.infer_frames([Path("frame_0001.jpg")]) == []


def test_vision_yolo_real_model_raises_until_v0a():
    with pytest.raises(NotImplementedError, match="V0a"):
        VisionYolo(model_name="some-real-model-id")


def test_load_real_model_raises_with_helpful_message():
    with pytest.raises(NotImplementedError, match="MODEL_NAME"):
        _load_real_model("roboflow/frc-2024")


def test_vision_yolo_preserves_frame_order():
    ev_a = _ev(frame_idx=1, team_num=2950)
    ev_b = _ev(frame_idx=2, team_num=148)
    ev_c = _ev(frame_idx=3, team_num=2950)
    fake = FakeYOLOModel(scripted_events={
        "frame_0001.jpg": [ev_a],
        "frame_0002.jpg": [ev_b],
        "frame_0003.jpg": [ev_c],
    })
    y = VisionYolo(model=fake)
    out = y.infer_frames([
        Path("frame_0001.jpg"),
        Path("frame_0002.jpg"),
        Path("frame_0003.jpg"),
    ])
    assert [e.frame_idx for e in out] == [1, 2, 3]


# ─── aggregate_cycle_counts ───


def test_cycle_counts_groups_by_team():
    events = [
        _ev(frame_idx=1, team_num=2950),
        _ev(frame_idx=2, team_num=2950),
        _ev(frame_idx=3, team_num=148),
    ]
    assert aggregate_cycle_counts(events) == {"2950": 2, "148": 1}


def test_cycle_counts_ignores_non_cycle_events():
    events = [
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=2950, event_type="climb_success"),
        _ev(team_num=2950, event_type="defense"),
    ]
    assert aggregate_cycle_counts(events) == {"2950": 1}


def test_cycle_counts_skips_team_none():
    events = [
        _ev(team_num=None, event_type="cycle"),
        _ev(team_num=2950, event_type="cycle"),
    ]
    assert aggregate_cycle_counts(events) == {"2950": 1}


def test_cycle_counts_empty_list():
    assert aggregate_cycle_counts([]) == {}


# ─── aggregate_climb_results ───


def test_climb_results_picks_success_over_attempt():
    events = [
        _ev(team_num=2950, event_type="climb_attempt"),
        _ev(team_num=2950, event_type="climb_success"),
    ]
    assert aggregate_climb_results(events) == {"2950": "success"}


def test_climb_results_attempt_beats_failure():
    events = [
        _ev(team_num=2950, event_type="climb_failure"),
        _ev(team_num=2950, event_type="climb_attempt"),
    ]
    assert aggregate_climb_results(events) == {"2950": "attempt"}


def test_climb_results_keeps_success_when_failure_comes_later():
    """Order doesn't matter — precedence does."""
    events = [
        _ev(team_num=2950, event_type="climb_success"),
        _ev(team_num=2950, event_type="climb_failure"),
    ]
    assert aggregate_climb_results(events) == {"2950": "success"}


def test_climb_results_ignores_non_climb_events():
    events = [
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=2950, event_type="defense"),
    ]
    assert aggregate_climb_results(events) == {}


def test_climb_results_skips_team_none():
    events = [_ev(team_num=None, event_type="climb_success")]
    assert aggregate_climb_results(events) == {}


def test_climb_results_per_team_independent():
    events = [
        _ev(team_num=2950, event_type="climb_success"),
        _ev(team_num=148, event_type="climb_failure"),
        _ev(team_num=254, event_type="climb_attempt"),
    ]
    assert aggregate_climb_results(events) == {
        "2950": "success",
        "148": "failure",
        "254": "attempt",
    }


# ─── Cross-module: aggregator output passes LiveMatch validation ───


def test_aggregator_output_passes_live_match_validation():
    """The aggregators must produce dicts that LiveMatch.__post_init__
    accepts without modification — that's the contract with the worker."""
    from live_match import LiveMatch

    events = [
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=2950, event_type="cycle"),
        _ev(team_num=148, event_type="cycle"),
        _ev(team_num=2950, event_type="climb_success"),
        _ev(team_num=148, event_type="climb_failure"),
    ]

    cycle_counts = aggregate_cycle_counts(events)
    climb_results = aggregate_climb_results(events)
    vision_events = [e.to_dict() for e in events]

    m = LiveMatch(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        match_num=32,
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
        vision_events=vision_events,
        cycle_counts=cycle_counts,
        climb_results=climb_results,
    )
    assert m.cycle_counts == {"2950": 2, "148": 1}
    assert m.climb_results == {"2950": "success", "148": "failure"}
    assert len(m.vision_events) == 5
