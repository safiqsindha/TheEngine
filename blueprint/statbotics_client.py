"""
blueprint/statbotics_client.py
--------------------------------
Bulk Statbotics API client for β-tuning data pulls.

Uses two endpoints per season:
  - /v3/matches/year/{year}   → all matches (qual + playoff), paginated at 1000/page
  - /v3/team_years/{year}     → all team EPA records for a year, paginated at 1000/page

Caches responses to .cache/statbotics/{endpoint}_{year}_{offset}.json.
Rate-limited to 2 req/sec to stay within Statbotics free tier.

DO NOT use /v3/team_matches — that's per-team pagination which would require
thousands of calls instead of ~100-200 across 13 seasons.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

BASE_URL = "https://api.statbotics.io"
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "statbotics"
RATE_LIMIT_DELAY = 0.5  # seconds between requests (2 req/sec max)

# Set to True in tests to prevent any network calls
_OFFLINE_MODE = False


def _cache_path(endpoint: str, year: int, offset: int) -> Path:
    """Return the filesystem path for a cached response."""
    safe_endpoint = endpoint.replace("/", "_").strip("_")
    return CACHE_DIR / f"{safe_endpoint}_{year}_{offset}.json"


def _load_cache(endpoint: str, year: int, offset: int) -> Optional[list[dict]]:
    """Return cached data if it exists, else None."""
    p = _cache_path(endpoint, year, offset)
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_cache(endpoint: str, year: int, offset: int, data: list[dict]) -> None:
    """Write data to the filesystem cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(endpoint, year, offset)
    with open(p, "w") as f:
        json.dump(data, f)


def _fetch_page(url: str) -> list[dict]:
    """
    Fetch a single page from the Statbotics API.
    Returns parsed JSON list (empty list on 404 or empty body).
    Raises RuntimeError on network/HTTP errors.
    """
    if _OFFLINE_MODE:
        raise RuntimeError("Network calls disabled in offline/test mode.")

    req = Request(url, headers={"User-Agent": "TheEngine-BetaTuner/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            if isinstance(data, list):
                return data
            # Some endpoints return a dict with a "data" key
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
    except HTTPError as e:
        if e.code == 404:
            return []
        raise RuntimeError(f"HTTP {e.code} fetching {url}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e}") from e


def _fetch_all_pages(
    endpoint: str,
    year: int,
    limit: int = 1000,
    extra_params: str = "",
) -> list[dict]:
    """
    Paginate through all records for an endpoint/year combination.
    Uses filesystem cache; only calls the network for uncached pages.

    Parameters
    ----------
    endpoint    : e.g. "matches" or "team_years"
    year        : FRC season year
    limit       : records per page (max Statbotics allows)
    extra_params: additional query string parameters (without leading &)

    Returns
    -------
    Flat list of all records across all pages.
    """
    all_records: list[dict] = []
    offset = 0

    while True:
        # Check cache first
        cached = _load_cache(endpoint, year, offset)
        if cached is not None:
            page_data = cached
        else:
            url = (
                f"{BASE_URL}/v3/{endpoint}?year={year}"
                f"&limit={limit}&offset={offset}"
            )
            if extra_params:
                url += f"&{extra_params}"
            page_data = _fetch_page(url)
            _save_cache(endpoint, year, offset, page_data)
            # Rate-limit only after actual network calls
            time.sleep(RATE_LIMIT_DELAY)

        all_records.extend(page_data)

        # If we got fewer records than the limit, we've hit the last page
        if len(page_data) < limit:
            break

        offset += limit

    return all_records


def fetch_season_matches(year: int) -> list[dict]:
    """
    Fetch all matches for a season from Statbotics.

    Returns a list of match dicts. Each match has (among others):
      - key          : str  e.g. "2025txhou_qm1"
      - comp_level   : str  e.g. "qm", "sf", "f"
      - red_1, red_2, red_3 : int  team numbers
      - blue_1, blue_2, blue_3 : int
      - red_score    : int  actual red alliance score
      - blue_score   : int  actual blue alliance score
      - red_epa_sum  : float  (if available)
      - blue_epa_sum : float

    Only qual matches ("comp_level" == "qm") are used for β tuning;
    filtering is done downstream in the objective function.
    """
    return _fetch_all_pages("matches", year)


def fetch_team_epas(year: int) -> dict[int, float]:
    """
    Fetch all teams' season EPA for a year, return as {team_number: epa}.

    Uses /v3/team_years/{year} endpoint via pagination.
    The returned dict covers every team that competed that year.
    """
    records = _fetch_all_pages("team_years", year)
    epa_map: dict[int, float] = {}
    for rec in records:
        team = rec.get("team")
        # Statbotics v3 nested EPA structure:
        #   epa.total_points.mean  — primary (preferred)
        #   epa.breakdown.total_points — fallback
        #   epa.mean / epa.total   — older API versions
        #   total_epa              — flat legacy field
        epa = None
        epa_block = rec.get("epa")
        if isinstance(epa_block, dict):
            # v3 structure: epa.total_points.mean
            tp = epa_block.get("total_points")
            if isinstance(tp, dict):
                epa = tp.get("mean")
            # fallback: epa.breakdown.total_points
            if epa is None:
                bd = epa_block.get("breakdown")
                if isinstance(bd, dict):
                    epa = bd.get("total_points")
            # fallback: older flat fields
            if epa is None:
                epa = epa_block.get("mean") or epa_block.get("total")
        if epa is None:
            epa = rec.get("total_epa")
        if team is not None and epa is not None:
            try:
                epa_map[int(team)] = float(epa)
            except (TypeError, ValueError):
                pass
    return epa_map


def cache_size_bytes() -> int:
    """Return total bytes in the Statbotics cache directory."""
    total = 0
    if CACHE_DIR.exists():
        for p in CACHE_DIR.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


def api_call_count() -> int:
    """Return number of cache files (each represents one API call or cache hit)."""
    if not CACHE_DIR.exists():
        return 0
    return sum(1 for p in CACHE_DIR.rglob("*.json") if p.is_file())
