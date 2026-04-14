# pitcrew

Pit Crew DS Log diagnostic subsystem for The Engine. Team 2950.

## Status: tested against synthetic fixtures; needs validation against real .dslog file before competition use

Dependency wired and 33 synthetic-fixture tests added 2026-04-14.
No real `.dslog` file is required to run the test suite.

What exists:

- `pitcrew/dslog.py` — analysis layer (voltage, CAN, timeline, errors, trip computer)
- `pitcrew/report.py` — markdown report generator (single-match + batch table)
- `pitcrew/cli.py` — `python -m pitcrew analyze <path>` / `python -m pitcrew batch <dir>` CLI

## Dependency

`dslogparser>=1.0.0` (LigerBots Team 2877, MIT — https://github.com/ligerbots/dslogparser)
is listed in `requirements-test.txt`. Install with:

```
pip install dslogparser
```

## Before competition use

1. Run against a real DS log from the FRC Driver Station laptop
   (typically `C:\Users\Public\Documents\FRC\Log Files\`) to validate that
   the field names and voltage/CAN scaling assumptions match the actual binary format.

2. Confirm brownout voltage threshold (6.8 V) and packet-loss disconnect
   threshold (≥4.0, i.e. ~100%) match observed DS behavior for your season.

## Intended use

Between matches: drop the `.dslog` file from the DS laptop into the pit
laptop, run the CLI, get a 30-second report with battery stats, brownout
count, CAN errors, and the top failure modes of the match.

```
python -m pitcrew analyze match01.dslog --team 2950
python -m pitcrew batch ./logs/ --team 2950 --table-only
```

Completes the first deliverable of `ARCH_PIT_SYSTEMS.md`.
