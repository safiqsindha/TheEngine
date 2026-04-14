"""
blueprint/attribution_betas.py
--------------------------------
Per-season power-curve attribution β configuration.

IMPORTANT: `prior_expected_beta` values come from the documented prior table in
design-intelligence/TOMORROW_POWER_CURVE_WORK.md lines 22-35.  They are prior
expectations, NOT empirical fits.  `empirical_beta` is None for every season
until the data-pull run (Item 1 execution) fills them in.

TODO(Item 1 data run): populate empirical_beta + empirical_ci + tuned_on_match_count
for each year after pulling Statbotics/TBA match data and running tune_attribution_beta.
"""

from __future__ import annotations

from typing import Optional, Union

# ---------------------------------------------------------------------------
# Season registry
# ---------------------------------------------------------------------------
# Each entry:
#   game_name             : str
#   prior_expected_beta   : float | dict[str, float]  (dict for per-phase, e.g. 2019)
#   prior_reason          : str  — why this prior was chosen
#   empirical_beta        : None until Item 1 data run fills it
#   empirical_ci          : None until Item 1 data run fills it (tuple[float,float])
#   tuned_on_match_count  : 0 until Item 1 data run fills it

ATTRIBUTION_BETAS: dict[int, dict] = {
    2013: {
        "game_name": "Ultimate Ascent",
        "prior_expected_beta": 0.70,
        "prior_reason": "Frisbee alliance coupling — robots share shooting lanes",
        "empirical_beta": 0.6,
        "empirical_ci": (0.5, 1.0),
        "tuned_on_match_count": 13748,
    },
    2014: {
        "game_name": "Aerial Assist",
        "prior_expected_beta": 0.60,
        "prior_reason": "Ball passing = extreme coupling; assist chains dominate scoring",
        "empirical_beta": 0.95,
        "empirical_ci": (0.6, 1.0),
        "tuned_on_match_count": 17854,
    },
    2015: {
        "game_name": "Recycle Rush",
        "prior_expected_beta": 0.85,
        "prior_reason": "Co-op + solo totes; mostly independent scoring per robot",
        "empirical_beta": None,   # TODO(Item 1 data run)
        "empirical_ci": None,     # TODO(Item 1 data run)
        "tuned_on_match_count": 0,
    },
    2016: {
        "game_name": "Stronghold",
        "prior_expected_beta": 0.60,
        "prior_reason": "Shooter + feeder + crosser roles; high inter-robot coupling",
        "empirical_beta": 1.0,
        "empirical_ci": (0.4, 1.0),
        "tuned_on_match_count": 21834,
    },
    2017: {
        "game_name": "Steamworks",
        "prior_expected_beta": 0.70,
        "prior_reason": "Gears coupled (require human player + loader), fuel independent",
        "empirical_beta": 0.85,
        "empirical_ci": (0.4, 1.0),
        "tuned_on_match_count": 24936,
    },
    2018: {
        "game_name": "Power Up",
        "prior_expected_beta": 0.75,
        "prior_reason": "Vault + switch coupled; exchange requires human player hand-off",
        "empirical_beta": 0.8,
        "empirical_ci": (0.4, 1.0),
        "tuned_on_match_count": 28234,
    },
    2019: {
        "game_name": "Deep Space",
        # Per-phase β — cycle and climb have different coupling profiles
        "prior_expected_beta": {"cycle": 0.85, "climb": 0.60},
        "prior_reason": (
            "Cycle phase: mostly independent cargo/hatch placement (β~0.85). "
            "Climb phase: HAB level 3 often requires buddy-climb assistance (β~0.60)."
        ),
        # empirical_beta kept None for 2019: bulk Statbotics data does not separate
        # cycle vs climb phases.  Overall tune returned β=1.0 (n=29232, CI=(0.75,1.0))
        # but the per-phase prior (cycle:0.85 / climb:0.60) is retained as the best
        # available estimate.  Set empirical_beta only when per-phase data is available.
        "empirical_beta": None,
        "empirical_ci": None,
        "tuned_on_match_count": 29232,  # overall qual matches tuned; no per-phase β
    },
    2020: {
        "game_name": "Infinite Recharge",
        "prior_expected_beta": 0.75,
        "prior_reason": "Power cells cycling; trench run coordination creates moderate coupling",
        "empirical_beta": 1.0,
        "empirical_ci": (0.65, 1.0),
        "tuned_on_match_count": 7558,
    },
    2022: {
        "game_name": "Rapid React",
        "prior_expected_beta": 0.70,
        "prior_reason": "Ball coupling strong; terminal + human player handoff coordination",
        "empirical_beta": 0.95,
        "empirical_ci": (0.55, 1.0),
        "tuned_on_match_count": 23750,
    },
    2023: {
        "game_name": "Charged Up",
        "prior_expected_beta": 0.80,
        "prior_reason": "Grid scoring largely independent per robot; charge station shared",
        "empirical_beta": 0.65,
        "empirical_ci": (0.7, 1.0),
        "tuned_on_match_count": 26804,
    },
    2024: {
        "game_name": "Crescendo",
        "prior_expected_beta": 0.70,
        "prior_reason": "Speaker carries dominant; note passing from source creates coupling",
        "empirical_beta": 0.55,
        "empirical_ci": (0.5, 1.0),
        "tuned_on_match_count": 27874,
    },
    2025: {
        "game_name": "Reefscape",
        "prior_expected_beta": 0.70,
        "prior_reason": "Algae staging effects verified by kl26436 community analysis",
        "empirical_beta": 0.65,
        "empirical_ci": (0.5, 1.0),
        "tuned_on_match_count": 32442,
    },
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_attribution_beta(year: int, phase: str = "overall") -> float:
    """
    Return the best available β for the given season and phase.

    Priority order:
      1. empirical_beta (set by Item 1 data run) — most accurate
      2. prior_expected_beta (documented prior expectations)
      3. 1.0 fallback — linear attribution, safe default

    Parameters
    ----------
    year  : FRC season year (e.g. 2025)
    phase : "overall" for whole-match β, or a phase key like "cycle" / "climb"
            (only meaningful for seasons with per-phase β, currently 2019).
            Unknown phase names fall back to the overall / scalar prior.

    Returns
    -------
    float — β in approximately [0.4, 1.0], or 1.0 if year is unknown.
    """
    if year not in ATTRIBUTION_BETAS:
        return 1.0  # safe linear fallback for unknown seasons

    entry = ATTRIBUTION_BETAS[year]

    # --- empirical_beta takes priority when available ---
    emp = entry.get("empirical_beta")
    if emp is not None:
        if isinstance(emp, dict):
            return _resolve_phase(emp, phase, year)
        return float(emp)

    # --- fall back to prior ---
    prior = entry.get("prior_expected_beta")
    if prior is None:
        return 1.0
    if isinstance(prior, dict):
        return _resolve_phase(prior, phase, year)
    return float(prior)


def _resolve_phase(phase_dict: dict[str, float], phase: str, year: int) -> float:
    """
    Resolve a phase key from a per-phase dict.
    Falls back to the first value in the dict if the requested phase is absent,
    then to 1.0 if the dict is empty.
    """
    if phase in phase_dict:
        return float(phase_dict[phase])
    # Unknown phase for a per-phase season: use the first available value as proxy
    values = list(phase_dict.values())
    if values:
        return float(values[0])
    return 1.0
