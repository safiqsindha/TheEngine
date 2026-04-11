#!/usr/bin/env python3
"""
The Engine — Live Scout TBA Trusted v1 Writer (Phase 2 U2)
Team 2950 — The Devastators

Thin client over The Blue Alliance's Trusted v1 POST API used by the
TBA uploader worker (Phase 2 U3) to attach YouTube video keys to
match records.

TBA Trusted v1 signing (https://www.thebluealliance.com/apidocs/trusted/v1):
    X-TBA-Auth-Id:  <auth_id>
    X-TBA-Auth-Sig: md5(auth_secret + request_path + request_body)

`request_path` is the URL path only (no host, no querystring).
`request_body` is the raw JSON string as it will be sent.

Design notes:
  - `requests` is a lazy import so this module is import-safe in test
    environments that don't install it. The HTTP transport is also
    injectable for hermetic tests — pass `http=FakeTransport()` to
    `TbaWriter` and it will call that instead of `requests.post`.
  - Idempotency: TBA returns HTTP 400 with a "already exists" message
    when the match video has already been posted. The writer treats
    that as success, so re-runs of the uploader cron are cheap and safe.
  - Retries: exponential backoff on 5xx up to `max_retries`. 4xx is
    never retried (auth failures, validation errors).
  - Dry run: construct with `dry_run=True` and the writer logs what it
    would have sent but never touches the network. U3 uses this for
    the TBA_UPLOADER_DRY_RUN env guard.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md Phase 2 §U2.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


TBA_BASE_URL = "https://www.thebluealliance.com"
TBA_ADD_MATCH_VIDEOS_PATH = "/api/trusted/v1/event/{event_key}/match_videos/add"
DEFAULT_TIMEOUT_S = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 1.0


# ─── Response types ───


@dataclass
class TbaWriteResponse:
    """Result of one POST to TBA Trusted v1."""

    status: str                              # "ok" | "already_exists" | "error:<detail>"
    http_status: int = 0
    body: str = ""                           # raw TBA response body for debugging
    attempts: int = 0                        # number of HTTP attempts made
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "already_exists"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "http_status": int(self.http_status),
            "body": self.body,
            "attempts": int(self.attempts),
            "dry_run": bool(self.dry_run),
        }


# ─── HTTP transport protocol ───


class HttpTransport(Protocol):
    """The subset of `requests.post` we actually use.

    Tests inject a fake transport; production uses the default which
    lazy-imports `requests`.
    """

    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> "HttpResponse":
        ...


class HttpResponse(Protocol):
    status_code: int
    text: str


def _default_transport() -> HttpTransport:
    """Lazy-import `requests` and wrap it in the transport shape."""
    import requests  # lazy: tests never import requests

    class _RequestsTransport:
        def post(self, url: str, *, data: bytes, headers: dict[str, str], timeout: float):
            return requests.post(url, data=data, headers=headers, timeout=timeout)

    return _RequestsTransport()


# ─── Signing ───


def sign_request(auth_secret: str, request_path: str, request_body: str) -> str:
    """Compute the TBA Trusted v1 X-TBA-Auth-Sig.

    Per the TBA docs, the signature is the MD5 of the concatenation:
        md5(auth_secret + request_path + request_body)
    rendered as a lowercase hex string.
    """
    if not auth_secret:
        raise ValueError("sign_request requires a non-empty auth_secret")
    if not request_path.startswith("/"):
        raise ValueError(f"request_path must start with /, got {request_path!r}")
    payload = (auth_secret + request_path + request_body).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


# ─── Writer ───


def _is_already_exists(http_status: int, body: str) -> bool:
    """TBA returns HTTP 400 + a message body when the video is already linked.
    We treat that as a successful no-op. The exact phrasing varies a bit
    across TBA versions, so we pattern match loosely.
    """
    if http_status != 400:
        return False
    lowered = body.lower()
    return "already" in lowered or "exist" in lowered


class TbaWriter:
    """POST one or more match videos to TBA Trusted v1.

    Example:
        writer = TbaWriter(auth_id="2950", auth_secret=os.environ["TBA_TRUSTED_AUTH_SECRET"])
        resp = writer.add_match_video(
            event_key="2026txbel",
            match_key="2026txbel_qm32",
            video_key="WpzeaX1vgeQ",
        )
        if not resp.ok:
            print("failed:", resp.status, resp.body)
    """

    def __init__(
        self,
        *,
        auth_id: str,
        auth_secret: str,
        dry_run: bool = False,
        http: Optional[HttpTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        base_url: str = TBA_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not auth_id:
            raise ValueError("TbaWriter requires a non-empty auth_id")
        if not auth_secret and not dry_run:
            raise ValueError(
                "TbaWriter requires an auth_secret unless dry_run=True"
            )
        self._auth_id = auth_id
        self._auth_secret = auth_secret
        self._dry_run = dry_run
        self._http = http
        self._sleep = sleep
        self._max_retries = max(1, int(max_retries))
        self._backoff_base_s = float(backoff_base_s)
        self._base_url = base_url.rstrip("/")
        self._timeout_s = float(timeout_s)

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    # ─── Primitive ───

    def _post_signed(self, path: str, body: dict[str, Any]) -> TbaWriteResponse:
        """POST a JSON body to TBA with a signed header set. Retries on 5xx."""
        body_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
        headers = {
            "Content-Type": "application/json",
            "X-TBA-Auth-Id": self._auth_id,
            "X-TBA-Auth-Sig": sign_request(self._auth_secret, path, body_json) if self._auth_secret else "",
        }
        url = f"{self._base_url}{path}"

        if self._dry_run:
            return TbaWriteResponse(
                status="ok",
                http_status=0,
                body=f"DRY_RUN: {url} {body_json}",
                attempts=0,
                dry_run=True,
            )

        if self._http is None:
            try:
                self._http = _default_transport()
            except ImportError:
                return TbaWriteResponse(
                    status="error:no_http_transport",
                    body="requests not installed and no http transport injected",
                )

        last_status = 0
        last_body = ""
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._http.post(
                    url,
                    data=body_json.encode("utf-8"),
                    headers=headers,
                    timeout=self._timeout_s,
                )
            except Exception as e:
                last_status = 0
                last_body = f"transport_exception:{e}"
                if attempt < self._max_retries:
                    self._sleep(self._backoff_base_s * (2 ** (attempt - 1)))
                    continue
                return TbaWriteResponse(
                    status=f"error:{last_body}",
                    http_status=0,
                    body=last_body,
                    attempts=attempt,
                )

            last_status = int(getattr(resp, "status_code", 0))
            last_body = str(getattr(resp, "text", "") or "")

            if 200 <= last_status < 300:
                return TbaWriteResponse(
                    status="ok",
                    http_status=last_status,
                    body=last_body,
                    attempts=attempt,
                )

            if _is_already_exists(last_status, last_body):
                return TbaWriteResponse(
                    status="already_exists",
                    http_status=last_status,
                    body=last_body,
                    attempts=attempt,
                )

            # 4xx other than "already exists" — don't retry, the caller has
            # to fix the input.
            if 400 <= last_status < 500:
                return TbaWriteResponse(
                    status=f"error:http_{last_status}",
                    http_status=last_status,
                    body=last_body,
                    attempts=attempt,
                )

            # 5xx — retry with backoff
            if attempt < self._max_retries:
                self._sleep(self._backoff_base_s * (2 ** (attempt - 1)))

        return TbaWriteResponse(
            status=f"error:http_{last_status}",
            http_status=last_status,
            body=last_body,
            attempts=self._max_retries,
        )

    # ─── Public API ───

    def add_match_video(
        self,
        *,
        event_key: str,
        match_key: str,
        video_key: str,
    ) -> TbaWriteResponse:
        """POST one match video link to TBA.

        TBA's endpoint expects:
            POST /api/trusted/v1/event/{event_key}/match_videos/add
            body: { "<match_key_short>": "<youtube_key>" }

        where `match_key_short` is the match_key with the event prefix
        stripped (e.g. `qm32` for `2026txbel_qm32`).
        """
        if not event_key or not match_key or not video_key:
            return TbaWriteResponse(
                status="error:missing_field",
                body=f"event_key={event_key!r} match_key={match_key!r} video_key={video_key!r}",
            )
        if not match_key.startswith(f"{event_key}_"):
            return TbaWriteResponse(
                status="error:match_key_event_mismatch",
                body=f"match_key {match_key!r} does not start with {event_key}_",
            )
        short = match_key[len(event_key) + 1 :]
        path = TBA_ADD_MATCH_VIDEOS_PATH.format(event_key=event_key)
        return self._post_signed(path, {short: video_key})
