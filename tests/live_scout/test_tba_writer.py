"""Tests for scout/tba_writer.py — Phase 2 U2.

Fully hermetic: no `requests` import, HTTP transport is always injected.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from tba_writer import (  # noqa: E402
    TBA_ADD_MATCH_VIDEOS_PATH,
    TBA_BASE_URL,
    TbaWriteResponse,
    TbaWriter,
    _is_already_exists,
    sign_request,
)


# ─── Fake HTTP transport ───


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class FakeTransport:
    """Records every POST and returns a scripted sequence of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []  # list of (url, data, headers, timeout)

    def post(self, url, *, data, headers, timeout):
        self.calls.append({
            "url": url,
            "data": data,
            "headers": dict(headers),
            "timeout": timeout,
        })
        if not self._responses:
            return FakeResponse(500, "no more scripted responses")
        return self._responses.pop(0)


class ExplodingTransport:
    def __init__(self):
        self.calls = 0

    def post(self, url, *, data, headers, timeout):
        self.calls += 1
        raise ConnectionError(f"boom #{self.calls}")


def _writer(http=None, *, dry_run=False, auth_secret="SECRET", **kw):
    sleeps = []
    w = TbaWriter(
        auth_id="2950",
        auth_secret=auth_secret,
        dry_run=dry_run,
        http=http,
        sleep=lambda s: sleeps.append(s),
        max_retries=3,
        backoff_base_s=0.01,
        **kw,
    )
    return w, sleeps


# ─── sign_request ───


def test_sign_request_matches_tba_spec():
    """Regression: the signature is md5(secret + path + body) hex."""
    secret = "hunter2"
    path = "/api/trusted/v1/event/2026txbel/match_videos/add"
    body = '{"qm32":"abc"}'
    expected = hashlib.md5((secret + path + body).encode("utf-8")).hexdigest()
    assert sign_request(secret, path, body) == expected


def test_sign_request_rejects_empty_secret():
    with pytest.raises(ValueError, match="auth_secret"):
        sign_request("", "/x", "{}")


def test_sign_request_rejects_path_without_slash():
    with pytest.raises(ValueError, match="request_path"):
        sign_request("s", "api/trusted/v1/x", "{}")


# ─── _is_already_exists ───


def test_is_already_exists_true_for_400_with_already():
    assert _is_already_exists(400, "Video already exists for this match") is True


def test_is_already_exists_true_for_400_with_exist():
    assert _is_already_exists(400, "Match video link existing") is True


def test_is_already_exists_false_for_other_status():
    assert _is_already_exists(500, "already exists") is False


def test_is_already_exists_false_for_400_without_keyword():
    assert _is_already_exists(400, "Invalid JSON body") is False


# ─── TbaWriter construction ───


def test_writer_rejects_empty_auth_id():
    with pytest.raises(ValueError, match="auth_id"):
        TbaWriter(auth_id="", auth_secret="s")


def test_writer_rejects_empty_secret_in_non_dry_run():
    with pytest.raises(ValueError, match="auth_secret"):
        TbaWriter(auth_id="2950", auth_secret="", dry_run=False)


def test_writer_allows_empty_secret_in_dry_run():
    w = TbaWriter(auth_id="2950", auth_secret="", dry_run=True)
    assert w.dry_run is True


# ─── add_match_video: input validation ───


def test_add_match_video_rejects_missing_fields():
    w, _ = _writer(FakeTransport([]))
    resp = w.add_match_video(event_key="", match_key="2026txbel_qm1", video_key="vid")
    assert resp.status == "error:missing_field"
    assert not resp.ok


def test_add_match_video_rejects_event_mismatch():
    w, _ = _writer(FakeTransport([]))
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txdri_qm1",  # wrong event prefix
        video_key="vid",
    )
    assert resp.status == "error:match_key_event_mismatch"


# ─── add_match_video: happy path ───


def test_add_match_video_happy_path_sends_signed_request():
    http = FakeTransport([FakeResponse(200, "ok")])
    w, _ = _writer(http)

    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="WpzeaX1vgeQ",
    )
    assert resp.ok
    assert resp.status == "ok"
    assert resp.http_status == 200
    assert resp.attempts == 1

    assert len(http.calls) == 1
    call = http.calls[0]
    expected_path = TBA_ADD_MATCH_VIDEOS_PATH.format(event_key="2026txbel")
    assert call["url"] == f"{TBA_BASE_URL}{expected_path}"

    # Body shape
    body = json.loads(call["data"].decode("utf-8"))
    assert body == {"qm32": "WpzeaX1vgeQ"}

    # Headers include auth + signed sig
    assert call["headers"]["X-TBA-Auth-Id"] == "2950"
    expected_sig = sign_request("SECRET", expected_path, call["data"].decode("utf-8"))
    assert call["headers"]["X-TBA-Auth-Sig"] == expected_sig
    assert call["headers"]["Content-Type"] == "application/json"


def test_add_match_video_playoff_match_key_shortens_correctly():
    http = FakeTransport([FakeResponse(200, "ok")])
    w, _ = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qf1m1",
        video_key="abc",
    )
    assert resp.ok
    body = json.loads(http.calls[0]["data"].decode("utf-8"))
    assert body == {"qf1m1": "abc"}


# ─── add_match_video: already-exists idempotency ───


def test_add_match_video_already_exists_is_success():
    http = FakeTransport([FakeResponse(400, "Match video already exists")])
    w, _ = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.ok
    assert resp.status == "already_exists"
    assert resp.attempts == 1


# ─── add_match_video: retry logic ───


def test_add_match_video_retries_on_5xx_then_succeeds():
    http = FakeTransport([
        FakeResponse(503, "Service Unavailable"),
        FakeResponse(502, "Bad Gateway"),
        FakeResponse(200, "ok"),
    ])
    w, sleeps = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.ok
    assert resp.attempts == 3
    # Exponential backoff: base, base*2
    assert len(sleeps) == 2
    assert sleeps[0] < sleeps[1]


def test_add_match_video_does_not_retry_on_400_non_already_exists():
    http = FakeTransport([
        FakeResponse(400, "Invalid body"),
        FakeResponse(200, "ok"),  # should never get here
    ])
    w, sleeps = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.status == "error:http_400"
    assert resp.attempts == 1
    assert len(http.calls) == 1
    assert sleeps == []


def test_add_match_video_gives_up_after_max_retries_on_5xx():
    http = FakeTransport([
        FakeResponse(503, "no"),
        FakeResponse(503, "still no"),
        FakeResponse(503, "very no"),
    ])
    w, sleeps = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.status == "error:http_503"
    assert resp.attempts == 3
    # max_retries=3 means 2 sleeps between the 3 attempts
    assert len(sleeps) == 2


def test_add_match_video_retries_on_transport_exception():
    http = ExplodingTransport()
    w, sleeps = _writer(http)
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.status.startswith("error:transport_exception")
    assert resp.attempts == 3
    assert http.calls == 3


# ─── dry run ───


def test_dry_run_never_calls_http():
    http = FakeTransport([])
    w, _ = _writer(http, dry_run=True, auth_secret="")
    resp = w.add_match_video(
        event_key="2026txbel",
        match_key="2026txbel_qm32",
        video_key="abc",
    )
    assert resp.ok
    assert resp.status == "ok"
    assert resp.dry_run is True
    assert http.calls == []
    assert "DRY_RUN" in resp.body


# ─── Response helper ───


def test_response_to_dict_round_trip():
    r = TbaWriteResponse(
        status="already_exists", http_status=400, body="exists",
        attempts=1, dry_run=False,
    )
    d = r.to_dict()
    assert d["status"] == "already_exists"
    assert d["attempts"] == 1
    assert r.ok is True
