"""
blueprint/fit_rulebook_regression.py
--------------------------------------
One-shot script: fit ridge regression from game manual signals -> empirical β*.
Run from the TheEngine root:

    python3 blueprint/fit_rulebook_regression.py

Outputs:
  - Fitted coefficients (printed to stdout)
  - Leave-one-out validation table (printed to stdout)
  - Saves signal JSON to .cache/manuals/ for audit trail

Signal extraction approach:
  For each season, signals were extracted from game manual summaries fetched from
  Wikipedia (fetched 2026-04-14). Because summary texts are ~400 words (far shorter
  than actual PDFs which run 50–100k words), raw regex density estimates are unreliable.
  Expert-assigned signals are used instead, derived from the fetched Wikipedia content
  plus documented game mechanics knowledge. Each value is documented with its source.

  Key: has_coop_rp is True only when a co-op/coopertition RP exists that requires
  *intra-ALLIANCE* robot coordination (not cross-alliance coopertition).
  Handoff verb density is estimated as occurrences-per-1k-words in a ~100k word manual
  (scaled from Wikipedia descriptions of handoff importance).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BLUEPRINT_DIR = _ROOT / "blueprint"
_CACHE_DIR = _ROOT / ".cache" / "manuals"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from rulebook_beta_prior import RulebookSignals  # noqa: E402


# ---------------------------------------------------------------------------
# Empirical β* labels from attribution_betas.py (Item 1, commit 58a37cf)
# ---------------------------------------------------------------------------
EMPIRICAL_BETAS: dict[int, float] = {
    2013: 0.60,   # Ultimate Ascent
    2014: 0.95,   # Aerial Assist (counter-intuitive: pass bonus inflated individual stats)
    2016: 1.00,   # Stronghold    (empirical linear despite role specialization)
    2017: 0.85,   # Steamworks
    2018: 0.80,   # Power Up
    2020: 1.00,   # Infinite Recharge (abbreviated season)
    2022: 0.95,   # Rapid React
    2023: 0.65,   # Charged Up
    2024: 0.55,   # Crescendo
    2025: 0.65,   # Reefscape
}

EXCLUDED = {
    2015: "empirical_beta=None (Recycle Rush Statbotics tuning failed)",
    2019: "per-phase β only (cycle/climb split); no single overall empirical β available",
}

# ---------------------------------------------------------------------------
# Expert-assigned signals per season
#
# Source: Wikipedia summaries fetched 2026-04-14 + documented game knowledge.
# Handoff verb density scaled to approximate occurrences-per-1k-words in a
# full (~60k word) game manual. Real manual PDFs would give precise numbers;
# these estimates encode the *relative* coupling intensity across seasons.
#
# Calibration anchors (from fetched content):
#   - 2014 Aerial Assist: highest handoff density — multi-robot assist chain
#   - 2015 Recycle Rush: lowest handoff density — robots score independently
#   - 2016 Stronghold: high handoff — HUMAN PLAYER feeds boulders to ROBOTs
#   - 2023 Charged Up: low handoff — SUBSTATION delivery, no robot-to-robot
#
# alliance_scope_ratio: fraction of scoring clauses that reference ALLIANCE
#   rather than individual ROBOT. Estimated from game scoring descriptions.
#
# named_feeder_zones: count of distinctly named loading/feeder zones.
#   Cross-checked against Wikipedia fetched content.
#
# has_possession_limit: True only when per-robot limit is explicitly stated
#   (e.g., 2016: 1 boulder, 2017: 1 gear, 2024: 1 NOTE).
#
# has_coop_rp: True when an intra-alliance bonus RP requires all 3 robots to
#   coordinate (e.g., 2018 Auto Quest / Face the Boss, 2015 Coopertition).
#   NOTE: Cross-alliance COOPERTITION is NOT scored here — it's a different
#   signal (reduces field coupling, not increases it).
#
# h_rule_count: approximate H-rule count from manual structure. Real manuals
#   have ~10-25 H-rules. Estimated from complexity of defense descriptions.
# ---------------------------------------------------------------------------
EXPERT_SIGNALS: dict[int, dict] = {
    2013: {
        # Ultimate Ascent: frisbee shooting, pyramid climb, HUMAN PLAYER throws in final 30s
        # Alliance coupling: moderate (shared shooting zones, aggregate alliance score)
        # Source: Wikipedia 2013 FRC, fetched 2026-04-14
        "handoff_verb_density": 0.5,   # minimal robot-to-robot handoff; HP throws at end
        "alliance_scope_ratio": 0.55,  # alliance wins on total score; per-robot disc limits
        "named_feeder_zones": 1,       # HUMAN PLAYER STATION only; no named SOURCE/LOADING
        "has_possession_limit": True,  # 2-3 disc limit per robot at start
        "has_coop_rp": False,          # no co-op ranking point
        "h_rule_count": 8,             # moderate defense rules for a shooting game
        "source": "Wikipedia (fetched 2026-04-14)",
        "note": "Possession limit at match start only; no refill possession limit during play",
    },
    2014: {
        # Aerial Assist: multi-robot pass chain, assist bonuses, HUMAN PLAYER ball delivery
        # Most mechanically coupled game in FRC history (pass -> throw -> catch -> score chain)
        # Source: Wikipedia 2014 FRC, fetched 2026-04-14
        "handoff_verb_density": 3.5,   # pass, hand off, deliver, transfer, feed central to game
        "alliance_scope_ratio": 0.70,  # assist chain = alliance-level scoring; high coupling
        "named_feeder_zones": 1,       # HUMAN PLAYER STATION; no other named zones
        "has_possession_limit": False, # preload 1 ball; no explicit in-play limit stated
        "has_coop_rp": False,          # no co-op RP (assist bonus != co-op RP)
        "h_rule_count": 10,            # goalie zone rules, contact rules
        "source": "Wikipedia (fetched 2026-04-14)",
        "note": "Assist chain mechanic is primary inter-robot coupling; no explicit coop RP",
    },
    2016: {
        # Stronghold: HUMAN PLAYER feeds boulders, 1 boulder possession limit, role specialization
        # Shooter + feeder + crosser roles; HUMAN PLAYER feeds through secret passage
        # Source: Wikipedia FIRST Stronghold, fetched 2026-04-14
        "handoff_verb_density": 2.0,   # feed verbs central: HP feeds boulders through passage
        "alliance_scope_ratio": 0.65,  # breach/capture are alliance-level; robot scores boulders
        "named_feeder_zones": 2,       # Secret Passage + Human Player Station
        "has_possession_limit": True,  # 1 boulder per robot explicitly stated
        "has_coop_rp": False,          # no co-op RP (breach/capture are alliance-internal)
        "h_rule_count": 15,            # defense-heavy game with obstacle crossing rules
        "source": "Wikipedia FIRST Stronghold (fetched 2026-04-14)",
        "note": "High role specialization but empirical β=1.0 (defense game, EPA uncorrelated with coupling)",
    },
    2017: {
        # Steamworks: HUMAN PLAYER delivers gears via LOADING STATION, 1 gear possession limit
        # Fuel shooting independent; gear delivery requires HP coordination
        # Source: Wikipedia FIRST Steamworks, fetched 2026-04-14
        "handoff_verb_density": 1.8,   # deliver/feed verbs for gear and fuel loading
        "alliance_scope_ratio": 0.60,  # all scoring alliance-level; per-robot contribution
        "named_feeder_zones": 2,       # LOADING STATION + LOADING LANE
        "has_possession_limit": True,  # 1 gear per robot explicitly stated
        "has_coop_rp": False,          # no co-op RP; rotor RP is intra-alliance performance
        "h_rule_count": 12,            # Key time-limit rule, retrieval zone contact rules
        "source": "Wikipedia FIRST Steamworks (fetched 2026-04-14)",
    },
    2018: {
        # Power Up: EXCHANGE ZONE for robot-to-HP cube transfer, vault system
        # ALLIANCE-wide switch/scale ownership; Auto Quest + Face the Boss require all 3 robots
        # Source: Wikipedia FIRST Power Up (fetched 2026-04-14)
        "handoff_verb_density": 1.2,   # deliver verbs for cube placement; exchange zone
        "alliance_scope_ratio": 0.65,  # switch/scale/vault = alliance-wide; climb = per-robot
        "named_feeder_zones": 3,       # EXCHANGE ZONE + PORTALS + POWER CUBE ZONE
        "has_possession_limit": False, # preload 1 cube; no explicit in-play possession limit
        "has_coop_rp": True,           # Auto Quest + Face the Boss require all 3 robots
        "h_rule_count": 12,            # protected zones, null territory rules
        "source": "Wikipedia FIRST Power Up (fetched 2026-04-14)",
        "note": "Auto Quest/Face the Boss are intra-alliance 3-robot coordination RPs",
    },
    2020: {
        # Infinite Recharge: LOADING BAY delivers Power Cells, Shield Generator ALLIANCE-level
        # Abbreviated season (COVID); trench run coordination moderate coupling
        # Source: Wikipedia Infinite Recharge (fetched 2026-04-14)
        "handoff_verb_density": 0.8,   # LOADING BAY delivery; moderate handoff language
        "alliance_scope_ratio": 0.55,  # Power Cell scoring alliance-level; climb per-robot
        "named_feeder_zones": 1,       # LOADING BAY only
        "has_possession_limit": False, # no explicit per-robot possession limit
        "has_coop_rp": False,          # no co-op RP; Shield Generator is performance threshold
        "h_rule_count": 8,             # standard contact rules
        "source": "Wikipedia Infinite Recharge (fetched 2026-04-14)",
        "note": "Abbreviated 2020 season; empirical β=1.0 may reflect small sample",
    },
    2022: {
        # Rapid React: TERMINALS shared by both alliances, no per-robot possession limit
        # Ball shooting game; Cargo Bonus / Hangar Bonus alliance-level
        # Source: Wikipedia Rapid React (fetched 2026-04-14)
        "handoff_verb_density": 0.6,   # TERMINAL loading; moderate handoff language
        "alliance_scope_ratio": 0.55,  # all cargo scores alliance-level; hangar per-robot
        "named_feeder_zones": 1,       # TERMINALS (shared, not per-alliance named zones)
        "has_possession_limit": False, # no explicit per-robot possession limit stated
        "has_coop_rp": False,          # no co-op RP; Cargo/Hangar are performance bonuses
        "h_rule_count": 8,             # Launch Pad protection rules
        "source": "Wikipedia Rapid React (fetched 2026-04-14)",
    },
    2023: {
        # Charged Up: SINGLE/DOUBLE SUBSTATION delivery, LINK scoring, COOPERTITION bonus
        # Grid scoring independent per robot; SUSTAINABILITY bonus via co-op
        # Source: Wikipedia Charged Up FIRST (fetched 2026-04-14)
        "handoff_verb_density": 0.5,   # SUBSTATION shelf delivery; limited handoff verbs
        "alliance_scope_ratio": 0.50,  # grid scoring per-robot; alliance total for LINK
        "named_feeder_zones": 2,       # SINGLE SUBSTATION + DOUBLE SUBSTATION
        "has_possession_limit": False, # no explicit per-robot possession limit
        "has_coop_rp": True,           # COOPERTITION/SUSTAINABILITY bonus RP exists
        "h_rule_count": 10,            # standard contact rules
        "source": "Wikipedia Charged Up FIRST (fetched 2026-04-14)",
        "note": "COOPERTITION reduces SUSTAINABILITY threshold; cross-alliance coordination",
    },
    2024: {
        # Crescendo: SOURCE delivery zones, 1 NOTE possession limit, MELODY/ENSEMBLE/COOPERTITION
        # AMPLIFIER-SPEAKER chain requires coordination; highly coupled mid-cycle
        # Source: Well-documented game (2026-04-14 knowledge)
        "handoff_verb_density": 0.8,   # SOURCE delivery; moderate handoff language
        "alliance_scope_ratio": 0.65,  # SPEAKER/AMPLIFIER scoring alliance-level
        "named_feeder_zones": 2,       # SOURCE zones (two per alliance)
        "has_possession_limit": True,  # 1 NOTE per robot explicitly stated
        "has_coop_rp": True,           # MELODY RP + COOPERTITION bonus both present
        "h_rule_count": 12,            # WING zone rules, Stage proximity restrictions
        "source": "Knowledge synthesis (Wikipedia 404; using documented game knowledge)",
        "note": "2024 Wikipedia page returned 404; mechanics well-documented in community sources",
    },
    2025: {
        # Reefscape: CORAL STATIONS + PROCESSORS named zones, per-robot possession limit
        # ALGAE staging effects create moderate coupling; no explicit COOPERTITION RP
        # Source: Wikipedia Reefscape (fetched 2026-04-14)
        "handoff_verb_density": 0.7,   # CORAL STATION delivery; PROCESSOR indirect transfer
        "alliance_scope_ratio": 0.55,  # mostly per-robot REEF scoring; BARGE shared
        "named_feeder_zones": 3,       # CORAL STATIONS + PROCESSORS + REEF (processing zones)
        "has_possession_limit": True,  # 1 CORAL + 1 ALGAE per robot stated
        "has_coop_rp": False,          # no explicit COOPERTITION RP per Wikipedia
        "h_rule_count": 10,            # BARGE proximity rules
        "source": "Wikipedia Reefscape (fetched 2026-04-14)",
    },
}


def signals_to_features(s: RulebookSignals) -> list[float]:
    """Convert RulebookSignals to a feature vector for regression."""
    return [
        s.handoff_verb_density,
        s.alliance_scope_ratio,
        float(s.named_feeder_zones),
        1.0 if s.has_possession_limit else 0.0,
        1.0 if s.has_coop_rp else 0.0,
        float(s.h_rule_count),
    ]


def dict_to_signals(d: dict) -> RulebookSignals:
    """Build RulebookSignals from expert dict."""
    return RulebookSignals(
        handoff_verb_density=d["handoff_verb_density"],
        alliance_scope_ratio=d["alliance_scope_ratio"],
        named_feeder_zones=d["named_feeder_zones"],
        has_possession_limit=d["has_possession_limit"],
        has_coop_rp=d["has_coop_rp"],
        h_rule_count=d["h_rule_count"],
    )


def ridge_fit(X: list[list[float]], y: list[float], lam: float = 0.1) -> list[float]:
    """Ridge regression via augmented normal equations.
    Returns [intercept, w1, w2, w3, w4, w5, w6]."""
    import numpy as np
    Xm = np.array(X, dtype=float)
    ym = np.array(y, dtype=float)
    n, p = Xm.shape
    Xa = np.hstack([np.ones((n, 1)), Xm])
    XtX = Xa.T @ Xa
    reg = lam * np.eye(p + 1)
    reg[0, 0] = 0.0  # don't regularize intercept
    w = np.linalg.solve(XtX + reg, Xa.T @ ym)
    return w.tolist()


def predict_from_w(w: list[float], features: list[float]) -> float:
    """Apply weight vector to features (with prepended intercept). Clamp to [0.4, 1.0]."""
    raw = w[0] + sum(w[i + 1] * f for i, f in enumerate(features))
    return float(max(0.4, min(1.0, raw)))


def leave_one_out(
    years: list[int],
    features: dict[int, list[float]],
    betas: dict[int, float],
    lam: float = 0.1,
) -> list[dict]:
    """Run leave-one-out cross-validation. Returns list of result dicts."""
    results = []
    for held_out in years:
        train_years = [y for y in years if y != held_out]
        X_train = [features[y] for y in train_years]
        y_train = [betas[y] for y in train_years]
        w = ridge_fit(X_train, y_train, lam=lam)
        pred = predict_from_w(w, features[held_out])
        actual = betas[held_out]
        results.append({
            "year": held_out,
            "predicted": round(pred, 4),
            "actual": actual,
            "abs_error": round(abs(pred - actual), 4),
        })
    return results


def compute_std_errors(
    X: list[list[float]], y: list[float], w: list[float], lam: float = 0.1
) -> list[float]:
    """Estimate coefficient std errors from ridge sandwich estimator."""
    import numpy as np
    Xm = np.array(X, dtype=float)
    ym = np.array(y, dtype=float)
    n, p = Xm.shape
    Xa = np.hstack([np.ones((n, 1)), Xm])
    wm = np.array(w)
    residuals = ym - Xa @ wm
    sigma2 = float(np.sum(residuals ** 2) / max(n - p - 1, 1))
    reg = lam * np.eye(p + 1)
    reg[0, 0] = 0.0
    XtX_reg_inv = np.linalg.inv(Xa.T @ Xa + reg)
    var_w = sigma2 * np.diag(XtX_reg_inv)
    return [float(math.sqrt(max(v, 0))) for v in var_w]


def main() -> dict:
    """Run regression and return fitted coefficients."""
    LAM = 0.1

    print("=" * 70)
    print("RULEBOOK β PRIOR — REGRESSION FIT")
    print("=" * 70)
    print()
    print("Excluded years:")
    for yr, reason in EXCLUDED.items():
        print(f"  {yr}: {reason}")
    print()

    # Build feature matrix
    fit_years = sorted(EXPERT_SIGNALS.keys())
    year_features: dict[int, list[float]] = {}

    print("Expert-assigned signals per year:")
    print(f"  {'Year':<6} {'Hnd':>6} {'Alln':>6} {'Feed':>5} {'Poss':>5} {'Coop':>5} {'Hrul':>5}")
    print("  " + "-" * 42)
    for yr in fit_years:
        sig = dict_to_signals(EXPERT_SIGNALS[yr])
        feats = signals_to_features(sig)
        year_features[yr] = feats
        print(f"  {yr:<6} {sig.handoff_verb_density:>6.2f} {sig.alliance_scope_ratio:>6.3f} "
              f"{sig.named_feeder_zones:>5} {int(sig.has_possession_limit):>5} "
              f"{int(sig.has_coop_rp):>5} {sig.h_rule_count:>5}")
    print()

    # Filter to years with empirical β*
    fit_years_w_beta = [y for y in fit_years if y in EMPIRICAL_BETAS]
    print(f"Training set: {len(fit_years_w_beta)} years: {fit_years_w_beta}")
    print()

    X = [year_features[y] for y in fit_years_w_beta]
    y_vals = [EMPIRICAL_BETAS[y] for y in fit_years_w_beta]

    # Fit full model
    w = ridge_fit(X, y_vals, lam=LAM)
    std_errors = compute_std_errors(X, y_vals, w, lam=LAM)

    feature_names = ["intercept", "handoff_verb_density", "alliance_scope_ratio",
                     "named_feeder_zones", "has_possession_limit", "has_coop_rp", "h_rule_count"]

    print(f"FITTED COEFFICIENTS (ridge λ={LAM}):")
    print(f"  {'Feature':<28} {'Coef':>10}  {'±SE':>10}  {'Direction'}")
    print("  " + "-" * 70)
    expected_signs = [None, "-", "-", "-", "-", "-", "-"]
    for name, coef, se, exp_sign in zip(feature_names, w, std_errors, expected_signs):
        if exp_sign is None:
            direction = "(intercept)"
        else:
            actual_sign = "+" if coef >= 0 else "-"
            direction = "OK" if actual_sign == exp_sign else f"UNEXPECTED (expected {exp_sign})"
        print(f"  {name:<28} {coef:>+10.4f}  {se:>10.4f}  {direction}")
    print()

    # Leave-one-out
    loo_results = leave_one_out(fit_years_w_beta, year_features, EMPIRICAL_BETAS, lam=LAM)
    mae = sum(r["abs_error"] for r in loo_results) / len(loo_results)

    print("LEAVE-ONE-OUT VALIDATION:")
    print(f"  {'Year':<6} {'Predicted':>10} {'Actual':>10} {'|Error|':>10} {'Result':>12}")
    print("  " + "-" * 54)
    for r in loo_results:
        if r["abs_error"] <= 0.10:
            flag = "PASS"
        elif r["abs_error"] <= 0.15:
            flag = "WARN (≤0.15)"
        else:
            flag = "FAIL"
        print(f"  {r['year']:<6} {r['predicted']:>10.3f} {r['actual']:>10.3f} "
              f"{r['abs_error']:>10.3f} {flag:>12}")
    print()
    print(f"  Mean Absolute Error (LOO): {mae:.4f}")
    print()

    # In-sample predictions (for sanity check)
    print("IN-SAMPLE PREDICTIONS (full model on all training data):")
    print(f"  {'Year':<6} {'Fitted':>10} {'Actual':>10} {'|Resid|':>10}")
    print("  " + "-" * 40)
    in_sample_errors = []
    for yr in fit_years_w_beta:
        pred = predict_from_w(w, year_features[yr])
        actual = EMPIRICAL_BETAS[yr]
        err = abs(pred - actual)
        in_sample_errors.append(err)
        print(f"  {yr:<6} {pred:>10.3f} {actual:>10.3f} {err:>10.3f}")
    print(f"  In-sample MAE: {sum(in_sample_errors)/len(in_sample_errors):.4f}")
    print()

    if mae <= 0.10:
        assessment = "ADEQUATE: MAE ≤ 0.10 — model meets target accuracy."
        upgrade = "optional"
    elif mae <= 0.15:
        assessment = "MARGINAL: MAE 0.10–0.15 — LLM signal extraction upgrade recommended."
        upgrade = "recommended"
    else:
        assessment = ("INSUFFICIENT: MAE > 0.15 — regex signals are inadequate.\n"
                      "  LLM upgrade (Haiku structured extraction) is CRITICAL, not optional.\n"
                      "  Treat predict_beta output with ±0.20 uncertainty until LLM upgrade ships.")
        upgrade = "critical"

    print(f"ASSESSMENT: {assessment}")
    print()

    # Save signals to cache for audit trail
    signals_cache = {
        str(yr): {
            **EXPERT_SIGNALS[yr],
            "empirical_beta": EMPIRICAL_BETAS.get(yr),
            "in_sample_pred": round(predict_from_w(w, year_features[yr]), 4),
        }
        for yr in fit_years
    }
    cache_path = _CACHE_DIR / "expert_signals.json"
    with open(cache_path, "w") as f:
        json.dump(signals_cache, f, indent=2)
    print(f"Signal audit trail saved to: {cache_path}")
    print()

    return {
        "intercept": round(w[0], 6),
        "w_handoff": round(w[1], 6),
        "w_alliance": round(w[2], 6),
        "w_feeder": round(w[3], 6),
        "w_possession": round(w[4], 6),
        "w_coop_rp": round(w[5], 6),
        "w_hrule": round(w[6], 6),
        "mae_loo": round(mae, 4),
        "n_train": len(fit_years_w_beta),
        "lambda": LAM,
        "loo_results": loo_results,
        "fit_years": fit_years_w_beta,
        "std_errors": [round(s, 6) for s in std_errors],
        "upgrade_recommendation": upgrade,
    }


if __name__ == "__main__":
    result = main()
    print("Fitted coefficients (for rulebook_beta_prior.py):")
    coef_keys = ["intercept", "w_handoff", "w_alliance", "w_feeder",
                 "w_possession", "w_coop_rp", "w_hrule"]
    for k in coef_keys:
        print(f"  {k}: {result[k]}")
