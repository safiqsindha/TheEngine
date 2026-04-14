# Memory Profile: tune_attribution_beta + scout bulk load

Run date: 2026-04-14. Measurements use stdlib `tracemalloc` (peak across
traced allocations) and `resource.getrusage` (process peak RSS). Pure
cache-backed — no network.

## 1. blueprint.tune_attribution_beta.run_all_seasons (2013-2025)

- Years loaded from cache: [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
- Years skipped (missing cache): []
- Total alliance match records built: 246,708
- Peak traced memory (after build_match_records): **332.7 MB**
- Peak traced memory (after tuning, n_bootstrap=0): **332.7 MB**
- Process peak RSS: **1741.0 MB**
- n_bootstrap=0 used to keep runtime bounded; enabling n_bootstrap=100
  multiplies predictive_mse calls by ~100x per season but does NOT
  materially grow peak memory (bootstrap reuses the same match lists).

### Top 10 allocation sites

```
 1.  139.90 MB  (2331506 blocks)  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/decoder.py:353
 2.   56.48 MB  ( 492622 blocks)  blueprint/tune_attribution_beta.py:466
 3.   20.70 MB  ( 493415 blocks)  blueprint/tune_attribution_beta.py:460
 4.   18.82 MB  ( 493413 blocks)  blueprint/tune_attribution_beta.py:370
 5.    5.65 MB  ( 246708 blocks)  blueprint/tune_attribution_beta.py:398
 6.    0.15 MB  (      1 blocks)  scripts/profile_memory.py:54
 7.    0.14 MB  (      1 blocks)  scripts/profile_memory.py:80
 8.    0.01 MB  (     22 blocks)  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/sre_compile.py:780
 9.    0.01 MB  (     41 blocks)  scripts/profile_memory.py:51
10.    0.01 MB  (     11 blocks)  blueprint/tune_attribution_beta.py:324
```

## 2. scout.statbotics_client bulk load (2025 Reefscape, event 2025txcmp2)

- Event: 2025txcmp2
- Teams loaded (TeamEventEPA): 45
- 2025 season matches loaded from root cache: 19,727
- Peak traced memory: **125.4 MB**
- Process peak RSS (after both profiles): **1741.0 MB**

### Top 10 allocation sites

```
 1.  122.94 MB  (1690393 blocks)  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/decoder.py:353
 2.    0.15 MB  (      1 blocks)  scripts/profile_memory.py:54
 3.    0.01 MB  (     89 blocks)  <string>:3
 4.    0.00 MB  (     25 blocks)  scripts/profile_memory.py:51
 5.    0.00 MB  (     46 blocks)  scout/statbotics_client.py:159
 6.    0.00 MB  (      3 blocks)  scripts/profile_memory.py:151
 7.    0.00 MB  (      1 blocks)  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/pathlib.py:1256
 8.    0.00 MB  (      1 blocks)  scripts/profile_memory.py:142
 9.    0.00 MB  (      1 blocks)  scripts/profile_memory.py:141
10.    0.00 MB  (      1 blocks)  scripts/profile_memory.py:150
```

## Findings & Recommendations

Two allocation sites exceed the 50 MB threshold:

- **`json/decoder.py:353` — 139.90 MB (tune) / 122.94 MB (scout)**:
  the dominant cost in both paths is parsing the on-disk Statbotics
  cache. For tune_attribution, all 11 seasons of raw match JSON (+
  team_year pages) are deserialised and kept in memory while
  `build_match_records` walks them. On macOS the process peak RSS
  climbed to **1.74 GB** — well above traced peak because CPython's
  allocator holds freed small-object arenas.
- **`blueprint/tune_attribution_beta.py:466` — 56.48 MB**: the compact
  record dict `{{"teams": [...], "epas": [...], "score": float}}`
  × 246,708 alliances. Dict + two 3-element lists per record.

### Recommendations

1. **Stream-and-drop raw pages (highest-impact, moderate change)**:
   `run_all_seasons` accepts a fully built `season_data` dict, forcing
   the caller to hold all raw pages simultaneously. Refactor the
   orchestrator to iterate season-by-season: fetch raw matches +
   team_years for one year, build compact records, `del` the raw,
   invoke `tune_beta_for_season`, store only the `TuningResult`.
   Traced peak would drop from 332 MB to roughly 332/11 ≈ 30 MB per
   season, and RSS would drop proportionally.
2. **Namedtuple / slotted dataclass for match records** (line 466):
   replacing the dict with `NamedTuple('AllianceRecord', teams, epas, score)`
   saves ~40% per record — ~22 MB on the current dataset, more on
   bigger ones. Requires touching every reader in
   `tune_attribution_beta.py` (predictive_mse, _attributed_scores,
   bootstrap) to use attribute access instead of `m["teams"]`.
3. **In-memory LRU for `scout/statbotics_client.py::_get`**:
   currently each call re-parses JSON from disk. For the long-running
   Discord bot, `@functools.lru_cache(maxsize=256)` on the endpoint
   string eliminates repeated parsing for hot queries
   (`team_year/2950/2025`, `team_event/...`). Scout bulk load alone
   is not the bottleneck (125 MB peak dominated by the 19,727-match
   2025 root cache we additionally loaded for comparison; the pure
   scout path is <3 MB).

### Quick win not implemented

All three changes are non-trivial refactors and touch tested code
paths (501+ tests in scout, 936+ in blueprint). The profile itself
is the deliverable; a follow-up task should land (1) as a
`run_all_seasons_streaming` variant and gate the old API as a
compatibility shim, then measure again.
