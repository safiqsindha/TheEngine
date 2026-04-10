# Engine Anthropic Proxy

A tiny FastAPI service that sits between student Codespaces and `api.anthropic.com`. It enforces a per-student daily and lifetime budget so the kids can experiment with the Engine without burning a hole in your wallet.

## What it does

- **Authenticates each request** via a fake API key shaped `<shared_token>:<github_user>`. The proxy parses out the username and validates the shared token.
- **Tracks spend per user** in SQLite. Every request's token usage is parsed (streaming or not) and converted to USD using current Anthropic pricing.
- **Enforces two limits** (configurable):
  - `$0.50` per day per student → returns `429` with a friendly message
  - `$5.00` lifetime per student → returns `402 OUT OF CREDITS`
- **Forwards** all requests to real Anthropic with the real API key, swapping in the proper `x-api-key` header.
- **Streaming-aware**: tees SSE chunks to the client while parsing `message_start` and `message_delta` events to extract token counts.

## Architecture

```
┌────────────────┐    fake key      ┌──────────────┐    real key   ┌──────────────────┐
│ Student        │  proxytoken:user │ Engine Proxy │   on Fly.io   │ api.anthropic.com │
│  Codespace     │ ───────────────► │  (FastAPI)   │ ────────────► │                  │
└────────────────┘                  └──────┬───────┘               └──────────────────┘
                                           │ records cost
                                           ▼
                                     SQLite spend.db
                                     (Fly volume)
```

## Files

| File | What it does |
|---|---|
| `proxy.py` | FastAPI app: `/v1/messages`, `/budget/{user}`, `/health` |
| `pricing.py` | USD-per-MTok rates for Haiku 4.5, Sonnet 4.5/4.6, Opus 4.5/4.6 |
| `storage.py` | SQLite spend tracker (one row per request) |
| `Dockerfile` | python:3.11-slim image |
| `fly.toml` | Fly.io deployment config (free tier sized) |
| `requirements.txt` | fastapi + uvicorn + httpx |

---

## Deploy to Fly.io

### One-time setup

```bash
brew install flyctl
fly auth login
cd engine_proxy
fly launch --no-deploy --copy-config --name engine-proxy
fly volumes create engine_proxy_data --size 1 --region ord
```

### Set the real Anthropic key + the shared proxy token as Fly secrets

```bash
# Generate a random shared token (this becomes the prefix of every student's fake key)
PROXY_TOKEN=$(openssl rand -hex 16)
echo "Shared token: $PROXY_TOKEN"

# Set on Fly
fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-api03-..." \
  PROXY_SHARED_TOKEN="$PROXY_TOKEN"

fly deploy
```

After deploy, note the URL Fly assigns (e.g. `https://engine-proxy.fly.dev`). You'll use it in the next step.

### Verify it's up

```bash
curl https://engine-proxy.fly.dev/health
# {"ok":true,"daily_limit":0.5,"total_limit":5.0}
```

---

## Configure GitHub org-level Codespaces secrets

Go to your GitHub org → **Settings → Codespaces → Secrets** and add the following secrets, **scoped to TheEngine repository** (or scoped to "All repositories" if you want every team repo to inherit them):

| Secret name | Value |
|---|---|
| `ANTHROPIC_PROXY_TOKEN` | the same `$PROXY_TOKEN` you set on Fly above |
| `ANTHROPIC_BASE_URL` | `https://engine-proxy.fly.dev` (your Fly URL, no trailing slash) |

When a student starts a Codespace, the devcontainer at `.devcontainer/devcontainer.json` reads these secrets and constructs:

```
ANTHROPIC_API_KEY = $ANTHROPIC_PROXY_TOKEN:$GITHUB_USER
ANTHROPIC_BASE_URL = $ANTHROPIC_BASE_URL
ENGINE_DEFAULT_MODEL = claude-haiku-4-5-20251001
```

The Anthropic Python SDK reads `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` automatically — **no Engine code changes are required**. Existing scripts (`engine_advisor.py`, etc.) Just Work, but every call now goes through the proxy and gets billed against the student's budget.

---

## How students see their budget

Inside any Codespace:

```bash
python3 engine_budget.py
```

Output:

```
  Engine API budget — alex-student
  ─────────────────────────────────────────────────────
  Today    [#######---------------------]  $0.1234 / $0.50
  Lifetime [###-------------------------]  $0.5612 / $5.00
  Requests 47
```

The script hits `GET /budget/{user}` on the proxy. No API call to Anthropic, no cost.

---

## What students see when they hit a limit

When a student exceeds their daily limit, the next Anthropic call raises:

```
anthropic.RateLimitError: DAILY LIMIT HIT: you've used your $0.50 for today
($0.5012 spent). Remaining lifetime budget: $4.49. Try again tomorrow.
```

When they hit the lifetime cap:

```
anthropic.PermissionDeniedError: OUT OF CREDITS: you've used all $5.00 of your
Engine budget ($5.0023 spent). Talk to your mentor to top up.
```

These errors come back in standard Anthropic error format so the SDK surfaces them as normal exceptions, not cryptic HTTP errors.

---

## Topping up a student

To reset or extend a student's budget, you have two options.

### Option A: just delete their rows

```bash
fly ssh console -C "sqlite3 /data/spend.db 'DELETE FROM spend WHERE user = \"alex-student\";'"
```

### Option B: raise the global lifetime cap

Edit `fly.toml`, bump `TOTAL_LIMIT_USD`, redeploy.

---

## Tuning

| Env var | Default | What it controls |
|---|---|---|
| `DAILY_LIMIT_USD` | `0.50` | Per-user per-calendar-day spend cap (UTC) |
| `TOTAL_LIMIT_USD` | `5.00` | Per-user lifetime spend cap |
| `DB_PATH` | `/data/spend.db` | SQLite path (must be on the persistent volume) |

Update via `fly secrets set` and re-deploy. No code changes needed.

---

## Cost reality check

At Haiku 4.5 rates ($1/$5 per MTok):

- A typical Engine Advisor query is ~2k input + 500 output tokens = `$0.0045`
- $0.50/day = ~110 advisor queries per student
- $5.00 lifetime = ~1,100 advisor queries per student

If a student switches to Sonnet 4.5/4.6 ($3/$15 per MTok), each query costs ~3x more, so they hit the limit faster. If they go Opus 4.6 ($15/$75), each query is ~15x more expensive — they'll burn $0.50 in ~7 queries. Encourage Haiku unless they're explicitly experimenting with the advisor escalation pattern.

---

## Threat model

This proxy is designed for high school students who are curious, not adversarial. Specifically:

- The shared token is **not** treated as cryptographic auth — kids can extract it from `$ANTHROPIC_API_KEY`. The token only blocks random internet traffic.
- A student who wants to spoof another student's username can do so. Worst case: they spend that other student's budget. We accept this.
- The proxy has no rate limiting beyond the spend cap. If a student writes a tight loop, they'll hit `$0.50` in seconds, then get blocked for the rest of the day.

If you need stricter isolation later, give each student a unique secret (rotate `PROXY_SHARED_TOKEN` per repo, store as a per-user Codespace secret).
