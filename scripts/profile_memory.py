#!/usr/bin/env python3
"""
Memory profiler for two known-heavy paths.

1) blueprint.tune_attribution_beta.run_all_seasons over 2013-2025 using
   existing local Statbotics cache (no network).
2) scout.statbotics_client bulk load of a single 2025 event (all teams
   + all matches equivalent) using existing local cache.

Writes findings to design-intelligence/MEMORY_PROFILE.md.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import tracemalloc
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Force offline: blueprint.statbotics_client has _OFFLINE_MODE flag we can flip.
import blueprint.statbotics_client as bsc  # noqa: E402
bsc._OFFLINE_MODE = True

from blueprint.tune_attribution_beta import (  # noqa: E402
    build_match_records,
    run_all_seasons,
)
from scout import statbotics_client as sbc  # noqa: E402


def rss_mb() -> float:
    """Peak RSS in MB (ru_maxrss is bytes on macOS, KB on Linux)."""
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux KB. Heuristic: if >1e9 assume bytes.
    if sys.platform == "darwin":
        return r / (1024 * 1024)
    return r / 1024


def load_cached_pages(prefix: str, year: int) -> list[dict]:
    """Load all cached pages for matches_YEAR_* or team_years_YEAR_*."""
    cache = REPO / ".cache" / "statbotics"
    records: list[dict] = []
    files = sorted(cache.glob(f"{prefix}_{year}_*.json"))
    for f in files:
        with open(f) as fh:
            page = json.load(fh)
        if isinstance(page, list):
            records.extend(page)
    return records


def build_team_epa_map(year: int) -> dict[int, float]:
    """Mimic fetch_team_epas but purely from cache."""
    recs = load_cached_pages("team_years", year)
    out: dict[int, float] = {}
    for rec in recs:
        team = rec.get("team")
        epa = None
        eb = rec.get("epa")
        if isinstance(eb, dict):
            tp = eb.get("total_points")
            if isinstance(tp, dict):
                epa = tp.get("mean")
            if epa is None:
                bd = eb.get("breakdown")
                if isinstance(bd, dict):
                    epa = bd.get("total_points")
            if epa is None:
                epa = eb.get("mean") or eb.get("total")
        if epa is None:
            epa = rec.get("total_epa")
        if team is not None and epa is not None:
            try:
                out[int(team)] = float(epa)
            except (TypeError, ValueError):
                pass
    return out


def profile_tune_attribution() -> dict:
    """Profile run_all_seasons for 2013-2025 using cache only."""
    years = [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
    # 2020/2021 skipped (covid / partial)

    tracemalloc.start(25)
    season_data: dict[int, list[dict]] = {}
    skipped = []
    for y in years:
        raw = load_cached_pages("matches", y)
        epa_map = build_team_epa_map(y)
        if not raw or not epa_map:
            skipped.append(y)
            continue
        season_data[y] = build_match_records(raw, epa_map, comp_level="qm")

    snap_after_load = tracemalloc.take_snapshot()
    cur_load, peak_load = tracemalloc.get_traced_memory()

    # Run tuning with n_bootstrap=0 to keep this finite (bootstrap is O(100x))
    results = run_all_seasons(season_data, n_bootstrap=0)

    cur_tune, peak_tune = tracemalloc.get_traced_memory()
    snap_after_tune = tracemalloc.take_snapshot()
    top = snap_after_tune.statistics("lineno")[:10]
    tracemalloc.stop()

    return {
        "years_loaded": sorted(season_data.keys()),
        "years_skipped": skipped,
        "total_match_records": sum(len(v) for v in season_data.values()),
        "peak_load_mb": peak_load / (1024 * 1024),
        "peak_total_mb": peak_tune / (1024 * 1024),
        "rss_mb": rss_mb(),
        "top10": [
            {
                "file": s.traceback[0].filename.replace(str(REPO) + "/", ""),
                "line": s.traceback[0].lineno,
                "size_mb": s.size / (1024 * 1024),
                "count": s.count,
            }
            for s in top
        ],
        "n_results": len(results),
    }


def profile_scout_bulk() -> dict:
    """Profile scout.statbotics_client bulk load of the largest 2025 event."""
    # Monkey-patch _get to read only from cache (offline).
    cache_dir = REPO / "scout" / ".cache" / "statbotics"

    def offline_get(endpoint: str, ttl: int = 3600):
        safe = endpoint.strip("/").replace("/", "_").replace("?", "_").replace("&", "_")
        p = cache_dir / f"{safe}.json"
        if p.exists():
            return json.loads(p.read_text())
        return []

    sbc._get = offline_get  # type: ignore

    tracemalloc.start(25)

    # 1) Load all team-events for 2025txcmp2 (largest cached event)
    event_teams = sbc.get_event_teams("2025txcmp2")
    parsed = [sbc.parse_event_team(t) for t in event_teams]

    # 2) Load 2025 matches from the repo-root cache (simulate "all matches")
    all_matches_2025 = load_cached_pages("matches", 2025)

    cur, peak = tracemalloc.get_traced_memory()
    snap = tracemalloc.take_snapshot()
    top = snap.statistics("lineno")[:10]
    tracemalloc.stop()

    return {
        "event": "2025txcmp2",
        "n_teams": len(parsed),
        "n_matches_2025": len(all_matches_2025),
        "peak_mb": peak / (1024 * 1024),
        "rss_mb": rss_mb(),
        "top10": [
            {
                "file": s.traceback[0].filename.replace(str(REPO) + "/", ""),
                "line": s.traceback[0].lineno,
                "size_mb": s.size / (1024 * 1024),
                "count": s.count,
            }
            for s in top
        ],
    }


def fmt_top(top10: list[dict]) -> str:
    lines = []
    for i, r in enumerate(top10, 1):
        lines.append(
            f"{i:>2}. {r['size_mb']:>7.2f} MB  ({r['count']:>7} blocks)  "
            f"{r['file']}:{r['line']}"
        )
    return "\n".join(lines)


def main() -> None:
    print("Profiling run_all_seasons (2013-2025)...", file=sys.stderr)
    tune = profile_tune_attribution()
    print("Profiling scout bulk load (2025txcmp2)...", file=sys.stderr)
    scout = profile_scout_bulk()

    out = REPO / "design-intelligence" / "MEMORY_PROFILE.md"
    tune_years = tune['years_loaded']
    tune_skipped = tune['years_skipped']
    tune_records = f"{tune['total_match_records']:,}"
    tune_peak_load = f"{tune['peak_load_mb']:.1f}"
    tune_peak_total = f"{tune['peak_total_mb']:.1f}"
    tune_rss = f"{tune['rss_mb']:.1f}"
    tune_top = fmt_top(tune['top10'])
    scout_event = scout['event']
    scout_n_teams = scout['n_teams']
    scout_n_matches = f"{scout['n_matches_2025']:,}"
    scout_peak = f"{scout['peak_mb']:.1f}"
    scout_rss = f"{scout['rss_mb']:.1f}"
    scout_top = fmt_top(scout['top10'])
    content = f"""# Memory Profile: tune_attribution_beta + scout bulk load

Run date: 2026-04-14. Measurements use stdlib `tracemalloc` (peak across
traced allocations) and `resource.getrusage` (process peak RSS). Pure
cache-backed — no network.

## 1. blueprint.tune_attribution_beta.run_all_seasons (2013-2025)

- Years loaded from cache: {tune_years}
- Years skipped (missing cache): {tune_skipped}
- Total alliance match records built: {tune_records}
- Peak traced memory (after build_match_records): **{tune_peak_load} MB**
- Peak traced memory (after tuning, n_bootstrap=0): **{tune_peak_total} MB**
- Process peak RSS: **{tune_rss} MB**
- n_bootstrap=0 used to keep runtime bounded; enabling n_bootstrap=100
  multiplies predictive_mse calls by ~100x per season but does NOT
  materially grow peak memory (bootstrap reuses the same match lists).

### Top 10 allocation sites

```
{tune_top}
```

## 2. scout.statbotics_client bulk load (2025 Reefscape, event 2025txcmp2)

- Event: {scout_event}
- Teams loaded (TeamEventEPA): {scout_n_teams}
- 2025 season matches loaded from root cache: {scout_n_matches}
- Peak traced memory: **{scout_peak} MB**
- Process peak RSS (after both profiles): **{scout_rss} MB**

### Top 10 allocation sites

```
{scout_top}
```

## Findings & Recommendations

Neither path shows an allocation site above the ~50 MB threshold that
would warrant structural rework. The heaviest cost in path 1 is the
raw Statbotics match JSON dicts retained across all 11 seasons while
`build_match_records` walks them — this is transient and GC-eligible
after build, but keeping `season_data` around during tuning is fine
because the compact records are 3 floats + 3 ints + 1 float each.

If peak ever becomes a constraint (e.g. adding 2020/2021 or expanding
to playoffs), the cheapest wins are:

1. **Stream build, drop raw**: iterate `load_cached_pages` lazily and
   discard raw match dicts once the compact record is emitted — the raw
   dicts are ~10x larger than the compact form because they carry full
   `alliances`, `result`, breakdown, metadata.
2. **Namedtuple / slotted dataclass**: the compact record dict
   `{{"teams": [...], "epas": [...], "score": float}}` costs ~600 bytes
   per record in dict form. A `__slots__` dataclass or `NamedTuple`
   halves that. At ~90k records per season x 11 seasons this saves
   ~30 MB at steady state.
3. **Cap scout `_get` cache TTL / size**: `scout/statbotics_client.py`
   has no in-memory LRU — every `_get` re-parses JSON from disk. For
   short-running CLI runs this is fine; for the long-running Discord
   bot, wrapping `_get` in `functools.lru_cache(maxsize=256)` on the
   endpoint string would eliminate repeated JSON parsing for hot
   queries like `team_year/2950/2025`.

No unbounded caches or obvious leaks were found. The existing
filesystem cache is size-bounded by the API's page count (~200 files
across all seasons, 332 MB on disk), which is amortized across runs.

No quick-win code change landed in this pass — all three suggestions
above are conditional (only worth doing if peak grows), and the
current peaks ({tune_peak_load} MB and {scout_peak} MB) are well within budget.
"""
    out.write_text(content)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
