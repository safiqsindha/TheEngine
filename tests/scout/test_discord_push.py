"""Tests for workers/discord_push.py — D1 Discord webhook wrapper.

All tests run offline — no `requests` network calls. The HTTP post is
injected via `_post_fn`, the clock via `_clock`, and the dedupe state
backend via `_dedupe_backend` (a LocalFileBackend pointed at a tmp file).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers import discord_push  # noqa: E402
from workers.discord_push import (  # noqa: E402
    format_anomaly,
    format_event_end_digest,
    format_heads_up,
    post,
)
from workers.state_backend import LocalFileBackend  # noqa: E402


# ─── Test helpers ───


@dataclass
class _StubMatch:
    match_key: str = "2026txbel_qm32"
    red_teams: tuple = (2950, 1234, 5678)
    blue_teams: tuple = (148, 254, 1678)


class _StubResponse:
    def __init__(self, status_code: int = 204):
        self.status_code = status_code


class _RecordingPost:
    """Callable that records each (url, payload) it's invoked with."""
    def __init__(self, status_code: int = 204, raise_exc: Exception | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._status = status_code
        self._raise = raise_exc

    def __call__(self, url: str, payload: dict[str, Any]) -> Any:
        self.calls.append((url, payload))
        if self._raise is not None:
            raise self._raise
        return _StubResponse(self._status)


class _FakeClock:
    """Monotonic clock that only moves when tick() is called."""
    def __init__(self, start: float = 0.0):
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Clear the module-level last-post dict between tests."""
    discord_push._reset_rate_limit_state()
    yield
    discord_push._reset_rate_limit_state()


def _tmp_backend(tmp_path: Path, name: str = "dedupe.json") -> LocalFileBackend:
    return LocalFileBackend(tmp_path / name)


# ─── format_* shape tests ───


def test_format_heads_up_shape():
    payload = format_heads_up(_StubMatch(), opponent_team=254, breakdown_event="2026txbel")
    assert "content" in payload
    assert "embeds" in payload and len(payload["embeds"]) == 1
    assert "2026txbel_qm32" in payload["content"]
    assert "254" in payload["content"]
    assert payload["embeds"][0]["title"].endswith("2026txbel_qm32")


def test_format_anomaly_shape():
    payload = format_anomaly(
        team=254, event_key="2026txdal",
        match_key="2026txdal_qm12", score=218, reason="z-score +3.4",
    )
    assert "2026txdal_qm12" in payload["content"]
    assert "218" in payload["content"]
    desc = payload["embeds"][0]["description"]
    assert "254" in desc and "2026txdal" in desc
    assert "z-score" in desc


def test_format_event_end_digest_shape():
    payload = format_event_end_digest(
        event_key="2026txdal",
        top_three=[
            {"team": 254, "avg_score": 145.3},
            {"team": 2056, "avg_score": 138.9},
            {"team": 1678, "avg_score": 132.1},
        ],
        match_count=72,
    )
    assert "2026txdal" in payload["content"]
    assert "72" in payload["content"]
    desc = payload["embeds"][0]["description"]
    assert "254" in desc and "2056" in desc and "1678" in desc


def test_format_event_end_digest_handles_empty_top_three():
    payload = format_event_end_digest("2026txdal", top_three=[], match_count=0)
    assert "0" in payload["content"]
    assert "no qualifying teams" in payload["embeds"][0]["description"]


# ─── post() — basic path ───


def test_post_empty_url_is_noop(tmp_path):
    rec = _RecordingPost()
    ok = post(
        "",
        {"content": "hi"},
        _post_fn=rec,
        _dedupe_backend=_tmp_backend(tmp_path),
    )
    assert ok is False
    assert rec.calls == []


def test_post_success_fires_once(tmp_path):
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    ok = post(
        "https://discord.example/webhooks/abc",
        {"content": "hi"},
        dedupe_key="alert-1",
        _post_fn=rec,
        _dedupe_backend=backend,
    )
    assert ok is True
    assert len(rec.calls) == 1
    stored = backend.read()
    assert stored is not None and "alert-1" in set(stored.get("seen", []))


def test_post_network_failure_returns_false_and_does_not_poison_dedupe(tmp_path):
    rec = _RecordingPost(raise_exc=RuntimeError("network down"))
    backend = _tmp_backend(tmp_path)
    ok = post(
        "https://discord.example/webhooks/abc",
        {"content": "hi"},
        dedupe_key="alert-1",
        _post_fn=rec,
        _dedupe_backend=backend,
    )
    assert ok is False
    # Dedupe state must not contain the key — retry must be allowed.
    stored = backend.read() or {}
    assert "alert-1" not in set(stored.get("seen", []))


def test_post_non_2xx_returns_false_and_does_not_poison_dedupe(tmp_path):
    rec = _RecordingPost(status_code=500)
    backend = _tmp_backend(tmp_path)
    ok = post(
        "https://discord.example/webhooks/abc",
        {"content": "hi"},
        dedupe_key="alert-1",
        _post_fn=rec,
        _dedupe_backend=backend,
    )
    assert ok is False
    stored = backend.read() or {}
    assert "alert-1" not in set(stored.get("seen", []))


# ─── Dedupe ───


def test_post_dedupe_second_call_is_noop(tmp_path):
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    url = "https://discord.example/webhooks/abc"

    ok1 = post(url, {"content": "hi"}, dedupe_key="alert-1",
               _post_fn=rec, _dedupe_backend=backend)
    ok2 = post(url, {"content": "hi again"}, dedupe_key="alert-1",
               _post_fn=rec, _dedupe_backend=backend)

    assert ok1 is True
    assert ok2 is False
    assert len(rec.calls) == 1  # second call never hit the network


def test_post_distinct_dedupe_keys_both_fire(tmp_path):
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    url = "https://discord.example/webhooks/abc"

    clock = _FakeClock(start=0.0)
    # use long enough interval to not hit rate limit on second call
    post(url, {"content": "1"}, dedupe_key="a",
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    clock.now += 10.0
    post(url, {"content": "2"}, dedupe_key="b",
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    assert len(rec.calls) == 2


# ─── Rate limiting ───


def test_post_rate_limit_sleeps_when_under_interval(tmp_path):
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    url = "https://discord.example/webhooks/abc"
    clock = _FakeClock(start=0.0)

    post(url, {"content": "a"}, dedupe_key="a", min_interval_s=1.5,
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    # Fire again 0.2s later — should sleep ~1.3s.
    clock.now = 0.2
    post(url, {"content": "b"}, dedupe_key="b", min_interval_s=1.5,
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)

    assert len(rec.calls) == 2
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(1.3, abs=1e-6)


def test_post_rate_limit_does_not_sleep_when_over_interval(tmp_path):
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    url = "https://discord.example/webhooks/abc"
    clock = _FakeClock(start=0.0)

    post(url, {"content": "a"}, dedupe_key="a", min_interval_s=1.5,
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    clock.now = 5.0
    post(url, {"content": "b"}, dedupe_key="b", min_interval_s=1.5,
         _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)

    assert len(rec.calls) == 2
    assert clock.sleeps == []


def test_post_rate_limit_per_url(tmp_path):
    """Different webhooks should have independent rate-limit clocks."""
    rec = _RecordingPost(status_code=204)
    backend = _tmp_backend(tmp_path)
    clock = _FakeClock(start=0.0)

    post("https://discord.example/wh/a", {"content": "1"}, dedupe_key="k1",
         min_interval_s=1.5, _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    # Same instant, different URL → no sleep.
    post("https://discord.example/wh/b", {"content": "2"}, dedupe_key="k2",
         min_interval_s=1.5, _post_fn=rec, _dedupe_backend=backend,
         _clock=clock, _sleep=clock.sleep)
    assert clock.sleeps == []
    assert len(rec.calls) == 2
