# The Engine — Code Review & Tech Debt Analysis
**Date:** 2026-04-14  
**Reviewer:** Claude (read-only pass)  
**Codebase state:** Post Blueprint CAD cut (2026-04-13), post-session additions (TrueSkill, robust anomaly, shot model, Roboflow wiring, Discord command layer)  
**Test suite:** 1,245 test functions across ~17,000 LOC of test code

---

## 1. Module-by-Module Inventory

| Module | LOC | Test coverage (est.) | Purpose |
|--------|-----|---------------------|---------|
| `scout/` (22 files) | ~9,500 | High (40+ test files) | Prediction engine, pick board, TBA/Statbotics clients, anomaly, TrueSkill, synergy |
| `blueprint/` (27 files) | ~12,100 | Moderate (7 test files, many generator tests now dead) | Oracle rules R1-R19, BOM rollup, motor model, attribution β tuning, *8 generator files (post-cut orphans)* |
| `antenna/` (9 files) | ~4,500 | Moderate (3 test files) | Discord bot, Chief Delphi scraper, live scout command layer |
| `workers/` (12 files) | ~4,400 | Moderate (10 test files) | Azure Container App Job workers: mode A/B/C, synthesis, vision, state backend |
| `eye/` (10 files) | ~4,700 | Low (1 test file + 7 misrouted into `tests/scout/`) | Vision pipeline: ffmpeg/OCR/LLM frame analysis, Roboflow wiring, HLS pull |
| `pitcrew/` (5 files) | ~710 | Moderate (1 test file, 418 LOC) | DS log parser, pit report generator |
| `design-intelligence/` | ~75 MD files | N/A (docs) | CROSS_SEASON_PATTERNS brain, session logs, ARCH plans |
| `workers/Dockerfile` | 85 | N/A | Multi-stage PaddleOCR image for Azure deploy |

---

## 2. Tech Debt Top 10

### TD-1: Duplicate `_normal_cdf` in three places
**What:** `scout/win_probability.py:53`, `blueprint/oracle.py:90`, and inline in `scout/trueskill_ratings.py:169` each re-implement `0.5 * math.erfc(-z / sqrt(2))`.  
**Why:** Copy-paste; the oracle docstring even says "Identical implementation to scout/win_probability.py so the two modules stay in sync."  
**Fix effort:** S — extract to `scout/math_utils.py`, import in all three.  
**Impact if not fixed:** If one copy diverges (e.g. adding continuity correction), predictions from oracle and win_probability will silently produce different results for the same inputs.

---

### TD-2: `blueprint/attribution_betas.py` — empirical β values missing for 8 of 13 seasons
**What:** `attribution_betas.py:51-52` — `empirical_beta: None` and `empirical_ci: None` for 2015, 2020 (COVID), and several others. The TODO comment says "populate after Item 1 data run."  
**Why:** Data-pull step (Statbotics bulk season fetch) was never executed post-infrastructure build.  
**Fix effort:** M — run `blueprint/run_beta_tuning.py` for each uncompleted season; takes ~2h plus cache write.  
**Impact if not fixed:** `pick_board.py` and `alliance_decomposition.py` call `get_attribution_beta()` which falls back to `prior_expected_beta`. On seasons where prior ≠ empirical (e.g. 2014 Aerial Assist: prior 0.60, empirical 0.95), pick recommendations will have meaningfully wrong confidence weighting.

---

### TD-3: `pick_board.py` is a 1,834-LOC God module
**What:** Single file contains: state I/O, ranking math, Monte Carlo simulation (`sim_bo3`, `sim_playoffs`), 10 CLI commands (`cmd_setup`, `cmd_pick`, `cmd_rec`, etc.), TBA enrichment, captain prediction, TrueSkill integration, beta-weighted scoring, and display formatting.  
**Why:** Organic growth — each feature was added inline.  
**Fix effort:** L — split into `pick_board_state.py`, `pick_board_sim.py`, `pick_board_cli.py`, `pick_board_scoring.py`.  
**Impact if not fixed:** Adding the next feature (e.g. per-team consistency score) requires navigating and reasoning about 1,834 lines. High merge conflict surface. Unit testing individual concerns requires mocking unrelated internals.

---

### TD-4: `importlib.util.spec_from_file_location` used as cross-module loader
**What:** `scout/pick_board.py:68-70` and `scout/alliance_decomposition.py:96-98` both load `blueprint/attribution_betas.py` by **absolute filesystem path** using `importlib.util` at call time, on **every invocation** of `_get_beta_for_year()`.  
**Why:** `blueprint/` has no `__init__.py`, and the comment in `alliance_decomposition.py:87` says "cannot use `from blueprint.attribution_betas`."  
**Fix effort:** S — add `blueprint/__init__.py` (empty file), add `blueprint/` to `sys.path` in `conftest.py`, replace both `importlib.util` blocks with standard imports.  
**Impact if not fixed:** Each `recommend_pick()` call re-parses `attribution_betas.py` from disk. At draft pace (10 picks/minute), this is 10 unnecessary module parses. Also, the pattern breaks if the repo is installed as a package rather than run from source.

---

### TD-5: `scout/auto_path_compatibility.py` — `AUTO_PATH_LIBRARY` is empty
**What:** `auto_path_compatibility.py:168` — `AUTO_PATH_LIBRARY: dict = {}`. The 2024 path stubs are commented out at lines 171-185 with a TODO to populate from PathPlanner exports. The compatibility score function returns a hardcoded `_DEFAULT_UNKNOWN = 0.5` for all queries.  
**Why:** Data-collection step never executed. Per the file comment: "no authoritative machine-readable zone assignments found."  
**Fix effort:** M — populate from 6328 Mechanical Advantage's 2024 strategy docs + PathPlanner community repos (sources identified in the comment).  
**Impact if not fixed:** `project_board()` in pick_board always uses neutral 0.5 compatibility score for auto paths, meaning path-conflict risk between alliance partners is never surfaced in pick recommendations.

---

### TD-6: `blueprint/apply_feature.py` and `fix_featurescript.py` import a missing module
**What:** Both `blueprint/apply_feature.py:10` and `blueprint/fix_featurescript.py:10` do `from insert_cots import ...`, and line 13 opens `fresh_assembly_ids.json`. Neither `insert_cots.py` nor `fresh_assembly_ids.json` exist in the repo. These are leftover Onshape MCP scripts from pre-cut.  
**Why:** The 2026-04-13 cut removed CAD generators conceptually but did not delete these two scripts.  
**Fix effort:** S — delete `blueprint/apply_feature.py` and `blueprint/fix_featurescript.py`. They are unreachable without `insert_cots.py`.  
**Impact if not fixed:** Any `import *` scan or static analysis tool will surface an `ImportError`. Confuses students reading the blueprint directory.

---

### TD-7: `scout/the_scout.py:95` — `year = 2025` hardcoded in `cmd_lookup`
**What:** `the_scout.py:95` — `year = 2025` is a literal default. `pick_board.py:52` similarly has `DEFAULT_YEAR: int = 2025`. These will silently produce stale data in the 2027 season without any warning.  
**Why:** Shortcut during 2025 build — expected to be updated manually each season.  
**Fix effort:** S — derive from `datetime.date.today().year` (or use `datetime.date.today().year if datetime.date.today().month >= 1 else ...` for kickoff seasonality). Centralize in a single `CURRENT_SEASON` constant.  
**Impact if not fixed:** In January 2027 after kickoff, all EPA lookups and pick recommendations will default to 2025 data unless the operator knows to pass `--year 2027`.

---

### TD-8: Three independent cache layer implementations
**What:** The codebase has three separate JSON-to-disk caching layers:  
- `scout/tba_client.py:42-57` — `requests`-based, 1-hour TTL  
- `scout/statbotics_client.py:76-95` — `requests`-based, 1-hour TTL  
- `blueprint/statbotics_client.py:36-59` — `urllib`-based, offset-keyed pages, no TTL  

All three re-implement the same mkdir/read/write/TTL-check pattern.  
**Why:** Each was written independently; no shared HTTP client module exists.  
**Fix effort:** M — extract to `scout/http_cache.py` with configurable TTL, backend (requests/urllib), and key schema.  
**Impact if not fixed:** A bug in cache invalidation (e.g., stale alliances data at an event) must be fixed in three places. The scout/ Statbotics client uses `requests` while blueprint/ uses `urllib`; they cache to the same directory (`.cache/statbotics/`) with **different filename schemas**, so cached files from one client are invisible to the other.

---

### TD-9: `probe_api()` in `roboflow_config.py` sends API key as URL query parameter
**What:** `eye/pipeline/roboflow_config.py:177` — `url = f"https://api.roboflow.com/?api_key={key}"`. The API key appears in the URL, which means it will appear in server access logs, browser history, and any HTTP proxy logs.  
**Why:** This is the Roboflow SDK's own pattern; the wrapper mirrors it without sanitizing.  
**Fix effort:** S — switch to Authorization header: `headers={"Authorization": f"Bearer {key}"}` (Roboflow supports this; check their v1 API docs).  
**Impact if not fixed:** If the team's laptop is used for debugging and logs are shared (e.g. pasted to CD), the Roboflow API key will be exposed.

---

### TD-10: `eye/the_eye.py` — subprocess `ffmpeg` call silently ignores failure
**What:** `the_eye.py:114` — `subprocess.run(cmd, capture_output=True)` does not check the return code. If `ffmpeg` is not installed or the video download failed, `extract_frames` returns an empty list. The caller at line 638 checks `if not frames: return` but prints no diagnostic. The user sees nothing.  
**Why:** Prototype-quality error handling.  
**Fix effort:** S — add `check=True` or check `result.returncode`; print `result.stderr.decode()` on failure.  
**Impact if not fixed:** At a competition, if ffmpeg is missing or the video is malformed, the eye pipeline silently produces zero frames and the operator has no indication of why the analysis returned empty.

---

## 3. Architecture Smells

**No structured logging in scout/ or blueprint/**: Both modules use `print()` exclusively — 159 print statements in `pick_board.py` alone, 48 in `oracle.py`. The `antenna/` module correctly uses Python `logging`. At competition, capturing pick-board decision reasoning requires terminal scroll; it cannot be filtered or persisted to a log file without shell redirection. Recommendation: add a `LOG_LEVEL` env var and a `scout/logger.py` that respects it.

**sys.path mutation spread across 10+ files**: The `conftest.py` adds the project root, but individual modules (`antenna/antenna.py`, `antenna/bot.py` twice, `antenna/live_scout_commands.py`, `eye/vision_yolo.py`, `scout/synergy.py`) each also mutate `sys.path` defensively. This is belt-and-suspenders that makes it hard to understand what the actual import graph is. A proper `pyproject.toml` with editable install would eliminate all of these.

**State file is an untyped dict**: `pick_board.py` uses a raw `dict` for the draft state (loaded/saved as JSON). There is no schema validation, no TypedDict, no dataclass. Fields are accessed via string keys like `state["teams"]`, `state["alliances"]`, `state["our_seed"]`. Any new field added by one function may be absent in a state file created by an older version. Consider a `PickBoardState` dataclass with a migration layer.

**shot_model.py is 2025-inert**: The module docstring says "Not used for 2025 Reefscape (no shooter mechanism)." It is tested (13 tests) but not called from any production path. It is dead code until a 2026+ shooter game arrives.

---

## 4. Testing Gaps

**eye/ integration paths are mostly untested**: `the_eye.py`, `stream_recorder.py`, `eye_bridge.py`, and `capture/fit_dcmp.py` have **zero dedicated tests**. The roboflow config has 15 tests. The hls_pull, overlay_ocr, and vision_yolo tests live in `tests/scout/` (wrong location — they're eye/ modules). `the_eye.py`'s `cmd_analyze`, `cmd_scout`, `synthesize_report`, and `print_report` functions are fully untested.

**No regression test for pick_board setup → pick → undo → board round-trip**: The `test_live_scout_commands.py` and `test_pick_board.py` test individual commands in isolation. There is no end-to-end test that runs setup, 5 picks, an undo, then verifies board state matches expected draft order. This is the most-used flow at competition.

**auto_path_compatibility.py has empty library**: The tests in `test_auto_path_compatibility.py` test the algorithm with synthetic paths, but `AUTO_PATH_LIBRARY` being empty means the integration path (look up team's actual path, score compatibility) is never exercised.

**TrueSkill + pick_board integration**: `trueskill_ratings.py` has 19 unit tests. But there are no tests confirming that `from_match_history()` → `predict_match_win_prob()` produces a win probability that is consistent with what `win_probability.py` produces for the same alliance matchup. The two models can diverge silently.

---

## 5. Documentation Gaps

**`workers/` has no README**: The `workers/` directory contains 4,400 LOC including Dockerfile, Azure state backend, and 4 distinct worker modes. There is no README explaining how to run locally, how to configure `STATE_BACKEND`, or what environment variables are required.

**`eye/pipeline/roboflow_config.py` zone polygons are PLACEHOLDER**: `FIELD_ZONES_2026_REBUILT` has four `ZoneConfig` objects with `[[0,0],[200,0],[200,200],[0,200]]` placeholder coordinates. The module docstring says "Week 2: define real zone polygons via polygonzone tool." This is shipped with placeholder values that would silently produce wrong zone assignments in production.

**`blueprint/oracle_pipeline.py` references deleted generators without noting the cut**: `oracle_pipeline.py:34-39` imports from `elevator_generator`, `intake_generator`, `flywheel_generator`, `arm_generator`, `climber_generator`, `conveyor_generator`. The `BLUEPRINT_REV2_POSTMORTEM.md` documents the cut, but `oracle_pipeline.py` has no header comment indicating it now operates in a degraded/analysis-only mode.

**`blueprint/onshape_api.py`**: Still functional code (imports `onshape_client.client.Client`), but post-cut the Onshape MCP integration was deleted. The file has no "DEPRECATED" or "analysis-only" notice.

---

## 6. Dependency Health

**`requirements-test.txt` is unpinned**: All dependencies use `>=` or bare package name (`pytest`, `numpy`, `trueskill>=0.4.5`, `roboflow>=1.1.0`). The `workers/requirements.txt` uses range pins (e.g. `paddleocr>=3.0,<4.0`), which is better. Recommend pinning the test requirements to a lockfile or at least adding upper bounds to prevent surprise breaks.

**`onshape-client>=1.6.0` in requirements-test.txt**: This is a dependency of the deleted Onshape MCP. Post-cut, it is no longer needed by any tested code path. It adds install time and a 3rd-party dependency surface for no benefit.

**`trueskill` backend is `scipy`**: `trueskill_ratings.py:34-41` sets `backend="scipy"`. `scipy` is not listed in `requirements-test.txt`. Tests pass because `trueskill` falls back to a pure-Python backend if scipy is absent, but the production code explicitly requests scipy. If scipy is missing in the test environment, the behavior differs from production.

---

## 7. Dead Code

**`blueprint/apply_feature.py` and `blueprint/fix_featurescript.py`**: Both import `insert_cots` which does not exist. These are broken orphans from the pre-cut Onshape MCP work and will `ImportError` if imported.

**`blueprint/run_dry_run.py` and `blueprint/run_2022_full_blueprint.py`**: Both import all 8 generator modules. Post-cut, these are demonstration/historical scripts with no production callers. They could be moved to `design-intelligence/_archived/`.

**`eye/the_eye.py:ANTHROPIC_MODELS`**: Contains `"opus": "claude-opus-4-6"`. The `LocalVisionBackend` and `YOLOVisionBackend` both raise `NotImplementedError` unconditionally — they are stub classes with no reachable behavior.

**`scout/shot_model.py`**: 119-LOC module, 13 tests, zero production callers. Not wired to any live pipeline. Placeholder until a shooter game.

---

## 8. Performance Hotspots

**`pick_board.py:_get_beta_for_year()`** re-parses `attribution_betas.py` from disk via `importlib.util.spec_from_file_location` on **every call** to `recommend_pick()`. In `cmd_rec`, this is called in a loop over all available teams (potentially 40+ teams at an event). That is 40+ module parses per `!rec` Discord command.

**`blueprint/statbotics_client.py` and `scout/statbotics_client.py` write to the same `.cache/statbotics/` directory with different key schemas**: The scout client uses `endpoint.strip("/").replace("/","_")` while the blueprint client uses `f"{safe_endpoint}_{year}_{offset}.json"`. If both clients are used in the same session (e.g. beta tuning after a pick-board run), their cache files coexist without collision — but the different naming means neither client can serve the other's cached pages, causing redundant network calls.

**`anomaly.py:detect_anomalies_all_teams()`** calls `detect_anomalies()` (not `detect_anomalies_robust()`) even though `ANOMALY_METHOD = "robust"`. The all-teams aggregator silently uses z-score rather than the recommended robust method. This is both a correctness gap and a performance non-issue (both are O(N)), but the inconsistency means the recommended method isn't actually used in the batch path.

---

## 9. Security/Safety

**`roboflow_config.py:177`**: API key appears in URL query string (`?api_key={key}`). Visible in any HTTP proxy log, CDN access log, or debug paste. Risk: low (Roboflow key is low-privilege), but fixable with an Authorization header.

**`scout/tba_client.py:31-37`**: Falls back to reading key from `scout/.tba_key` file. The `.gitignore` correctly excludes `scout/.tba_key`. No issue — documented and properly ignored.

**`eye/the_eye.py:298-299`**: Reads API key from `~/.anthropic_key` as a fallback. This is a plaintext key file in the user's home directory. No issue for a local laptop; worth noting if the repo ever runs in a shared environment.

**`blueprint/apply_feature.py:13`**: `open(BASE_DIR / "fresh_assembly_ids.json")` — opens a file at module import time. If the file doesn't exist, the import raises `FileNotFoundError` at load time, not call time. This is a boot-time crash risk for any script that imports from `blueprint/` via wildcard.

**No input validation on Discord command args**: `live_scout_commands.py` correctly returns user-facing error strings rather than raising. However, team numbers and alliance numbers parsed via `int(args[0])` in several places will raise `ValueError` if a user types a non-integer. The bot catches top-level exceptions, so this won't crash, but the error message will be an unformatted Python traceback rather than a helpful "Usage: ..." string.

---

## Top 5 Fixes to Prioritize (ROI-ranked)

**1. Extract `_normal_cdf` to `scout/math_utils.py` (TD-1)** — S effort, eliminates silent divergence risk between oracle confidence and win probability. Highest correctness ROI.

**2. Add `blueprint/__init__.py` and fix imports (TD-4)** — S effort, eliminates 40+ filesystem parses per `!rec` Discord command at competition. Direct latency win on the most-used command.

**3. Delete `blueprint/apply_feature.py` and `blueprint/fix_featurescript.py` (TD-6)** — S effort, removes broken orphan files that ImportError on import. Cleans up student-visible directory.

**4. Centralize `CURRENT_SEASON` constant and derive from date (TD-7)** — S effort, prevents silent 2025→2026 data staleness when 2027 kickoff arrives. One-time fix before January 2027.

**5. Add a `workers/README.md` and annotate `oracle_pipeline.py` as analysis-only (Doc gap + TD-6 adjacent)** — S effort, highest documentation ROI for any new contributor (mentor or student) trying to run the Azure pipeline.

---

*Secondary priority: run `blueprint/run_beta_tuning.py` for the 8 seasons with `empirical_beta: None` (TD-2, M effort) — this directly improves pick recommendation accuracy for historical validation runs and future season calibration.*
