"""Tests for workers/synthesis_worker.py — Phase 2 T3 S2/S3.

Hermetic: injects a FakeAnthropicClient and an in-memory brief
backend. Never imports the real `anthropic` SDK.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scout"))

from synthesis_prompt import SynthesisInputs  # noqa: E402
from workers.synthesis_worker import (  # noqa: E402
    BriefDocument,
    SynthesisWorkerResult,
    call_anthropic,
    parse_brief_response,
    run_synthesis_worker,
)


# ─── Fakes ───


class _FakeTextBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, parent):
        self._parent = parent

    def create(self, *, model, max_tokens, system, messages):
        self._parent.calls.append({
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        })
        if self._parent.raise_on_call:
            raise RuntimeError("boom")
        return _FakeMessage(self._parent.response_text)


class FakeAnthropicClient:
    """Minimal stand-in for anthropic.Anthropic."""

    def __init__(self, *, response_text="", raise_on_call=False):
        self.response_text = response_text
        self.raise_on_call = raise_on_call
        self.calls = []
        self.messages = _FakeMessages(self)


class InMemoryBackend:
    """Stand-in for a state_backend — just holds the last write."""

    def __init__(self):
        self.written = None

    def write(self, state):
        self.written = state

    def read(self):
        return self.written


# ─── Fixtures ───


def _state():
    return {
        "event_key": "2026txbel",
        "teams": {
            "148": {"team": 148, "real_avg_score": 95.0, "qual_rank": 1,
                    "qual_record": "9-1", "streak": "HOT"},
            "2950": {"team": 2950, "real_avg_score": 88.0, "qual_rank": 2,
                     "qual_record": "8-2", "streak": ""},
        },
        "live_matches": {
            "2026txbel_qm1": {
                "event_key": "2026txbel",
                "match_key": "2026txbel_qm1",
                "match_num": 1,
                "comp_level": "qm",
                "red_teams": [148, 1, 2],
                "blue_teams": [3, 4, 5],
                "red_score": 100,
                "blue_score": 80,
                "winning_alliance": "red",
            },
        },
        "dnp": [],
        "captains": [148, 254, 2950],
    }


_OPUS_RESPONSE = """\
The Devastators should target 148 for their first pick.

Top picks
  1. #148 — Most consistent scorer, currently HOT streak
  2. #254 — Complements our cycle game
  3. #1678 — Strong defensive option
  4. #2056 — Climbing specialist

Watch list
  #5460 — Trending up after match 20
  #9999 — Defensive specialist we should avoid

Upcoming matches
  qm34 — tough opponent alliance, expect ~90 points
"""


# ─── parse_brief_response ───


def test_parse_happy_path_extracts_top_picks():
    picks, rationale = parse_brief_response(_OPUS_RESPONSE)
    assert picks == [148, 254, 1678, 2056]
    assert "consistent" in rationale["148"].lower()
    assert "climb" in rationale["2056"].lower()


def test_parse_empty_input_returns_empty():
    assert parse_brief_response("") == ([], {})
    assert parse_brief_response("   \n\n  ") == ([], {})


def test_parse_missing_top_picks_section_returns_empty():
    assert parse_brief_response("Just a headline. Nothing else.") == ([], {})


def test_parse_dedupes_team_numbers():
    text = (
        "Top picks\n"
        "  1. #148 great\n"
        "  2. #148 great again\n"
        "  3. #254 solid\n"
    )
    picks, _ = parse_brief_response(text)
    assert picks == [148, 254]


def test_parse_stops_at_blank_line_after_content():
    text = (
        "Top picks\n"
        "  148 great\n"
        "  254 solid\n"
        "\n"
        "Watch list\n"
        "  999 nope\n"
    )
    picks, _ = parse_brief_response(text)
    assert picks == [148, 254]


def test_parse_stops_at_watch_list_header():
    text = (
        "Top picks\n"
        "  148 great\n"
        "Watch list\n"
        "  999 nope\n"
    )
    picks, _ = parse_brief_response(text)
    assert picks == [148]


def test_parse_tolerates_noise_lines_with_no_numbers():
    text = (
        "Top picks\n"
        "  some header with no number\n"
        "  148 — first real pick\n"
        "  254 — second\n"
    )
    picks, _ = parse_brief_response(text)
    assert picks == [148, 254]


def test_parse_rejects_out_of_range_team_numbers():
    text = (
        "Top picks\n"
        "  999999 too big\n"
        "  0 too small\n"
        "  148 ok\n"
    )
    picks, _ = parse_brief_response(text)
    assert picks == [148]


# ─── call_anthropic ───


def test_call_anthropic_happy_path_concatenates_text_blocks():
    client = FakeAnthropicClient(response_text="hello world")
    out = call_anthropic("sys", "user", client=client, model="claude-opus-4-6")
    assert out == "hello world"
    assert client.calls[0]["model"] == "claude-opus-4-6"
    assert client.calls[0]["system"] == "sys"
    assert client.calls[0]["messages"] == [{"role": "user", "content": "user"}]


def test_call_anthropic_rejects_none_client():
    with pytest.raises(RuntimeError, match="client"):
        call_anthropic("sys", "user", client=None)


def test_call_anthropic_handles_dict_content_blocks():
    class DictClient:
        def __init__(self):
            self.messages = self
        def create(self, **_):
            # Simulate an SDK that yields dict blocks (older envelopes)
            class M:
                content = [{"type": "text", "text": "dict-block"}]
            return M()
    out = call_anthropic("s", "u", client=DictClient())
    assert out == "dict-block"


# ─── run_synthesis_worker ───


def test_run_synthesis_worker_happy_path():
    backend = InMemoryBackend()
    client = FakeAnthropicClient(response_text=_OPUS_RESPONSE)
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state=_state(),
        brief_backend=backend,
        client=client,
        now_fn=lambda: 1700000000,
    )
    assert result.processed is True
    assert result.brief is not None
    assert result.brief.top_picks == [148, 254, 1678, 2056]
    assert result.brief.our_team == 2950
    assert result.brief.generated_at == 1700000000
    assert backend.written["event_key"] == "2026txbel"
    assert backend.written["top_picks"] == [148, 254, 1678, 2056]
    # Anthropic client was called exactly once
    assert len(client.calls) == 1
    # Prompt includes data from state
    assert "#148" in client.calls[0]["messages"][0]["content"]


def test_run_synthesis_worker_dry_run_skips_api_call():
    backend = InMemoryBackend()
    client = FakeAnthropicClient(response_text="should not be called")
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state=_state(),
        brief_backend=backend,
        client=client,
        dry_run=True,
        now_fn=lambda: 1700000000,
    )
    assert result.processed is True
    assert result.dry_run is True
    assert result.brief is not None
    assert result.brief.dry_run is True
    assert "DRY_RUN" in result.brief.summary
    # FakeAnthropicClient was not used
    assert client.calls == []
    # Backend still got written
    assert backend.written is not None


def test_run_synthesis_worker_api_error_is_caught():
    backend = InMemoryBackend()
    client = FakeAnthropicClient(raise_on_call=True)
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state=_state(),
        brief_backend=backend,
        client=client,
    )
    assert result.processed is False
    assert len(result.errors) == 1
    assert "anthropic" in result.errors[0]
    assert backend.written is None  # never wrote


def test_run_synthesis_worker_empty_state_still_runs():
    backend = InMemoryBackend()
    client = FakeAnthropicClient(response_text=_OPUS_RESPONSE)
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state={},
        brief_backend=backend,
        client=client,
    )
    assert result.processed is True
    assert backend.written is not None
    # Prompt should still mention "no team data yet" fallback
    assert "no team data" in client.calls[0]["messages"][0]["content"]


def test_run_synthesis_worker_missing_top_picks_leaves_lists_empty():
    backend = InMemoryBackend()
    client = FakeAnthropicClient(
        response_text="Just a headline, no picks section.",
    )
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state=_state(),
        brief_backend=backend,
        client=client,
    )
    assert result.processed is True
    assert result.brief.top_picks == []
    assert result.brief.summary.startswith("Just a headline")


def test_run_synthesis_worker_backend_write_error():
    class ExplodingBackend:
        def write(self, _):
            raise RuntimeError("disk full")

    client = FakeAnthropicClient(response_text=_OPUS_RESPONSE)
    result = run_synthesis_worker(
        event_key="2026txbel",
        our_team=2950,
        state=_state(),
        brief_backend=ExplodingBackend(),
        client=client,
    )
    assert result.processed is False
    assert "brief_write" in result.errors[0]


# ─── BriefDocument / result serialization ───


def test_brief_document_to_dict_round_trip():
    b = BriefDocument(
        event_key="2026txbel",
        generated_at=1700000000,
        our_team=2950,
        model="claude-opus-4-6",
        summary="hello",
        top_picks=[148, 254],
        pick_rationale={"148": "best", "254": "second"},
        raw_response="hello",
    )
    d = b.to_dict()
    assert d["event_key"] == "2026txbel"
    assert d["top_picks"] == [148, 254]
    assert d["pick_rationale"] == {"148": "best", "254": "second"}
    assert d["dry_run"] is False


def test_result_to_dict_with_brief():
    b = BriefDocument(
        event_key="2026txbel", generated_at=1, our_team=2950,
        model="m", summary="s",
    )
    r = SynthesisWorkerResult(processed=True, brief=b, dry_run=False)
    d = r.to_dict()
    assert d["processed"] is True
    assert d["brief"]["event_key"] == "2026txbel"


def test_result_to_dict_without_brief():
    r = SynthesisWorkerResult(errors=["boom"])
    d = r.to_dict()
    assert d["brief"] is None
    assert d["errors"] == ["boom"]
