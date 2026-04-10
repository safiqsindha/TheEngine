#!/usr/bin/env python3
"""Show the current student's Engine API budget.

Reads ENGINE_PROXY_URL and ENGINE_USER from the environment (set by the
Codespace devcontainer) and prints daily / total spend with a visual bar.
"""

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import json


def _bar(used: float, total: float, width: int = 28) -> str:
    if total <= 0:
        return "[" + " " * width + "]"
    pct = min(1.0, used / total)
    filled = int(round(width * pct))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> int:
    proxy_url = os.environ.get("ENGINE_PROXY_URL", "").rstrip("/")
    user = os.environ.get("ENGINE_USER") or os.environ.get("GITHUB_USER") or ""

    if not proxy_url or not user:
        print(
            "Could not find ENGINE_PROXY_URL or ENGINE_USER in environment.\n"
            "This script is meant to run inside a Codespace devcontainer.",
            file=sys.stderr,
        )
        return 1

    url = f"{proxy_url}/budget/{user}"
    try:
        with urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        print(f"Proxy returned HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 1
    except URLError as e:
        print(f"Could not reach proxy at {proxy_url}: {e.reason}", file=sys.stderr)
        return 1

    daily_used = data["daily_spent_usd"]
    daily_limit = data["daily_limit_usd"]
    total_used = data["total_spent_usd"]
    total_limit = data["total_limit_usd"]
    requests = data["request_count"]

    print()
    print(f"  Engine API budget — {user}")
    print(f"  ─────────────────────────────────────────────────────")
    print(
        f"  Today    {_bar(daily_used, daily_limit)} "
        f"${daily_used:.4f} / ${daily_limit:.2f}"
    )
    print(
        f"  Lifetime {_bar(total_used, total_limit)} "
        f"${total_used:.4f} / ${total_limit:.2f}"
    )
    print(f"  Requests {requests}")
    print()

    if data["out_of_credits"]:
        print("  ⚠ OUT OF CREDITS — talk to your mentor to top up.")
    elif data["daily_limit_hit"]:
        print("  ⚠ Daily limit hit — try again tomorrow.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
