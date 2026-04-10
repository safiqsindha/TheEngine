"""Anthropic API proxy for The Engine.

Sits between student Codespaces and api.anthropic.com. Each student is
identified by their GitHub username (encoded in their API key as
"<shared_token>:<github_user>"). Spend is tracked per user in SQLite.

Limits (configurable via env):
  DAILY_LIMIT_USD = 0.25
  TOTAL_LIMIT_USD = 2.00

Required environment:
  ANTHROPIC_API_KEY      — the REAL Anthropic key (server-side only)
  PROXY_SHARED_TOKEN     — shared secret students' fake keys must include
  DB_PATH                — path to SQLite file (default /data/spend.db)

Endpoints:
  POST /v1/messages      — proxied messages endpoint (streaming + non-streaming)
  GET  /budget/{user}    — JSON view of one user's spend
  GET  /budget           — JSON view of all users (admin diagnostic)
  GET  /health           — liveness probe
"""

import json
import os
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from pricing import calculate_cost
from storage import Storage

# ─── Configuration ────────────────────────────────────────────────────────────

ANTHROPIC_BASE = "https://api.anthropic.com"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PROXY_SHARED_TOKEN = os.environ.get("PROXY_SHARED_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "/data/spend.db")

DAILY_LIMIT_USD = float(os.environ.get("DAILY_LIMIT_USD", "0.25"))
TOTAL_LIMIT_USD = float(os.environ.get("TOTAL_LIMIT_USD", "2.00"))

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY env var is required (the real key)")
if not PROXY_SHARED_TOKEN:
    raise RuntimeError("PROXY_SHARED_TOKEN env var is required")

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Engine Proxy")
storage = Storage(DB_PATH)
client = httpx.AsyncClient(base_url=ANTHROPIC_BASE, timeout=httpx.Timeout(300.0))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def parse_user(api_key: str) -> str:
    """Parse the student's fake api key into a (token, user) pair and validate.

    Format: "<PROXY_SHARED_TOKEN>:<github_username>"
    """
    parts = api_key.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(
            status_code=401,
            detail=_anthropic_error(
                "authentication_error",
                "Invalid API key format. Expected '<token>:<user>'.",
            ),
        )
    token, user = parts
    if token != PROXY_SHARED_TOKEN:
        raise HTTPException(
            status_code=401,
            detail=_anthropic_error(
                "authentication_error",
                "Proxy token mismatch. Re-create your codespace.",
            ),
        )
    return user.strip().lower()


def _anthropic_error(error_type: str, message: str) -> dict:
    """Build an error body the Anthropic SDK will surface as a normal exception."""
    return {"type": "error", "error": {"type": error_type, "message": message}}


def check_budget(user: str) -> None:
    """Raise HTTPException if the user is over either limit."""
    total = storage.get_total_spend(user)
    if total >= TOTAL_LIMIT_USD:
        raise HTTPException(
            status_code=402,
            detail=_anthropic_error(
                "permission_error",
                (
                    f"OUT OF CREDITS: you've used all ${TOTAL_LIMIT_USD:.2f} of your "
                    f"Engine budget (${total:.2f} spent). Talk to your mentor to top up."
                ),
            ),
        )

    daily = storage.get_daily_spend(user)
    if daily >= DAILY_LIMIT_USD:
        remaining_total = TOTAL_LIMIT_USD - total
        raise HTTPException(
            status_code=429,
            detail=_anthropic_error(
                "rate_limit_error",
                (
                    f"DAILY LIMIT HIT: you've used your ${DAILY_LIMIT_USD:.2f} for today "
                    f"(${daily:.4f} spent). Remaining lifetime budget: ${remaining_total:.2f}. "
                    f"Try again tomorrow."
                ),
            ),
        )


def _build_upstream_headers(request: Request) -> dict:
    """Forward only the Anthropic-relevant headers, swapping in the real key."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
        "content-type": "application/json",
    }
    if "anthropic-beta" in request.headers:
        headers["anthropic-beta"] = request.headers["anthropic-beta"]
    return headers


# ─── Routes ───────────────────────────────────────────────────────────────────


@app.post("/v1/messages")
async def messages(request: Request):
    api_key = request.headers.get("x-api-key", "")
    user = parse_user(api_key)
    check_budget(user)

    body = await request.body()
    try:
        body_json = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail=_anthropic_error("invalid_request_error", "Body is not valid JSON"),
        )

    model = body_json.get("model", "unknown")
    is_streaming = bool(body_json.get("stream", False))
    headers = _build_upstream_headers(request)

    if not is_streaming:
        return await _proxy_nonstreaming(user, model, body, headers)

    return StreamingResponse(
        _proxy_streaming(user, model, body, headers),
        media_type="text/event-stream",
    )


async def _proxy_nonstreaming(
    user: str, model: str, body: bytes, headers: dict
) -> JSONResponse:
    """Forward a non-streaming request, record spend on success."""
    try:
        resp = await client.post("/v1/messages", content=body, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=_anthropic_error("api_error", f"Upstream Anthropic error: {exc}"),
        )

    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})
        cost = calculate_cost(
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        )
        storage.record(
            user=user,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cost_usd=cost,
        )
        return JSONResponse(content=data)

    # Non-200 from upstream — surface the body verbatim
    try:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=resp.status_code,
            content=_anthropic_error("api_error", resp.text[:500]),
        )


async def _proxy_streaming(
    user: str, model: str, body: bytes, headers: dict
) -> AsyncIterator[bytes]:
    """Forward an SSE stream while accumulating token counts.

    Anthropic streams emit `message_start` (with input usage) and `message_delta`
    (with output usage). We tee the stream to the client and parse usage from
    the events as they pass through. After the stream completes, we record spend.
    """
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    buffer = ""

    try:
        async with client.stream(
            "POST", "/v1/messages", content=body, headers=headers
        ) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                yield err_body
                return

            async for chunk in resp.aiter_bytes():
                yield chunk
                # SSE arrives as text — accumulate and parse line-by-line
                try:
                    buffer += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    _accumulate_usage(evt, usage)
    finally:
        # Record spend even on partial streams; we charge for what we got back.
        cost = calculate_cost(
            model=model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_creation_tokens=usage["cache_creation_input_tokens"],
            cache_read_tokens=usage["cache_read_input_tokens"],
        )
        if cost > 0:
            storage.record(
                user=user,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_creation_tokens=usage["cache_creation_input_tokens"],
                cache_read_tokens=usage["cache_read_input_tokens"],
                cost_usd=cost,
            )


def _accumulate_usage(event: dict, usage: dict) -> None:
    """Pull token counts out of message_start / message_delta events."""
    etype = event.get("type")
    if etype == "message_start":
        msg_usage = event.get("message", {}).get("usage", {})
        for key in usage:
            if key in msg_usage:
                usage[key] = msg_usage[key]
    elif etype == "message_delta":
        delta_usage = event.get("usage", {})
        if "output_tokens" in delta_usage:
            usage["output_tokens"] = delta_usage["output_tokens"]


@app.get("/budget/{user}")
def get_budget(user: str):
    user = user.strip().lower()
    daily = storage.get_daily_spend(user)
    total = storage.get_total_spend(user)
    return {
        "user": user,
        "daily_spent_usd": round(daily, 6),
        "daily_limit_usd": DAILY_LIMIT_USD,
        "daily_remaining_usd": round(max(0.0, DAILY_LIMIT_USD - daily), 6),
        "total_spent_usd": round(total, 6),
        "total_limit_usd": TOTAL_LIMIT_USD,
        "total_remaining_usd": round(max(0.0, TOTAL_LIMIT_USD - total), 6),
        "out_of_credits": total >= TOTAL_LIMIT_USD,
        "daily_limit_hit": daily >= DAILY_LIMIT_USD,
        "request_count": storage.get_request_count(user),
    }


@app.get("/health")
def health():
    return {"ok": True, "daily_limit": DAILY_LIMIT_USD, "total_limit": TOTAL_LIMIT_USD}
