# Benchmark Baseline — Hot Paths

Baseline numbers from one local run of `pytest -m benchmark --benchmark-only`
on a single developer machine. Use these as a regression fence — a >2x
slowdown on any hot path should be investigated before landing.

## Environment

- Date: 2026-04-14
- Platform: darwin (macOS), Python 3.9.6
- pytest 8.4.2, pytest-benchmark 5.2.3
- Defaults: `timer=time.perf_counter disable_gc=False min_rounds=5`

## Results

| Hot path | Test | Median | Mean | Min | Rounds |
|---|---|---:|---:|---:|---:|
| 1. Oracle `predict_game` (R1–R19) | `test_bench_oracle_predict_game` | 21.6 µs | 31.1 µs | 21.2 µs | 7,543 |
| 2. `compute_alliance_decomposition` (β=0.7, year=2025) | `test_bench_alliance_decomposition` | 7.7 µs | 13.8 µs | 7.5 µs | 43,244 |
| 3. Oracle Rule #18 via `get_rule_breakdown` | `test_bench_oracle_rule_18_breakdown` | 25.7 µs | 52.1 µs | 25.2 µs | 21,146 |
| 4. `pick_board.recommend_pick` (~50 teams, β-aware) | `test_bench_pick_board_recommend_50_teams` | 1.371 s | 1.447 s | 1.329 s | 5 |
| 5. `synergy.defense_adjusted_synergy` | `test_bench_defense_adjusted_synergy` | 9.9 µs | 14.7 µs | 9.7 µs | 37,677 |

## Notes

- **Hot path #4 dominates** at ~1.4s per call. The cost lives in
  `_mc_quick` (2000 Monte Carlo sims per available team). Any UI path
  calling `recommend_pick` synchronously in the request loop should be
  treated as an offline/background computation, not interactive.
- Hot paths #1–3 and #5 are all sub-100µs — headroom is plentiful.
- To refresh: `pytest -m benchmark --benchmark-only`.
  Store comparative snapshots with `--benchmark-save=<name>` and diff via
  `pytest-benchmark compare`.
