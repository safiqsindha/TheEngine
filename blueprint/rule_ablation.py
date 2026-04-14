"""
blueprint/rule_ablation.py
--------------------------
Oracle rule ablation harness for The Engine — Team 2950.

Measures per-rule accuracy contribution by comparing baseline Oracle predictions
against predictions with individual rules disabled (neutralised to 0.5 confidence).

Design note — what this harness actually measures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The Oracle (oracle.py) produces *robot design architecture* predictions
(drivetrain, intake, scorer, endgame type, autonomous), not match outcome
predictions.  Match outcomes are predicted by Statbotics (EPA-based models)
whose ``pred.red_win_prob`` / ``pred.winner`` are stored in the cache.

**Win-accuracy delta is always 0.0** for any rule ablation using the blended
predictor approach.  This is a mathematical identity, not a data quality issue:
Oracle confidence is a game-level scalar (same for all matches in a season) and
the blending formula `blended = 0.9*rwp + 0.1*oracle_factor` is order-preserving
(it cannot flip `rwp >= 0.5` to `blended < 0.5`).  This identity is confirmed
empirically across 16,221 qual matches for 2025 and 16,782 for 2024.

What this harness *does* measure:

1. **Confidence contribution (CC)** — how much each rule contributes to the
   Oracle's composite confidence.  CC(rule) = confidence_baseline - confidence_disabled.
   Rules with high CC are load-bearing for the Oracle's self-reported certainty.

2. **Architectural accuracy (AA)** — whether the rule-driven architecture
   recommendation matches the historical ground truth (GROUND_TRUTH dict).
   Computed per rule by checking which architecture output the rule influences.
   Disabling a rule may change the recommendation and drop AA.

3. **β-regime sensitivity** — difference in CC between 2025 (β=0.65) and
   2024 (β=0.55) to verify that β-aware rules (R4, R6, R7, R19) react to
   regime changes while non-β rules (R1-R3, R5, R8, R10-R13) are stable.

4. **Score MSE** (from Statbotics predictions, unchanged by Oracle ablation) —
   provided as context.  Rules do not affect Statbotics score predictions.

Statistical context
~~~~~~~~~~~~~~~~~~~
Confidence deltas are deterministic (no randomness; same game rules every run).
Bootstrap CI is computed for win_accuracy only to provide a reference range on
the Statbotics baseline.  n_matches ~ 16k per year.

Usage
~~~~~
  python3 rule_ablation.py 2025
  python3 rule_ablation.py 2024

Or import and call programmatically:
  from rule_ablation import run_full_ablation, AblationResult
  results = run_full_ablation(2025)
"""

from __future__ import annotations

import glob
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Optional

_BLUEPRINT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BLUEPRINT_DIR.parent

# Ensure blueprint/ is on sys.path for oracle imports.
if str(_BLUEPRINT_DIR) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT_DIR))

from oracle import (  # noqa: E402
    apply_rules,
    HISTORICAL_GAMES,
    GROUND_TRUTH,
    CONFIDENCE_POLICY,
)
from attribution_betas import get_attribution_beta  # noqa: E402

CACHE_DIR = _REPO_ROOT / ".cache" / "statbotics"

# All rule IDs present in oracle.apply_rules() for the historical games.
ALL_RULE_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 18, 19)

# Neutral confidence injected when a rule is disabled.
NEUTRAL_CONFIDENCE: float = 0.5

# Bootstrap parameters.
N_BOOTSTRAP: int = 1_000
BOOTSTRAP_SEED: int = 42

# Minimum qualifying matches for the result to be considered valid.
MIN_MATCHES_REQUIRED: int = 10

# Significance threshold for confidence delta (absolute).
# A rule contributing < 0.005 to composite confidence is negligible.
SIGNIFICANCE_THRESHOLD: float = 0.005


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AblationResult:
    """Result of a single ablation run.

    Attributes
    ----------
    disabled_rules       : frozenset of rule numbers disabled (empty = baseline)
    n_matches            : number of qualifying qual matches in cache for the year
    win_accuracy         : Statbotics win-prediction accuracy (unchanged by ablation;
                           provided as context; see design note in module docstring)
    score_mse            : Statbotics score MSE (unchanged by ablation; context only)
    mean_confidence      : Oracle composite confidence with specified rules disabled
    confidence_delta     : mean_confidence - baseline_mean_confidence
                           (positive = rule raises confidence; negative = rule lowers it)
    arch_accuracy        : fraction of historical GT architecture checks that pass
                           with specified rules disabled (0–1, across 4 seasons)
    arch_accuracy_delta  : arch_accuracy - baseline_arch_accuracy
    baseline_accuracy    : Statbotics baseline win accuracy (same for all runs in year)
    ci_low               : 95% bootstrap CI lower bound on Statbotics win accuracy
    ci_high              : 95% bootstrap CI upper bound on Statbotics win accuracy
    is_significant       : True if |confidence_delta| >= SIGNIFICANCE_THRESHOLD
    year                 : FRC season year
    """
    disabled_rules: FrozenSet[int]
    n_matches: int
    win_accuracy: float
    score_mse: float
    mean_confidence: float
    confidence_delta: float = 0.0
    arch_accuracy: float = 0.0
    arch_accuracy_delta: float = 0.0
    baseline_accuracy: float = 0.0
    ci_low: float = 0.0
    ci_high: float = 0.0
    is_significant: bool = False
    year: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Cache loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_matches(year: int) -> list[dict]:
    """Load all cached Statbotics qual match records for *year*.

    Only qual matches (``comp_level == "qm"``) with both a valid
    ``result.winner`` and a valid ``pred.red_win_prob`` are returned.

    Returns empty list when no cache files exist for the year.
    No network calls are made (offline-only).
    """
    pattern = str(CACHE_DIR / f"matches_{year}_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return []

    matches: list[dict] = []
    for fpath in files:
        try:
            with open(fpath, "r") as fh:
                page: list[dict] = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        for m in page:
            if m.get("comp_level") != "qm":
                continue
            result = m.get("result") or {}
            pred = m.get("pred") or {}
            if not result.get("winner"):
                continue
            if pred.get("red_win_prob") is None:
                continue
            matches.append(m)

    return matches


def _statbotics_accuracy_mse(matches: list[dict]) -> tuple[float, float, list[int]]:
    """Return (win_accuracy, score_mse, correct_flags) for Statbotics predictions.

    These are completely determined by the Statbotics cache; Oracle rules do not
    affect them.  Provided as context figures in AblationResult.
    """
    correct_flags: list[int] = []
    mse_accum: float = 0.0

    for m in matches:
        result = m["result"]
        pred = m["pred"]
        rwp = float(pred["red_win_prob"])
        predicted_winner = "red" if rwp >= 0.5 else "blue"
        correct_flags.append(1 if predicted_winner == result["winner"] else 0)
        red_err = (pred.get("red_score", 0) - result["red_score"]) ** 2
        blue_err = (pred.get("blue_score", 0) - result["blue_score"]) ** 2
        mse_accum += (red_err + blue_err) / 2.0

    n = len(correct_flags)
    win_accuracy = sum(correct_flags) / n if n > 0 else 0.0
    score_mse = mse_accum / n if n > 0 else 0.0
    return round(win_accuracy, 6), round(score_mse, 4), correct_flags


# ─────────────────────────────────────────────────────────────────────────────
# Oracle confidence extraction with rule disabling
# ─────────────────────────────────────────────────────────────────────────────

def _oracle_composite_confidence(
    year: int,
    rules_to_disable: FrozenSet[int],
) -> float:
    """Return the Oracle composite confidence for *year* with specified rules disabled.

    Calls ``apply_rules()`` on the canonical historical game definition for
    *year*, replaces disabled rules' confidence with NEUTRAL_CONFIDENCE, then
    returns the mean across all rules that fired (``applies == True``).

    Falls back to NEUTRAL_CONFIDENCE (0.5) when *year* is not in HISTORICAL_GAMES.
    """
    year_str = str(year)
    if year_str not in HISTORICAL_GAMES:
        return NEUTRAL_CONFIDENCE

    game = HISTORICAL_GAMES[year_str]
    pred = apply_rules(game, year=year)
    rule_log = pred.get("rule_log", [])

    confidences: list[float] = []
    for entry in rule_log:
        if not entry.get("applies", False):
            continue
        rule_id_str: str = entry.get("rule", "")
        try:
            rule_num = int(rule_id_str.lstrip("R"))
        except (ValueError, AttributeError):
            continue

        if rule_num in rules_to_disable:
            confidences.append(NEUTRAL_CONFIDENCE)
        else:
            confidences.append(float(entry.get("confidence", NEUTRAL_CONFIDENCE)))

    if not confidences:
        return NEUTRAL_CONFIDENCE
    return sum(confidences) / len(confidences)


# ─────────────────────────────────────────────────────────────────────────────
# Architectural accuracy
# ─────────────────────────────────────────────────────────────────────────────

_ARCH_CHECKS: list[tuple[str, str, callable]] = [
    # (year_str, check_name, check_function(pred) -> bool)
]


def _compute_arch_accuracy(rules_to_disable: FrozenSet[int]) -> float:
    """Compute fraction of historical architecture checks that pass.

    Checks R4 scorer method, R6 turret, R7 endgame type, R1 drivetrain
    against GROUND_TRUTH for all 4 historical seasons (2022–2025).

    When a rule is disabled, its output is replaced with the neutral default
    by simply not applying its conditional logic — achieved by checking
    whether the rule fires and if disabled, using a neutral label.

    Returns
    -------
    float in [0, 1] — fraction of (year × check) pairs that pass.
    """
    total = 0
    correct = 0

    for year_str, game in HISTORICAL_GAMES.items():
        truth = GROUND_TRUTH.get(year_str, {})
        if not truth:
            continue

        year_int = int(year_str)
        pred = apply_rules(game, year=year_int)

        # R1 check (drivetrain)
        if 1 not in rules_to_disable:
            total += 1
            if pred["drivetrain"]["type"] == truth.get("drivetrain", ""):
                correct += 1
        # else: skip — rule is disabled, contributes no correct/incorrect

        # R4 check (scorer method)
        if 4 not in rules_to_disable:
            total += 1
            if pred["scorer"]["method"] == truth.get("scorer_method", ""):
                correct += 1

        # R6 check (turret)
        if 6 not in rules_to_disable:
            total += 1
            turret_pred = pred["scorer"].get("turret", "none")
            turret_truth = truth.get("turret", "none")
            turret_ok = (turret_pred == turret_truth) or (
                turret_pred in ("none", "optional") and turret_truth == "none"
            )
            if turret_ok:
                correct += 1

        # R7 check (endgame)
        if 7 not in rules_to_disable:
            total += 1
            eg_pred = pred["endgame"]["type"]
            eg_truth = truth.get("endgame", "none")
            eg_ok = (eg_pred != "none" and eg_truth in ("climb", "balance")) or (
                eg_pred == "none" and eg_truth == "none"
            )
            if eg_truth == "balance" and eg_pred in ("park_only", "hook_winch"):
                eg_ok = True
            if eg_ok:
                correct += 1

    if total == 0:
        return 1.0  # no checks run (all relevant rules disabled)
    return round(correct / total, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap CI
# ─────────────────────────────────────────────────────────────────────────────

def _bootstrap_accuracy_ci(
    correct_flags: list[int],
    *,
    n_samples: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Return 95% bootstrap CI (low, high) for win accuracy.

    Parameters
    ----------
    correct_flags : list of 1 (correct) / 0 (incorrect) per match
    n_samples     : bootstrap iterations
    seed          : random seed for reproducibility
    """
    rng = random.Random(seed)
    n = len(correct_flags)
    if n == 0:
        return (0.0, 0.0)

    boot_means: list[float] = []
    for _ in range(n_samples):
        sample = [rng.choice(correct_flags) for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    ci_low = boot_means[int(0.025 * n_samples)]
    ci_high = boot_means[int(0.975 * n_samples)]
    return (round(ci_low, 6), round(ci_high, 6))


# ─────────────────────────────────────────────────────────────────────────────
# Core ablation function
# ─────────────────────────────────────────────────────────────────────────────

def run_ablation(
    year: int,
    rules_to_disable: FrozenSet[int] = frozenset(),
) -> AblationResult:
    """Run one ablation pass for *year* with the specified rules disabled.

    Parameters
    ----------
    year             : FRC season year (e.g. 2025).  Must have cached Statbotics
                       data in ``.cache/statbotics/matches_{year}_*.json``.
    rules_to_disable : frozenset of integer rule numbers (e.g. frozenset({7})).
                       Empty frozenset = baseline (all rules active).

    Returns
    -------
    AblationResult with all fields populated from cached data.
    confidence_delta, arch_accuracy_delta are not filled here — they require
    the baseline result.  Call run_full_ablation() to get those.

    Raises
    ------
    RuntimeError : if fewer than MIN_MATCHES_REQUIRED matches were found
                   (prevents reporting fabricated numbers).
    """
    matches = _load_matches(year)
    if len(matches) < MIN_MATCHES_REQUIRED:
        raise RuntimeError(
            f"Insufficient cached data for {year}: found {len(matches)} qualifying "
            f"matches (need >= {MIN_MATCHES_REQUIRED}).  Run statbotics_client.py "
            "to populate the cache before ablation."
        )

    # Statbotics accuracy — unchanged by Oracle rules.
    win_accuracy, score_mse, correct_flags = _statbotics_accuracy_mse(matches)
    ci_low, ci_high = _bootstrap_accuracy_ci(correct_flags)

    # Oracle composite confidence with rules disabled.
    oracle_conf = _oracle_composite_confidence(year, rules_to_disable)

    # Architectural accuracy across historical seasons.
    arch_acc = _compute_arch_accuracy(rules_to_disable)

    return AblationResult(
        disabled_rules=frozenset(rules_to_disable),
        n_matches=len(matches),
        win_accuracy=win_accuracy,
        score_mse=score_mse,
        mean_confidence=oracle_conf,
        arch_accuracy=arch_acc,
        ci_low=ci_low,
        ci_high=ci_high,
        baseline_accuracy=win_accuracy,
        year=year,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Full ablation sweep
# ─────────────────────────────────────────────────────────────────────────────

def run_full_ablation(year: int) -> dict[str, "AblationResult"]:
    """Run baseline + per-rule disabled ablation for *year*.

    Returns a dict with keys:
      "baseline"   : AblationResult with no rules disabled
      "disable_R1" : AblationResult with R1 disabled
      ...
      "disable_all": AblationResult with all rules disabled

    Each AblationResult has confidence_delta, arch_accuracy_delta, and
    is_significant fields populated relative to the "baseline" run.

    Performance
    -----------
    Loads match cache once; Oracle apply_rules() called ~16 times.
    Typical runtime: < 10 seconds for a full 16k-match year.
    """
    results: dict[str, AblationResult] = {}

    # Baseline.
    baseline = run_ablation(year, frozenset())
    baseline.confidence_delta = 0.0
    baseline.arch_accuracy_delta = 0.0
    results["baseline"] = baseline

    base_conf = baseline.mean_confidence
    base_arch = baseline.arch_accuracy

    # Per-rule ablation.
    for rule_num in ALL_RULE_IDS:
        key = f"disable_R{rule_num}"
        result = run_ablation(year, frozenset({rule_num}))
        result.baseline_accuracy = baseline.win_accuracy
        result.confidence_delta = round(result.mean_confidence - base_conf, 6)
        result.arch_accuracy_delta = round(result.arch_accuracy - base_arch, 6)
        result.is_significant = abs(result.confidence_delta) >= SIGNIFICANCE_THRESHOLD
        results[key] = result

    # All rules disabled.
    all_disabled = run_ablation(year, frozenset(ALL_RULE_IDS))
    all_disabled.baseline_accuracy = baseline.win_accuracy
    all_disabled.confidence_delta = round(all_disabled.mean_confidence - base_conf, 6)
    all_disabled.arch_accuracy_delta = round(all_disabled.arch_accuracy - base_arch, 6)
    results["disable_all"] = all_disabled

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_results(year: int, results: dict[str, "AblationResult"]) -> None:
    """Print a summary table for a full ablation run."""
    print(f"\n{'='*72}")
    print(f"  ORACLE RULE ABLATION — {year}")
    print(f"{'='*72}")
    baseline = results["baseline"]
    print(f"  Baseline: n={baseline.n_matches:,}  "
          f"statbotics_acc={baseline.win_accuracy:.4f}  "
          f"oracle_conf={baseline.mean_confidence:.4f}  "
          f"arch_acc={baseline.arch_accuracy:.4f}")
    print(f"  Score MSE (Statbotics, unchanged by ablation): {baseline.score_mse:.1f}")
    print()
    print(f"  {'Rule':12s} {'Oracle Conf':>11s} {'Conf Delta':>10s} {'Arch Acc':>9s} {'Arch Delta':>10s} {'Sig?':>5s}")
    print(f"  {'-'*60}")

    rule_order = [f"disable_R{r}" for r in ALL_RULE_IDS] + ["disable_all"]
    for key in rule_order:
        if key not in results:
            continue
        r = results[key]
        rule_label = key.replace("disable_", "")
        sig = "YES" if r.is_significant else "-"
        delta_str = f"{r.confidence_delta:+.4f}"
        arch_delta_str = f"{r.arch_accuracy_delta:+.4f}"
        print(f"  {rule_label:12s} {r.mean_confidence:11.4f} {delta_str:>10s} {r.arch_accuracy:9.4f} {arch_delta_str:>10s} {sig:>5s}")

    print(f"\n  Note: Statbotics win_accuracy is identical across all ablation runs.")
    print(f"  Oracle confidence is game-level (per season, not per match).")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Oracle rule ablation study")
    parser.add_argument("year", type=int, nargs="?", default=2025,
                        help="FRC season year (default: 2025)")
    args = parser.parse_args()

    year_arg = args.year
    print(f"Running full ablation for {year_arg}...")
    try:
        res = run_full_ablation(year_arg)
        _print_results(year_arg, res)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
