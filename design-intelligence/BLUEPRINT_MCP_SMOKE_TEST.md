# Blueprint MCP Smoke Test — 2026-04-13

**Tier A2 output.** Confirms the hedless/onshape-mcp install works end-to-end and records the Variable Studio finding that drives A3.

---

## Install state

- `~/onshape-mcp` cloned at commit HEAD, Python 3.12.13 venv, onshape-mcp 0.3.0 installed editable
- Keys sourced from `blueprint/.env` via `~/onshape-mcp/start_server.sh` wrapper (no key duplication)
- Registered in project `.mcp.json` as stdio server `onshape`
- Also registered `frc-docs` (npx -y frc-docs-mcp) — not tested in this pass
- Prereq: `brew install python@3.12` (system Python was 3.9.6, too old for onshape-mcp)

---

## Tools exercised

| Tool | Result |
|---|---|
| `list_documents` | ✅ 11 docs returned, owner/date correct |
| `get_elements` | ✅ 17 elements on FRCDesign elevator doc |
| `get_variables` (Assembly element) | ⚠ `No variables found` — expected, assemblies don't hold variables |
| `get_variables` (Part Studio `2039be93...`) | ⚠ `Variables in Part Studio: - = ` (empty) |
| `get_variables` (Part Studio `c16aca7d...` "Inline Elevator Block") | ⚠ Empty |
| `get_assembly_features` | ✅ 134 features returned, all IDs + types visible |

Conclusion: **MCP transport works.** All tool calls returned without auth or transport errors. Tool inventory (45 total) not fully exercised — smoke test scope was the A1-equivalent parametric check.

---

## The A1 finding (done via MCP, not user spike)

**Target:** FRCDesign Elevator Assembly
`cad.onshape.com/documents/9d90cf1c3e2d2b3c2f3996a3/w/06553b0689c28e57c04b06b7/e/b42b6baee43b15995577002e`

### Variable Studios

**None.** The two Part Studios in the document (`Part Studio`, `Inline Elevator Block`) return empty variable lists. There is no separate Variable Studio element in the document tree. The earlier Saturday claim that the elevator "has parametric mates and Variable Studio variables" was half right: **mates are parametric (in the mate-connector sense), variables are not exposed.**

### Mate structure

134 assembly features, breakdown:
- **112 Fastened mates** — rigid joins, used for every bolt/washer/bracket position
- **2 Slider mates** (`Slider 1`, `Slider 2`) — the elevator extension DOF, one per stage
- **1 Linear mate relation** — couples Slider 1 and Slider 2 so both stages extend together (cascade)
- **2 Mate connectors** — reusable reference frames
- **17 Replicate features** (1-22, some numbers skipped) — pattern-duplicated bolt positions

### What "parametric" actually means here

The elevator is **assembly-parametric**, not **geometry-parametric**:
- Stage extension is a mate DOF you can drive via `set_instance_position` on the Slider
- The cascade ratio (stage 2 extends 2x relative to stage 1) is encoded in the Linear mate relation
- Stage count, tube width, tube length, stage offsets are **geometry, not variables.** Changing any of them requires editing the underlying part studios or the COTS part configurations, not setting a variable.

**Implication:** You cannot parametrize the elevator by setting `stage_count = 3` and re-fetching. You can only slide the existing 2 stages along their Slider mates.

---

## What this means for the pivot

The Saturday hypothesis was:
> Blueprint generators become "copy FRCDesign reference doc, set Variable Studio variables, fetch back geometry."

The elevator reference doesn't support that workflow. For this doc, the available parametrization is:
1. Drive Slider mate positions (changes extension length, not geometry)
2. Edit COTS part configurations (changes individual part variants, not topology)
3. Actually edit the assembly (add/remove instances, re-mate) — same effort as hand-rolling

Three open questions this smoke test did NOT answer:

1. **Do OTHER FRCDesign reference docs expose Variable Studios?** This was one elevator. The pivot hinges on whether Variable Studio coverage is "zero across the library" vs "this one is thin, others are richer." Worth checking 3-5 more reference docs (swerve, shooter, turret) before committing.

2. **Can we build our own parametric reference docs on top of FRCDesign parts?** We'd author the Variable Studio ourselves, use FRCDesignLib parts as inserted instances. This is the middle path.

3. **Is the right primitive "copy Variable Studios" or "copy assembly topology + re-mate"?** If (1) confirms Variable Studios are rare, the pivot has to be about reusing assembly *structure* rather than reusing parametric *inputs*.

---

## What didn't break

- Auth loaded from `blueprint/.env` without issue
- HMAC signing on all 45 tools (none tested threw auth errors)
- Namespace collision between `onshape-mcp` tools and the existing `blueprint/onshape_api.py` wrapper: none, they live at different layers

---

## Next step

Write `BLUEPRINT_REV2_DECISION.md` (A3) using the finding above. The decision is no longer "pivot vs stay," it's "which of three pivot branches."
