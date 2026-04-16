"""Multi-year validation driver for ``blueprint/manual_parser.py``.

Generalizes the 2019-only driver so 2019 / 2023 / 2024 / (future 2025, 2026)
can be validated with a single command. Ground truth is encoded as a per-year
dict so adding a new year is just appending to ``GROUND_TRUTH``.

Usage::

    export ANTHROPIC_API_KEY=sk-ant-...
    python blueprint/validate_manual.py --year 2019
    python blueprint/validate_manual.py --year 2023 --manual manuals/2023_charged_up.pdf
    python blueprint/validate_manual.py --year 2024

Guardrails:
- Exits non-zero if ``ANTHROPIC_API_KEY`` is unset.
- Exits non-zero if the target PDF does not exist.
- Writes a machine-readable summary to
  ``design-intelligence/_{year}_validation_summary.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from blueprint.manual_parser import (  # noqa: E402
    JSON_SCHEMA_DESCRIPTION,
    PROMPT_TEMPLATE,
    ManualParse,
    consensus,
    extract_pdf_text,
    parse_manual,
    _coerce_json,
)

MODEL = "claude-haiku-4-5"
N_PARSES = 3

# Haiku 4.5 pricing (USD per 1M tokens) — update if pricing changes.
HAIKU_INPUT_PER_MTOK = 1.00
HAIKU_OUTPUT_PER_MTOK = 5.00


# ---------------------------------------------------------------------------
# Per-year ground truth. Each entry returns an ordered list of check tuples
# ``(name, predicate(flat_scoring, merged))`` that the driver runs against the
# consensus parse. ``flat_scoring`` is the flattened
# ``{phase: [entries]}`` structure of the merged parse.
# ---------------------------------------------------------------------------


def find_pts(
    entries: list,
    keywords: list,
    require_all: bool = True,
) -> Optional[dict]:
    """Strict substring lookup over scoring entries.

    Returns the first entry whose lowercased ``name + " " + location`` blob
    contains ALL ``keywords`` (when ``require_all=True``) or ANY keyword
    (when ``require_all=False``). Returns ``None`` if no entry matches — no
    silent fallback to the first entry.
    """
    for e in entries or []:
        name = str(e.get("name", "")).lower()
        loc = str(e.get("location", "")).lower()
        blob = f"{name} {loc}"
        if require_all:
            if all(k.lower() in blob for k in keywords):
                return e
        else:
            if any(k.lower() in blob for k in keywords):
                return e
    return None


def _phase(merged: ManualParse, phase: str) -> list:
    return merged.scoring.get(phase, []) or []


CheckFn = Callable[[ManualParse], tuple[bool, str]]


def _eq_pts(entry: Optional[dict], expected: int) -> tuple[bool, str]:
    if entry is None:
        return False, f"no entry matched (expected {expected} pts)"
    got = entry.get("points")
    return got == expected, f"got points={got} from {entry!r}"


# --- 2019 Deep Space --------------------------------------------------------


def _checks_2019(merged: ManualParse) -> list:
    auto = _phase(merged, "auto")
    teleop = _phase(merged, "teleop")
    end = _phase(merged, "endgame")

    checks: list = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # --- Auto: cargo + hatch in cargo ship (distinct pieces at same location!)
    e = find_pts(auto, ["cargo", "cargo ship"])
    # Filter: must not be the hatch entry
    if e is not None and "hatch" in str(e.get("name", "")).lower():
        e = None
    ok, d = _eq_pts(e, 3)
    add("auto.cargo_in_cargo_ship=3", ok, d)

    e = find_pts(auto, ["hatch", "cargo ship"])
    ok, d = _eq_pts(e, 2)
    add("auto.hatch_on_cargo_ship=2", ok, d)

    e = find_pts(auto + end, ["hab", "level 1"]) or find_pts(auto + end, ["hab", "l1"])
    ok, d = _eq_pts(e, 3)
    add("auto.hab_cross_l1=3", ok, d)

    e = find_pts(auto + end, ["hab", "level 2"]) or find_pts(auto + end, ["hab", "l2"])
    ok, d = _eq_pts(e, 6)
    add("auto.hab_cross_l2=6", ok, d)

    # --- Teleop
    e = find_pts(teleop, ["cargo", "cargo ship"])
    if e is not None and "hatch" in str(e.get("name", "")).lower():
        e = None
    ok, d = _eq_pts(e, 3)
    add("teleop.cargo_in_cargo_ship=3", ok, d)

    e = find_pts(teleop, ["cargo", "rocket"])
    if e is not None and "hatch" in str(e.get("name", "")).lower():
        e = None
    ok, d = _eq_pts(e, 3)
    add("teleop.cargo_in_rocket=3", ok, d)

    e = find_pts(teleop, ["hatch", "rocket"])
    ok, d = _eq_pts(e, 2)
    add("teleop.hatch_in_rocket=2", ok, d)

    e = find_pts(teleop, ["hatch", "cargo ship"])
    ok, d = _eq_pts(e, 2)
    add("teleop.hatch_in_cargo_ship=2", ok, d)

    # --- Endgame climb
    e = find_pts(end, ["level 3"]) or find_pts(end, ["l3"])
    ok, d = _eq_pts(e, 12)
    add("endgame.hab_climb_l3=12", ok, d)
    e = find_pts(end, ["level 2"]) or find_pts(end, ["l2"])
    ok, d = _eq_pts(e, 6)
    add("endgame.hab_climb_l2=6", ok, d)
    e = find_pts(end, ["level 1"]) or find_pts(end, ["l1"])
    ok, d = _eq_pts(e, 3)
    add("endgame.hab_climb_l1=3", ok, d)

    # --- Game pieces
    names = {str(gp.get("name", "")).lower() for gp in merged.game_pieces or []}
    add("game_piece.cargo", any("cargo" in n for n in names), f"got {names}")
    add("game_piece.hatch", any("hatch" in n for n in names), f"got {names}")

    # --- Possession
    pl = merged.possession_limits or {}
    add("possession.max=1", pl.get("max_simultaneous") == 1, f"got {pl}")

    # --- RPs
    rp_names = " ".join(str(r.get("name", "")).lower() for r in merged.ranking_points or [])
    add("rp.rocket", "rocket" in rp_names, f"got {rp_names}")
    add("rp.hab", "hab" in rp_names or "climb" in rp_names, f"got {rp_names}")

    # --- Constraints
    cc = merged.critical_constraints or {}
    w = cc.get("weight_lbs")
    add("weight=125lb", w is not None and abs(float(w) - 125.0) < 0.5, f"got {w}")

    return checks


# --- 2023 Charged Up --------------------------------------------------------


def _checks_2023(merged: ManualParse) -> list:
    auto = _phase(merged, "auto")
    teleop = _phase(merged, "teleop")
    end = _phase(merged, "endgame")

    checks: list = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # Auto piece in hybrid=3, mid=4, high=6 (cone or cube — Charged Up hybrid
    # row accepted either piece at the same points, so we expect at least one
    # entry per (phase, location) row).
    for loc_kw, expected in [("hybrid", 3), ("mid", 4), ("high", 6)]:
        e = find_pts(auto, [loc_kw])
        ok, d = _eq_pts(e, expected)
        add(f"auto.{loc_kw}_node={expected}", ok, d)

    for loc_kw, expected in [("hybrid", 2), ("mid", 3), ("high", 5)]:
        e = find_pts(teleop, [loc_kw])
        ok, d = _eq_pts(e, expected)
        add(f"teleop.{loc_kw}_node={expected}", ok, d)

    # Auto mobility = 3
    e = find_pts(auto, ["mobility"]) or find_pts(auto + end, ["mobility"])
    ok, d = _eq_pts(e, 3)
    add("auto.mobility=3", ok, d)

    # Endgame park=2, dock=6, engage=10
    e = find_pts(end, ["park"])
    ok, d = _eq_pts(e, 2)
    add("endgame.park=2", ok, d)
    e = find_pts(end, ["dock"])
    if e is not None and "engage" in str(e.get("name", "")).lower():
        # Sometimes Haiku merges dock+engage into a single row; accept with a note
        pass
    ok, d = _eq_pts(e, 6)
    add("endgame.dock=6", ok, d)
    e = find_pts(end, ["engage"])
    ok, d = _eq_pts(e, 10)
    add("endgame.engage=10", ok, d)

    # Game pieces: cone + cube
    names = {str(gp.get("name", "")).lower() for gp in merged.game_pieces or []}
    add("game_piece.cone", any("cone" in n for n in names), f"got {names}")
    add("game_piece.cube", any("cube" in n for n in names), f"got {names}")

    # Possession 1
    pl = merged.possession_limits or {}
    add("possession.max=1", pl.get("max_simultaneous") == 1, f"got {pl}")

    # RPs: sustainability + activation
    rp_names = " ".join(str(r.get("name", "")).lower() for r in merged.ranking_points or [])
    add("rp.sustainability", "sustainability" in rp_names or "grid" in rp_names, f"got {rp_names}")
    add("rp.activation", "activation" in rp_names or "engage" in rp_names, f"got {rp_names}")

    # Weight 125lb
    cc = merged.critical_constraints or {}
    w = cc.get("weight_lbs")
    add("weight=125lb", w is not None and abs(float(w) - 125.0) < 0.5, f"got {w}")

    return checks


# --- 2024 Crescendo ---------------------------------------------------------


def _checks_2024(merged: ManualParse) -> list:
    auto = _phase(merged, "auto")
    teleop = _phase(merged, "teleop")
    end = _phase(merged, "endgame")

    checks: list = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # Auto AMP=2, SPEAKER=5
    e = find_pts(auto, ["amp"])
    ok, d = _eq_pts(e, 2)
    add("auto.amp=2", ok, d)
    e = find_pts(auto, ["speaker"])
    ok, d = _eq_pts(e, 5)
    add("auto.speaker=5", ok, d)

    # Teleop AMP=1, SPEAKER=2, amplified SPEAKER=5
    e = find_pts(teleop, ["amp"])
    # Filter out amplified-speaker entries that mention "amp" only because of "amplified"
    if e is not None and "speaker" in str(e.get("name", "")).lower():
        e = find_pts(teleop, ["amp", "note"]) or find_pts(teleop, ["amp"], require_all=True)
    ok, d = _eq_pts(e, 1)
    add("teleop.amp=1", ok, d)

    e = find_pts(teleop, ["speaker"])
    # Filter: must not be amplified
    if e is not None and "amplif" in str(e.get("name", "")).lower():
        # find a non-amplified speaker entry
        e = next(
            (x for x in teleop
             if "speaker" in str(x.get("name", "")).lower()
             and "amplif" not in str(x.get("name", "")).lower()),
            None,
        )
    ok, d = _eq_pts(e, 2)
    add("teleop.speaker=2", ok, d)

    e = find_pts(teleop, ["amplified", "speaker"]) or find_pts(teleop, ["amplified"])
    ok, d = _eq_pts(e, 5)
    add("teleop.amplified_speaker=5", ok, d)

    # Auto LEAVE=2
    e = find_pts(auto, ["leave"]) or find_pts(auto + end, ["leave"])
    ok, d = _eq_pts(e, 2)
    add("auto.leave=2", ok, d)

    # Endgame PARK=1, ONSTAGE=3, SPOTLIT=+1
    e = find_pts(end, ["park"])
    ok, d = _eq_pts(e, 1)
    add("endgame.park=1", ok, d)
    e = find_pts(end, ["onstage"])
    ok, d = _eq_pts(e, 3)
    add("endgame.onstage=3", ok, d)
    e = find_pts(end, ["spotlit"]) or find_pts(end, ["spotlight"])
    ok, d = _eq_pts(e, 1)
    add("endgame.spotlit=1", ok, d)

    # Game piece: NOTE
    names = {str(gp.get("name", "")).lower() for gp in merged.game_pieces or []}
    add("game_piece.note", any("note" in n for n in names), f"got {names}")

    # Possession 1
    pl = merged.possession_limits or {}
    add("possession.max=1", pl.get("max_simultaneous") == 1, f"got {pl}")

    # RPs: melody + ensemble
    rp_names = " ".join(str(r.get("name", "")).lower() for r in merged.ranking_points or [])
    add("rp.melody", "melody" in rp_names, f"got {rp_names}")
    add("rp.ensemble", "ensemble" in rp_names, f"got {rp_names}")

    # Weight 125lb
    cc = merged.critical_constraints or {}
    w = cc.get("weight_lbs")
    add("weight=125lb", w is not None and abs(float(w) - 125.0) < 0.5, f"got {w}")

    return checks


# Registry. Add 2025/2026 here once ground truth is written.
GROUND_TRUTH: dict = {
    2019: {
        "default_manual": "manuals/2019_deep_space.pdf",
        "checks": _checks_2019,
        "label": "Deep Space",
    },
    2023: {
        "default_manual": "manuals/2023_charged_up.pdf",
        "checks": _checks_2023,
        "label": "Charged Up",
    },
    2024: {
        "default_manual": "manuals/2024_crescendo.pdf",
        "checks": _checks_2024,
        "label": "Crescendo",
    },
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _require_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set. Export it before running:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(2)


def _instrumented_parse_fn(usage_log: list) -> Callable[[str, str], dict]:
    """Return a parse_fn that also records token usage per call."""
    from anthropic import Anthropic  # noqa: I001

    client = Anthropic()

    def fn(manual_text: str, model: str) -> dict:
        prompt = PROMPT_TEMPLATE.format(
            schema=JSON_SCHEMA_DESCRIPTION,
            text=manual_text[:120_000],
        )
        t0 = time.time()
        resp = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - t0
        raw = "".join(getattr(b, "text", "") for b in resp.content)
        usage_log.append(
            {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "elapsed_s": elapsed,
            }
        )
        return _coerce_json(raw)

    return fn


def _score(merged: ManualParse, year: int) -> dict:
    checks = GROUND_TRUTH[year]["checks"](merged)
    passed = sum(1 for c in checks if c["ok"])
    return {"checks": checks, "passed": passed, "total": len(checks)}


def run(year: int, manual_path: Optional[str] = None) -> int:
    _require_api_key()
    spec = GROUND_TRUTH.get(year)
    if spec is None:
        print(
            f"ERROR: no ground truth registered for year {year}. "
            f"Known years: {sorted(GROUND_TRUTH.keys())}",
            file=sys.stderr,
        )
        return 2

    pdf_path = Path(manual_path) if manual_path else REPO / spec["default_manual"]
    if not pdf_path.exists():
        print(f"ERROR: PDF not found at {pdf_path}", file=sys.stderr)
        return 2

    print(f"[+] Year: {year} ({spec['label']})")
    print(f"[+] PDF: {pdf_path} ({pdf_path.stat().st_size / 1e6:.1f} MB)")
    text = extract_pdf_text(str(pdf_path))
    print(f"[+] Extracted {len(text):,} chars from PDF")

    usage_log: list = []
    parse_fn = _instrumented_parse_fn(usage_log)

    print(f"[+] Running {N_PARSES} parses with {MODEL}...")
    parses = parse_manual(
        str(pdf_path), n_parses=N_PARSES, model=MODEL, parse_fn=parse_fn
    )

    merged, report = consensus(parses)
    print(
        f"[+] Consensus: locked={len(report.locked_fields)} "
        f"tentative={len(report.tentative_fields)} "
        f"ambiguous={len(report.ambiguous_fields)}"
    )

    acc = _score(merged, year)
    print(f"\n=== Per-field accuracy: {acc['passed']}/{acc['total']} ===")
    for c in acc["checks"]:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']} — {c['detail']}")

    total_in = sum(u["input_tokens"] for u in usage_log)
    total_out = sum(u["output_tokens"] for u in usage_log)
    cost = (total_in / 1e6) * HAIKU_INPUT_PER_MTOK + (total_out / 1e6) * HAIKU_OUTPUT_PER_MTOK
    print(f"\n=== Tokens: in={total_in:,} out={total_out:,} === est cost ${cost:.4f}")

    summary: dict[str, Any] = {
        "year": year,
        "label": spec["label"],
        "model": MODEL,
        "n_parses": N_PARSES,
        "locked": len(report.locked_fields),
        "tentative": len(report.tentative_fields),
        "ambiguous": len(report.ambiguous_fields),
        "accuracy": acc,
        "usage": usage_log,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "cost_usd": cost,
    }
    out_path = REPO / "design-intelligence" / f"_{year}_validation_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n[+] Wrote summary -> {out_path}")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        choices=sorted(GROUND_TRUTH.keys()),
        help="Season year to validate.",
    )
    parser.add_argument(
        "--manual",
        type=str,
        default=None,
        help="Path to manual PDF (defaults to manuals/{year}_{label}.pdf).",
    )
    args = parser.parse_args(argv)
    return run(args.year, args.manual)


if __name__ == "__main__":
    sys.exit(main())
