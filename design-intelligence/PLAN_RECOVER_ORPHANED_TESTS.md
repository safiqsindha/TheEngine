# Plan — Recover 297 Orphaned Tests
**Budget:** 2.5 hours autonomous (Sonnet 4.6)
**Branch tip:** `68ac05e` | **Today:** 2026-04-11

---

## The discovery

The repo has **800 tests collected by pytest default discovery**, but the GHA workflow
and every session summary so far has been running `pytest tests/` which only collects
**503 tests (501 pass + 2 skip)**.

The missing 297 tests are real and they pass, but they live in subsystem folders
instead of `tests/`:

| Location | Test count | Style | Currently in CI? |
|---|---|---|---|
| `antenna/test_antenna.py` | ~60 (function-style + custom runner) | mixed | **NO** |
| `antenna/test_bot_lock.py` | 5 (pytest functions) | pytest | **NO** |
| `blueprint/test_blueprint.py` | 76 (unittest.TestCase) | unittest | **NO** |
| `blueprint/test_b3_generators.py` | ~80 (unittest.TestCase) | unittest | **NO** |
| `blueprint/test_b4_b9_generators.py` | ~76 (unittest.TestCase) | unittest | **NO** |

**Net:** ~297 tests. They all PASS today when run directly (`pytest blueprint/`,
`pytest antenna/`), but they don't run in CI because the workflow says `tests/scout/`.

This is the highest-leverage cleanup left in the repo: zero new test code needed,
just relocating tests + wiring them into discovery.

---

## Goals

1. **Move all orphaned tests under `tests/`** so they run with the rest of the suite
2. **Wire them into CI** (GHA workflow + pytest.ini testpaths)
3. **Fix the 3 known warnings** from blueprint tests
4. **Mark network-dependent tests** so the hermetic suite stays green offline
5. **End state:** `pytest tests/` collects ~800 tests, all pass, runs in CI, zero warnings

---

## Ground rules

- **Run `pytest tests/ -q` between every phase.** Track the count: it should grow
  monotonically (503 → 568 after antenna → ~800 after blueprint).
- **One commit per phase.** Each phase stands alone.
- **Never modify test logic.** This is a relocation + wiring exercise. If a test fails
  after moving, the move is wrong — fix the path, not the test.
- **Network tests get `@pytest.mark.skipif(not os.getenv("ONSHAPE_*"), ...)`** so the
  suite is hermetic. Don't delete them — gate them.
- **Don't touch `blueprint/test_b3_*` or `_b4_b9_*` source content** — only their
  imports and locations.

---

## Phase 1 — Baseline + audit (15 min)

### 1.1 Baseline
```
git status                              # expect: clean tree
python3 -m pytest tests/ -q             # expect: 501 passed, 2 skipped
python3 -m pytest --collect-only -q | tail -5    # expect: 800 tests collected
```
If those numbers don't match, stop and figure out why.

### 1.2 Inventory orphaned tests
For each of the 5 orphaned files, capture:
- Test count via `pytest <file> --collect-only -q | tail -3`
- Top-of-file imports (look for sibling-package imports like `from frame_generator import`)
- Any `sys.path.insert` lines
- Any network dependencies (Onshape, Statbotics, TBA, Discord)

Write findings into a scratch comment in this plan. No code changes.

---

## Phase 2 — Move antenna tests (30 min)

### 2.1 Inspect imports
```
grep -n "^from\|^import" antenna/test_antenna.py
grep -n "^from\|^import" antenna/test_bot_lock.py
```
Both files use `sys.path.insert(0, Path(__file__).parent)` to import sibling antenna
modules. After the move, the parent will be `tests/antenna/`, not `antenna/`. The
sys.path line needs to point at the antenna/ folder.

### 2.2 Move
```
git mv antenna/test_antenna.py tests/antenna/
git mv antenna/test_bot_lock.py tests/antenna/
```

### 2.3 Fix sys.path
Update both moved files so the sys.path.insert points at the antenna source
directory. The pattern that works elsewhere in `tests/scout/`:

```python
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "antenna"))
```

### 2.4 Run + verify
```
python3 -m pytest tests/antenna/ -q       # expect: ~104 passed (39 existing + 65 new)
python3 -m pytest tests/ -q               # expect: ~568 passed total
```

If anything fails: the imports are still wrong, or one of the moved tests has
hardcoded paths. Fix the path, not the test.

### 2.5 Commit
```
git add -A
git commit -m "test(antenna): relocate test_antenna + test_bot_lock into tests/antenna/"
```

---

## Phase 3 — Move blueprint tests (60 min)

This is the bigger one. Blueprint tests use `unittest.TestCase` (not pytest functions),
and they import sibling blueprint modules (`from frame_generator import ...`).

### 3.1 Pre-create destination
```
mkdir -p tests/blueprint
touch tests/blueprint/__init__.py
```

### 3.2 Inspect each file
For each of `test_blueprint.py`, `test_b3_generators.py`, `test_b4_b9_generators.py`:
- List its sibling-blueprint imports (e.g. `from frame_generator import`,
  `from oracle import`, `from cad_builder import`, etc.)
- Note any `sys.path.insert` lines
- Note any imports of `test_*` symbols from non-test modules (the
  `from onshape_api import test_connection` is one — that's a Python function
  named `test_connection`, not a pytest test)

### 3.3 Move
```
git mv blueprint/test_blueprint.py tests/blueprint/
git mv blueprint/test_b3_generators.py tests/blueprint/
git mv blueprint/test_b4_b9_generators.py tests/blueprint/
```

### 3.4 Fix sys.path in each moved file
Replace the existing `sys.path.insert(0, str(Path(__file__).parent))` with:
```python
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "blueprint"))
```

### 3.5 Run + verify
```
python3 -m pytest tests/blueprint/ -q
```
Expect ~232 to collect; expect 232 to pass IF Onshape env vars aren't set, the
TestOnShapeSmoke class will fail because it hits the real API. That's the next step.

### 3.6 Gate network tests
Find every test that hits Onshape (or Statbotics live, or TBA live). The most
obvious is `class TestOnShapeSmoke` in `test_blueprint.py`. Add a class-level skip:

```python
@unittest.skipUnless(
    os.getenv("ONSHAPE_ACCESS_KEY") and os.getenv("ONSHAPE_SECRET_KEY"),
    "Onshape API credentials not set; skipping smoke tests"
)
class TestOnShapeSmoke(unittest.TestCase):
    ...
```

Do the same for any other API-touching test class in b3 or b4_b9.

### 3.7 Fix the test_connection name collision
`from onshape_api import test_connection` makes pytest collect a non-test as a test
and emit `PytestReturnNotNoneWarning`. Two clean fixes (pick whichever requires
less surgery):

**Option A** — alias the import:
```python
from onshape_api import (
    load_cots_catalog,
    lookup_part,
    test_connection as check_onshape_connection,
)
```

**Option B** — exclude it via pytest.ini collect_ignore_glob — but this is brittle.

Prefer Option A. Update any usages inside the test file from `test_connection(...)`
to `check_onshape_connection(...)`.

### 3.8 Run + verify clean
```
python3 -m pytest tests/blueprint/ -q
python3 -m pytest tests/ -q
```
Expected: ~800 collected, ~800 passed (or close — some may legitimately skip if env
vars aren't set), **0 warnings**.

### 3.9 Commit
```
git add -A
git commit -m "test(blueprint): relocate 232 tests into tests/blueprint/ + gate network smoke tests"
```

---

## Phase 4 — Wire CI + pytest config (15 min)

### 4.1 Update pytest.ini
Add `testpaths = tests` so pytest invocations without an explicit path find the
right thing automatically:
```ini
[pytest]
testpaths = tests
filterwarnings =
    ignore:.*NotOpenSSLWarning.*:Warning
    ignore::Warning:urllib3
```

This also closes the door on future orphaned tests — anything outside `tests/` will
not be auto-collected.

### 4.2 Update GHA workflow
`.github/workflows/mode-a-build.yml` line ~62:
```yaml
- name: Run full test suite
  run: |
    python -m pytest tests/ -v --tb=short
```
Rename the job from "pytest scout" to "pytest engine" since it's running the whole
suite now, not just scout.

### 4.3 Run + verify
```
python3 -m pytest -q          # bare invocation should now find tests/
```
Should match `pytest tests/ -q`.

### 4.4 Commit
```
git add -A
git commit -m "ci(engine): pytest testpaths + GHA workflow runs full tests/ tree"
```

---

## Phase 5 — Update memory + INDEX.md + RUNBOOK (15 min)

### 5.1 Update memory file
`~/.claude/projects/-Users-safiqsindha-Desktop-The-Engine/memory/project_antenna_complete.md`
mentions "501 tests passing". After this session, that number is ~800. Update both
that file and `project_scout_system.md` if it cites a count.

### 5.2 Update INDEX.md
Mention the orphaned-test recovery in a note at the top of `design-intelligence/INDEX.md`.

### 5.3 Update REGIONAL_RUNBOOK or just the cheat sheet
If the runbook references test count anywhere, update it. Otherwise skip.

### 5.4 Commit
```
git add -A
git commit -m "docs(engine): refresh test count after orphaned-test recovery"
```

---

## Phase 6 — Session summary + push (15 min)

### 6.1 Write `design-intelligence/SESSION_2026-04-11_TEST_RECOVERY_SUMMARY.md`
Document:
- The discovery: 297 hidden tests
- What was moved (5 files, ~297 tests)
- New test count: ~800
- Network-gated tests + how to enable them locally
- The pytest.ini testpaths change
- The GHA workflow update

### 6.2 Final push
```
git push origin main
```

### 6.3 Verify
`git log --oneline -8` should show 5–6 commits from this session.
`gh run list --limit 1` (if available) should show the new GHA workflow firing on push.

---

## Abort conditions

Stop and commit what's done if:

- Test count after a phase is LOWER than before — something got dropped
- A `git mv` reports unexpected output
- After fixing imports, a moved test still fails — investigate the test, not the move
- Onshape smoke tests hit the network and aren't gated by env-var check after
  Phase 3.6 — back out and fix the gate

Recovery from any abort: each phase is its own commit, so `git revert` cleanly
backs out a single phase without losing the others.

---

## Out of scope (do NOT do in this session)

1. Writing NEW tests for blueprint, eye, workers, or tools
2. Refactoring blueprint test classes from unittest to pytest functions (style migration)
3. Adding test coverage for `engine_advisor.py` or `engine_budget.py`
4. Touching `tools/` audit follow-ups (still pending human approval)
5. Any architectural refactor of antenna/scout/eye/workers package structure

All five are valuable but each deserves its own session. This session is purely
about recovering the tests that already exist.

---

## Why this is the right next thing

**Cheap to verify:** Tests that already pass standalone will pass once moved. There
is no new test logic to debug, just import paths.

**Off-season infrastructure:** 2026 season is over for Team 2950 — this is exactly
the time to fix CI gaps. Right now if blueprint regresses during off-season CAD
work, nobody finds out until someone manually runs `pytest blueprint/`. Moving
these tests into CI means any regression fails the GHA check immediately, so
off-season blueprint development can move with confidence.

**Honest test count:** Every session summary going forward will say "800 passing"
instead of "501 passing" — which is the actual truth.

**Closes a class of bugs:** With `testpaths = tests` set, no future test file will
silently end up orphaned.
