# pitcrew — WIP

Pit Crew DS Log diagnostic subsystem for The Engine. Team 2950.

## Status: code drop, untested

Landed 2026-04-13. The sub-agent building this was rate-limited before tests
and dependency wiring completed. What exists:

- `pitcrew/dslog.py` — analysis layer (voltage, CAN, timeline, errors)
- `pitcrew/report.py` — markdown report generator
- `pitcrew/cli.py` — `python -m pitcrew.dslog analyze <path>` entry

## Before first use

1. Install the upstream parser:
   ```
   pip install dslogparser
   ```
   (LigerBots Team 2877, MIT — https://github.com/ligerbots/dslogparser)

2. Run against a real DS log from the FRC Driver Station laptop
   (typically `C:\Users\Public\Documents\FRC\Log Files\`) to sanity-check
   output format.

3. Add tests in `tests/pitcrew/` with synthetic log fixtures before relying
   on this in competition.

## Intended use

Between matches: drop the `.dslog` file from the DS laptop into the pit
laptop, run the CLI, get a 30-second report with battery stats, brownout
count, CAN errors, and the top failure modes of the match.

Completes the first deliverable of `ARCH_PIT_SYSTEMS.md`.
