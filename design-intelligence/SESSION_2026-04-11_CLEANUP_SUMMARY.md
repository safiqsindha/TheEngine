# Session Summary — 2026-04-11 Cleanup
**Model:** Claude Sonnet 4.6 | **Plan:** CLEANUP_PLAN_2026-04-11.md

---

## What was done (6 commits)

### Phase 1 — Junk removal (`baad346`)
**Deleted from disk (not tracked — no git history impact):**
- 5 JVM crash dumps: `hs_err_pid18305.log`, `hs_err_pid31425.log`, `hs_err_pid31926.log`,
  `hs_err_pid32329.log`, `hs_err_pid33936.log`
- `.DS_Store` (repo root)
- `{src/` directory tree — empty artifact from a failed brace-expansion `mkdir` command

**Deleted stale untracked markdown (gitignored, no imports, stale Cursor/Maple content):**
- `CURSOR_PROMPTS.md` (referenced only in `setup.sh` banner and MASTER_DISPATCH)
- `MASTER_DISPATCH_PROMPT.md`
- `MAPLE_SIM_BUG_REPORT.md`
- `MAPLE_SIM_TELEOP_FIX_PROMPT.md`

**Fixed gitignore leak:**
- `antenna/antenna.db`, `antenna/antenna.db-shm`, `antenna/antenna.db-wal` were tracked in git
  despite being in `.gitignore`. Removed from git tracking via `git rm --cached`.
  **Files preserved on disk** — live SQLite state is intact.

### Phase 2 — Empty directories (`697e345`)
**Deleted 6 placeholder directories** that contained only `.gitkeep` or nothing:
`clock/`, `grid/`, `vault/`, `whisper/`, `systems/`, `skills/`

No Python imports found for any of them. These were reserved names never built out.

### Phase 3 — Docs consolidation (`c9af1bc`)
**Moved** `cockpit/` and `pit-crew/` into `design-intelligence/`:
- `cockpit/D1_CONTROLLER_MAPPING.md` → `design-intelligence/cockpit/`
- `cockpit/D2_DASHBOARD_LAYOUT.md` → `design-intelligence/cockpit/`
- `cockpit/D3_CONSOLE_HARDWARE_STANDARD.md` → `design-intelligence/cockpit/`
- `pit-crew/ROBOT_REPORT_TEMPLATE.md` → `design-intelligence/pit-crew/`

**Updated 3 markdown cross-references** to new paths:
`PLAYGROUND.md`, `LIVE_SCOUT_ARCHITECTURE.md`, `SUBSYSTEM_LEVERAGE_AUDIT.md`

No Python files were affected.

### Phase 4 — Test directory rename (`25036c9`)
**Renamed** `tests/live_scout/` → `tests/scout/` (23 files including fixtures).

"live_scout" naming was historical; the suite covers the Scout subsystem broadly
(pick_board, mode_a, mode_b, alliances, state backend, discord push, vision).

**Updated references in 4 files:**
- `.github/workflows/mode-a-build.yml` — functional pytest path updated
- `workers/mode_a.py` — docstring comment updated
- `tests/scout/test_mode_a_integration.py` — docstring + regen command updated
- `tests/scout/test_mode_b.py` — cross-reference comment updated

### Phase 5 — tools/ audit (`1bf5e31`)
**No deletions** — audit only. `design-intelligence/TOOLS_AUDIT_2026-04-11.md` written.

Findings:
- 5/11 scripts are stale robot-code analysis tools → candidates for `tools/_archived/`
- 4 are active run-once/event utilities → keep, add invocation docs
- 2 are active Limelight deploy artifacts → leave untouched

### Phase 6 — INDEX.md (`6cef05c`)
**Created** `design-intelligence/INDEX.md` — 51 docs classified into 5 buckets.
Entry point for all future agents and session planning.

---

## Test suite status throughout
Every phase confirmed: **501 passed, 2 skipped, 0 warnings.**

---

## Deferred (not acted on)

Per the plan's explicit exclusions:

| Item | Reason deferred |
|---|---|
| `sys.path.insert` hacks (antenna, eye, workers) | Package refactor; needs careful testing + design review |
| Config unification (antenna/.env, scout/.tba_key, workers env vars) | Needs design decision on shared bootstrap |
| tools/ script archival (5 stale robot-analysis scripts) | Human approval required — see TOOLS_AUDIT_2026-04-11.md |
| Test coverage expansion (blueprint, eye, workers, tools) | Separate task; significant effort |
| Top-level script consolidation (engine_advisor.py, engine_budget.py) | No obvious win; leave as-is |

---

## Repo state after cleanup

```
Top-level dirs (active):
  antenna/   blueprint/   design-intelligence/   engine_proxy/
  eye/       infra/       pit-crew/ (→ di/pit-crew/)
  scout/     scripts/     tests/    tools/        training/
  workers/

Top-level dirs (removed this session):
  clock/ grid/ vault/ whisper/ systems/ skills/ cockpit/ pit-crew/

Tests:
  tests/antenna/   (2 files — antenna + bot lock)
  tests/scout/     (23 files — scout subsystem, renamed from live_scout/)
  501 passed, 2 skipped, 0 warnings

design-intelligence/:
  52 docs + INDEX.md + TOOLS_AUDIT + CLEANUP_PLAN + CLEANUP_SUMMARY
  Subfolders: _archived/ cockpit/ pit-crew/
```

---

## Commits this session

```
baad346  chore(engine): remove junk files + untrack antenna db
697e345  chore(engine): remove 6 empty placeholder directories
c9af1bc  chore(engine): move cockpit + pit-crew docs into design-intelligence/
25036c9  chore(tests): rename tests/live_scout → tests/scout for clarity
1bf5e31  docs(engine): tools/ script audit 2026-04-11
6cef05c  docs(engine): add design-intelligence/INDEX.md
```

All pushed to `origin/main`.
