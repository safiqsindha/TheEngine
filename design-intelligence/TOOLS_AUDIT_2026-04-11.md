# tools/ Script Audit — 2026-04-11

Audit of all Python scripts in `tools/`. None are imported by production code
(antenna, scout, eye, blueprint, workers). All are standalone CLI utilities.

**No deletions made in this pass.** This doc informs a future human decision.

---

## Audit table

| Script | Last touched | Imported by | Purpose | Status |
|---|---|---|---|---|
| `analyze_path_error.py` | 2026-04-04 | — | Compares commanded vs actual robot pose from WPILOG; recommends PID adjustments | **stale** — robot-code analysis tool; only useful at competition with logs |
| `battery_analysis.py` | 2026-04-04 | — | Extracts battery voltage from hoot logs; flags critical sag events | **stale** — robot-code analysis tool; same boat as path error |
| `extract_cycles.py` | 2026-04-04 | — | Parses WPILOG for FUEL scoring cycles (2 refs are self-contained in tools/) | **stale** — game-piece-specific (2026 REBUILT); post-season rewrite candidate |
| `generate_configs.py` | 2026-04-04 | — | Reads `hardware_config.ini` → regenerates swerve drive JSONs | **stale** — hardware_config.ini is gitignored, lives in 2950-robot repo |
| `generate_grid_cards_v2.py` | 2026-04-07 | — | Generates PDF wiring standards card + PDH slot template via ReportLab | **active (run-once)** — updated most recently; PDF output not stored in repo |
| `generate_navgrid.py` | 2026-04-04 | — | Generates `navgrid.json` for 2026 REBUILT field (165×82 grid, 10 cm resolution) | **active (run-once)** — field-specific; re-run if obstacle zones change |
| `post_match_analyzer.py` | 2026-04-04 | — | Unified post-match debrief: cycle extraction + path error + battery | **stale** — depends on WPILOG data from 2950-robot; no test coverage |
| `pre_match_check.py` | 2026-04-04 | — | NetworkTables 4 pre-match health check at competition | **active (event only)** — standalone; run from pit laptop before enabling |
| `pull_statbotics.py` | 2026-04-04 | — | Pulls EPA data from Statbotics → CSV for design-intelligence/ analysis | **active** — feeds `design-intelligence/statbotics_epa_data.csv`; rerun each season |
| `sim_keyboard_driver.py` | 2026-04-04 | — | Keyboard-to-WPILib-Sim WebSocket bridge (replaces Sim GUI joystick) | **active (dev only)** — used when running robot sim; not needed in CI |
| `snapscript_fuel_detector.py` | 2026-04-04 | — | Limelight SnapScript: ONNX inference via Wave Robotics YOLOv11n model | **active** — deployed to Limelight 4 at competition |
| `wave_fuel_detector.onnx` | 2026-04-04 | — | ONNX model weights for fuel ball detection (Wave Robotics, single-class) | **active** — binary asset paired with snapscript_fuel_detector.py |

---

## Recommended actions (for human review)

### Tier A — Safe to archive (robot-code analysis, no Python deps here)
These scripts analyze WPILOG/hoot data from the robot. The robot code and its logs
live in the separate `2950-robot` repo. They can be moved to `tools/_archived/`
without affecting any Engine subsystem.

- `analyze_path_error.py`
- `battery_analysis.py`
- `extract_cycles.py`
- `generate_configs.py`
- `post_match_analyzer.py`

### Tier B — Keep but document invocation
These are standalone utilities that get run at specific times.

- `generate_grid_cards_v2.py` — add invocation to `design-intelligence/REGIONAL_RUNBOOK.md`
- `generate_navgrid.py` — add to runbook as "re-run if field obstacle zones change in a patch"
- `pre_match_check.py` — already documented in runbook; leave as-is
- `pull_statbotics.py` — add to runbook as "rerun at season start to refresh EPA CSV"
- `sim_keyboard_driver.py` — leave as-is; dev-only utility

### Keep as-is (active, no action needed)
- `snapscript_fuel_detector.py` + `wave_fuel_detector.onnx` — Limelight deploy artifacts; keep together

---

## Summary
- 5 of 11 scripts are stale robot-code analysis tools → candidates for `tools/_archived/`
- 4 are active but run-once or event-only utilities → keep + add invocation docs
- 2 are active production artifacts (snapscript + ONNX model) → leave untouched

**Next step:** Operator reviews this list and approves which tier-A scripts to archive.
