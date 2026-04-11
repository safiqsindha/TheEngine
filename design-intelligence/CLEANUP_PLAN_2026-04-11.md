# The Engine — Codebase Cleanup Plan
**Budget:** 2.5 hours autonomous (Sonnet 4.6)
**Starting state:** 501 tests passing, branch tip `9ca50f6`, clean working tree except untracked junk
**Goal:** Remove dead weight, fix gitignore leaks, consolidate docs. No architectural refactors.

---

## Ground rules

- **Run `pytest -q` between phases.** Expected: 501 passed, 2 skipped, 0 warnings. If that number changes, stop and investigate.
- **One commit per phase.** Each phase is self-contained and rollback-safe.
- **Never touch `design-intelligence/CROSS_SEASON_PATTERNS.md` or the 18 prediction rules.** These are the engine's brain.
- **Never touch `antenna/antenna.db` file contents.** Only remove it from git tracking — the file on disk is live state and must be preserved.
- **Never touch `blueprint/`, `src/`, `swervelib/`, `build/`, `bin/`, `vendordeps/`.** Blueprint is in active development; the rest is gitignored robot code.
- **If a "move" or "delete" turns up a code reference** (via Grep check), back out of that specific action and add it to a `CLEANUP_DEFERRED.md` list for later human review. Don't force it.

---

## Phase 1 — Junk removal (est. 20 min)

### 1.1 Baseline snapshot
```
git status
python3 -m pytest tests/ -q
```
Confirm clean + 501 passing. If dirty, stop.

### 1.2 Delete filesystem junk (not in git)
These are all local files already excluded by `.gitignore` — deleting them does not touch git history.

- `hs_err_pid*.log` (5 JVM crash dumps at repo root)
- `.DS_Store` (repo root and subdirs — use `find . -name .DS_Store -delete`)
- The `{src` directory — literal directory name from a broken brace-expansion mkdir. Verify it's empty with `find "./{src" -type f`, then `rm -rf "./{src"`.

### 1.3 Delete stale top-level markdown files (already in .gitignore, not tracked)
Verified via `git ls-files`: these files exist on disk but are NOT tracked. Safe to delete.
- `CURSOR_PROMPTS.md`
- `MASTER_DISPATCH_PROMPT.md`
- `MAPLE_SIM_BUG_REPORT.md`
- `MAPLE_SIM_TELEOP_FIX_PROMPT.md`

**Pre-check:** Grep for each filename across the repo (excluding `.git/` and `.gitignore`) — if any Python or markdown file references them, abort that specific deletion.

### 1.4 Fix gitignore leak: antenna database
`antenna/antenna.db`, `antenna/antenna.db-shm`, `antenna/antenna.db-wal` are tracked in git despite being in `.gitignore`. They must stay on disk (live state) but be removed from tracking.

```
git rm --cached antenna/antenna.db antenna/antenna.db-shm antenna/antenna.db-wal
```

Verify files still exist on disk after the command.

### 1.5 Test + commit
```
python3 -m pytest tests/ -q   # expect 501 passing
git add -A  # only removals + .gitignore state
git commit -m "chore(engine): remove junk files + untrack antenna db"
```

---

## Phase 2 — Empty placeholder directories (est. 10 min)

### 2.1 Verify dead dirs
These contain only `.gitkeep` or nothing at all:
- `clock/` (.gitkeep only)
- `grid/` (.gitkeep only)
- `vault/` (.gitkeep only)
- `whisper/` (.gitkeep only)
- `systems/` (empty)
- `skills/` (empty)

**Pre-check each:** Grep for the directory name as an import (e.g. `from clock`, `import clock`, `clock/`) in Python files. Expected result: no hits. If there are hits, skip that directory and note it.

### 2.2 Delete and commit
```
rm -rf clock grid vault whisper systems skills
python3 -m pytest tests/ -q   # still 501
git add -A
git commit -m "chore(engine): remove 6 empty placeholder directories"
```

---

## Phase 3 — Consolidate cockpit + pit-crew docs (est. 25 min)

`cockpit/` and `pit-crew/` are top-level but contain only markdown docs that logically belong with the rest of the design intelligence.

### 3.1 Inventory
- `cockpit/D1_CONTROLLER_MAPPING.md`
- `cockpit/D2_DASHBOARD_LAYOUT.md`
- `cockpit/D3_CONSOLE_HARDWARE_STANDARD.md`
- `pit-crew/ROBOT_REPORT_TEMPLATE.md`

### 3.2 Reference check
```
grep -rn "cockpit/D1\|cockpit/D2\|cockpit/D3\|pit-crew/ROBOT_REPORT" .
```
Any hit in Python files = potential breakage; list them. Hits in markdown files are fine — we'll update them after the move.

### 3.3 Move
```
mkdir -p design-intelligence/cockpit design-intelligence/pit-crew
git mv cockpit/*.md design-intelligence/cockpit/
git mv pit-crew/*.md design-intelligence/pit-crew/
rmdir cockpit pit-crew
```

### 3.4 Update any markdown cross-references
For each reference found in 3.2 that was in a `.md` file, update the path prefix.

### 3.5 Test + commit
```
python3 -m pytest tests/ -q
git add -A
git commit -m "chore(engine): move cockpit + pit-crew docs into design-intelligence/"
```

---

## Phase 4 — Rename `tests/live_scout/` → `tests/scout/` (est. 25 min)

The "live_scout" naming is historical; the tests cover the Scout subsystem generally. Renaming eliminates operator confusion.

### 4.1 Reference check
```
grep -rn "tests/live_scout\|live_scout" . --include="*.py" --include="*.ini" --include="*.toml" --include="*.yml" --include="*.yaml"
```
Expect hits in: test file headers/docstrings, possibly GHA workflows. NOT expected in production code.

### 4.2 Rename
```
git mv tests/live_scout tests/scout
```

### 4.3 Fix references
- Any test file with `tests/live_scout` in a comment/docstring → update to `tests/scout`
- Any CI workflow (`.github/workflows/*.yml`) that explicitly names `tests/live_scout` → update
- pytest discovery should still work automatically (no hardcoded paths in pytest.ini)

### 4.4 Test + commit
```
python3 -m pytest tests/ -q   # still 501 passing
git add -A
git commit -m "chore(tests): rename tests/live_scout → tests/scout for clarity"
```

---

## Phase 5 — Audit tools/ for staleness (est. 20 min)

`tools/` contains 12 utility scripts. Some may be archived; some live. Produce a report, don't delete anything yet.

### 5.1 Per-script last-touch analysis
For each `.py` in `tools/`, capture:
- Last commit date (`git log -1 --format=%cd --date=short -- tools/FILE`)
- Referenced-by count: `grep -rn "tools.FILE\|from tools" --include="*.py" | grep FILE_STEM`
- One-sentence purpose (read module docstring / top comment)

### 5.2 Write `design-intelligence/TOOLS_AUDIT_2026-04-11.md`
Table format:
| Script | Last touched | Imported by | Purpose | Status (active/stale/unknown) |

DO NOT delete or move any tools in this phase — the audit is an input for a later human decision.

### 5.3 Commit
```
git add design-intelligence/TOOLS_AUDIT_2026-04-11.md
git commit -m "docs(engine): tools/ script audit 2026-04-11"
```

---

## Phase 6 — Docs hygiene for design-intelligence/ (est. 25 min)

The `design-intelligence/` directory has 50+ markdown files. Some are system-of-record (the 18 rules, validation docs, roadmaps), some are session snapshots that pile up.

### 6.1 Classify
Walk the directory and bucket each `.md` file into one of:
- **SOR** (System of Record) — actively referenced by code or other SOR docs
- **Snapshot** — dated session summary, completed plan, one-shot report
- **Spec** — plans/specs that may or may not be complete

Use git log dates + cross-reference grep to classify. Do NOT move or delete yet.

### 6.2 Create `design-intelligence/INDEX.md`
A tidy top-level index listing every doc by bucket, with a one-line description. This becomes the entry point for future agents working in this repo. Sort alphabetically within each section.

### 6.3 Commit
```
git add design-intelligence/INDEX.md
git commit -m "docs(engine): add design-intelligence/INDEX.md"
```

---

## Phase 7 — Session summary + push (est. 15 min)

### 7.1 Write `design-intelligence/SESSION_2026-04-11_CLEANUP_SUMMARY.md`
Document:
- Files deleted (with reasons)
- Directories removed
- Files moved
- Gitignore leaks fixed
- Test suite status (501 passing confirmed)
- Deferred items (anything that was flagged but not acted on)

### 7.2 Final push
```
git push origin main
```

### 7.3 Verify
`git log --oneline -10` should show ~6 commits from this session, all with `chore(engine)` or `docs(engine)` prefixes.

---

## What this plan does NOT do

Deliberately excluded — too risky for autonomous execution:

1. **Package refactor** — Adding `__init__.py` files and eliminating `sys.path.insert` hacks. Needs careful testing across antenna, scout, eye, workers boundaries.
2. **Config unification** — Merging `antenna/.env`, `scout/.tba_key`, workers env patterns into a single loader. Needs design decisions.
3. **Tool deletions** — Phase 5 produces an audit doc but does NOT delete any tools/ scripts.
4. **Test coverage expansion** — The review identified blueprint/, eye/, workers/, tools/ as under-tested. Writing new tests is a separate task.
5. **Top-level script consolidation** — `engine_advisor.py`, `engine_budget.py` stay where they are.

All 5 are Tier B/C from the review and each deserves dedicated design time with the operator.

---

## Abort conditions

Stop work and commit what's done if any of the following:

- Test count drops below 501 and the cause isn't immediately obvious
- A phase's pre-check reveals code references that the review didn't flag
- Git status shows untracked files you don't recognize
- Any `git rm --cached` command fails or behaves unexpectedly

In any of these cases, finish the current commit cleanly, push, and write a note in the session summary explaining what was skipped and why.
