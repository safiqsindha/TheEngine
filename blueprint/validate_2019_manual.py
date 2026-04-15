"""Historical validation of manual_parser.py against the 2019 Deep Space manual.

One-shot driver. Runs 3 Haiku 4.5 parses over the 2019 FRC Deep Space game
manual PDF, runs consensus, compares the merged parse against the hand-coded
Deep Space ground truth, and prints a validation report.

Usage::

    export ANTHROPIC_API_KEY=sk-ant-...
    python blueprint/validate_2019_manual.py

Guardrail: exits non-zero with a clear error if ANTHROPIC_API_KEY is unset.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from blueprint.manual_parser import (  # noqa: E402
    JSON_SCHEMA_DESCRIPTION,
    PROMPT_TEMPLATE,
    ManualParse,
    consensus,
    extract_pdf_text,
    parse_manual,
    validate_parse_dict,
    _coerce_json,
)

PDF_PATH = REPO / "manuals" / "2019_deep_space.pdf"
MODEL = "claude-haiku-4-5"
N_PARSES = 3

# Haiku 4.5 pricing (USD per 1M tokens) — update if pricing changes.
HAIKU_INPUT_PER_MTOK = 1.00
HAIKU_OUTPUT_PER_MTOK = 5.00

# Ground truth for 2019 Deep Space.
GROUND_TRUTH = {
    "auto": {
        "cargo_cargo_ship": 3,
        "hatch_cargo_ship": 2,
        "hab_cross_l1": 3,
        "hab_cross_l2": 6,
    },
    "teleop": {
        "cargo_cargo_ship": 3,
        "cargo_rocket": 3,
        "hatch_rocket": 2,
        "hatch_cargo_ship": 2,
    },
    "endgame": {
        "hab_climb_l1": 3,
        "hab_climb_l2": 6,
        "hab_climb_l3": 12,
    },
    "game_pieces": {"cargo", "hatch panel"},
    "possession_max": 1,
    "ranking_points": {"rocket", "hab", "win", "tie"},
    "robot_weight_lbs": 125.0,
}


def _require_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set. Export it before running:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(2)


def _instrumented_parse_fn(usage_log: list):
    """Return a parse_fn that also records token usage per call."""
    from anthropic import Anthropic

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


def _find_action(entries: list, needles: list) -> dict | None:
    """Find first entry whose normalized name contains ALL needle tokens."""
    for e in entries or []:
        name = str(e.get("name", "")).lower()
        loc = str(e.get("location", "")).lower()
        blob = f"{name} {loc}"
        if all(n in blob for n in needles):
            return e
    return None


def _score_accuracy(merged: ManualParse) -> dict:
    """Per-field accuracy vs ground truth. Returns pass/fail breakdown."""
    results: dict = {"checks": [], "passed": 0, "total": 0}

    def check(name: str, ok: bool, detail: str = "") -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        results["total"] += 1
        if ok:
            results["passed"] += 1

    auto = merged.scoring.get("auto", []) or []
    teleop = merged.scoring.get("teleop", []) or []
    end = merged.scoring.get("endgame", []) or []

    # --- Auto
    e = _find_action(auto, ["cargo", "cargo ship"])
    check("auto.cargo_in_cargo_ship=3", e is not None and e.get("points") == 3,
          f"got {e}")
    e = _find_action(auto, ["hatch", "cargo ship"])
    check("auto.hatch_on_cargo_ship=2", e is not None and e.get("points") == 2,
          f"got {e}")
    e = _find_action(auto + end, ["hab", "level 1"]) or _find_action(auto + end, ["hab", "l1"])
    check("auto.hab_cross_l1=3", e is not None and e.get("points") == 3,
          f"got {e}")
    e = _find_action(auto + end, ["hab", "level 2"]) or _find_action(auto + end, ["hab", "l2"])
    check("auto.hab_cross_l2=6", e is not None and e.get("points") == 6,
          f"got {e}")

    # --- Teleop
    e = _find_action(teleop, ["cargo", "cargo ship"])
    check("teleop.cargo_in_cargo_ship=3", e is not None and e.get("points") == 3, f"got {e}")
    e = _find_action(teleop, ["cargo", "rocket"])
    check("teleop.cargo_in_rocket=3", e is not None and e.get("points") == 3, f"got {e}")
    e = _find_action(teleop, ["hatch", "rocket"])
    check("teleop.hatch_in_rocket=2", e is not None and e.get("points") == 2, f"got {e}")
    e = _find_action(teleop, ["hatch", "cargo ship"])
    check("teleop.hatch_in_cargo_ship=2", e is not None and e.get("points") == 2, f"got {e}")

    # --- Endgame climb
    e = _find_action(end, ["level 3"]) or _find_action(end, ["l3"])
    check("endgame.hab_climb_l3=12", e is not None and e.get("points") == 12, f"got {e}")
    e = _find_action(end, ["level 2"]) or _find_action(end, ["l2"])
    check("endgame.hab_climb_l2=6", e is not None and e.get("points") == 6, f"got {e}")
    e = _find_action(end, ["level 1"]) or _find_action(end, ["l1"])
    check("endgame.hab_climb_l1=3", e is not None and e.get("points") == 3, f"got {e}")

    # --- Game pieces
    names = {str(gp.get("name", "")).lower() for gp in merged.game_pieces or []}
    check("game_piece.cargo", any("cargo" in n for n in names), f"got {names}")
    check("game_piece.hatch", any("hatch" in n for n in names), f"got {names}")

    # --- Possession
    pl = merged.possession_limits or {}
    check("possession.max=1", pl.get("max_simultaneous") == 1, f"got {pl}")

    # --- RPs
    rp_names = " ".join(str(r.get("name", "")).lower() for r in merged.ranking_points or [])
    check("rp.rocket", "rocket" in rp_names, f"got {rp_names}")
    check("rp.hab", "hab" in rp_names or "climb" in rp_names, f"got {rp_names}")

    # --- Constraints
    cc = merged.critical_constraints or {}
    w = cc.get("weight_lbs")
    check("weight=125lb", w is not None and abs(float(w) - 125.0) < 0.5, f"got {w}")

    return results


def main() -> int:
    _require_api_key()

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}", file=sys.stderr)
        return 2

    print(f"[+] PDF: {PDF_PATH} ({PDF_PATH.stat().st_size / 1e6:.1f} MB)")
    text = extract_pdf_text(str(PDF_PATH))
    print(f"[+] Extracted {len(text):,} chars from PDF")

    usage_log: list = []
    parse_fn = _instrumented_parse_fn(usage_log)

    print(f"[+] Running {N_PARSES} parses with {MODEL}...")
    parses = parse_manual(
        str(PDF_PATH), n_parses=N_PARSES, model=MODEL, parse_fn=parse_fn
    )

    merged, report = consensus(parses)
    print(f"[+] Consensus: locked={len(report.locked_fields)} "
          f"tentative={len(report.tentative_fields)} "
          f"ambiguous={len(report.ambiguous_fields)}")

    acc = _score_accuracy(merged)
    print(f"\n=== Per-field accuracy: {acc['passed']}/{acc['total']} ===")
    for c in acc["checks"]:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']} — {c['detail']}")

    total_in = sum(u["input_tokens"] for u in usage_log)
    total_out = sum(u["output_tokens"] for u in usage_log)
    cost = (total_in / 1e6) * HAIKU_INPUT_PER_MTOK + (total_out / 1e6) * HAIKU_OUTPUT_PER_MTOK
    print(f"\n=== Tokens: in={total_in:,} out={total_out:,} === est cost ${cost:.4f}")

    # Emit machine-readable summary JSON for the report writer.
    summary = {
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
    out_path = REPO / "design-intelligence" / "_2019_validation_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n[+] Wrote summary → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
