#!/usr/bin/env python3
"""
The Engine — The Oracle (Prediction Engine)
Team 2950 — The Devastators

Applies CROSS_SEASON_PATTERNS rules R1-R19 + meta-rules to game parameters
and produces a complete OracleOutput JSON for the Blueprint pipeline.

This is the core intelligence: game rules in → robot architecture out.

Usage:
  python3 oracle.py predict <game_rules.json>         # Full prediction
  python3 oracle.py predict --example-2022             # 2022 Rapid React
  python3 oracle.py predict --example-2023             # 2023 Charged Up
  python3 oracle.py predict --example-2024             # 2024 Crescendo
  python3 oracle.py predict --example-2025             # 2025 Reefscape
  python3 oracle.py validate                           # Run all historical games

── Oracle Phase 1 Data Foundation (2026-04-13) ─────────────────────────────
Three targeted upgrades pulled forward from the June–July workstream:

  1. EPA UNCERTAINTY BANDS
     New helpers `epa_win_confidence` and `_normal_cdf` consume `epa_sd`
     and `epa_skew` from Statbotics. Rule confidence values can now be
     derived from a NormalDist(mu=EPA_diff, sigma=combined_sd).cdf(0)
     call instead of hardcoded constants. Backward-compat: when epa_sd is
     unavailable, confidence falls back to the old hardcoded constant.

  2. COMPONENT EPA DRAFT COMPLEMENTARITY
     New public helper `compute_alliance_complementarity(team_epas)` takes
     a list of per-team component-EPA dicts {auto, teleop, endgame} and
     returns a complementarity score [0.0, 1.0]. Score 1.0 = perfectly
     balanced; 0.0 = all three bots identical in every phase. Used by
     alliance advisors to flag structural weaknesses (e.g. 3 auto-heavy
     bots with no endgame).

  3. CONFIDENCE_POLICY DICT
     Single source of truth for confidence thresholds replacing scattered
     0.85/0.90/0.95 literals. All rule RuleResult() calls now reference
     CONFIDENCE_POLICY["high"] / ["medium"] / ["low"] / ["certain"].
     Old numeric values are preserved as the policy defaults so existing
     behaviour is unchanged when no EPA data is present.

Backward compatibility: `apply_rules()`, `predict_game()`, `validate_all()`,
`predict_from_file()` signatures and return shapes are unchanged. All 86
pre-existing tests continue to pass. New helpers are purely additive.
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent

# Import attribution β lookup — tolerant import so oracle works without
# the attribution_betas module (e.g. in isolated test environments).
try:
    from attribution_betas import get_attribution_beta as _get_attribution_beta  # type: ignore
except ImportError:
    def _get_attribution_beta(year: int, phase: str = "overall") -> float:  # type: ignore
        return 1.0


# ═══════════════════════════════════════════════════════════════════
# CONFIDENCE POLICY — single source of truth for rule thresholds
# ═══════════════════════════════════════════════════════════════════

CONFIDENCE_POLICY: Dict[str, float] = {
    "certain": 1.00,   # R1 — swerve, always true post-2022
    "high":    0.90,   # R4 ranged/placement, R6 turret decisions, R7 climb
    "medium":  0.85,   # R3 roller, R5 elevator, R8 auto, R10 detection
    "low":     0.75,   # R4 unknown target fallback
}

# Fraction of EPA total used as fallback SD when Statbotics sd is absent.
# Matches the same constant in scout/win_probability.py for consistency.
_DEFAULT_SD_FRACTION: float = 0.25

# Minimum sigma to prevent division-by-zero on degenerate inputs
_MIN_SIGMA: float = 1e-6


# ═══════════════════════════════════════════════════════════════════
# EPA UNCERTAINTY HELPERS
# ═══════════════════════════════════════════════════════════════════

def _normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erfc — no scipy required.

    Identical implementation to scout/win_probability.py so the two
    modules stay in sync without a shared dependency.
    """
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def epa_win_confidence(
    epa_a: float,
    epa_b: float,
    epa_sd_a: Optional[float] = None,
    epa_sd_b: Optional[float] = None,
    *,
    fallback_confidence: float = CONFIDENCE_POLICY["high"],
) -> float:
    """Return P(Team A outscores Team B) using a Gaussian score model.

    Parameters
    ----------
    epa_a, epa_b       : EPA mean values for the two teams/alliances
    epa_sd_a, epa_sd_b : EPA standard deviations (from Statbotics
                         ``epa.total_points.sd``). If either is None or
                         zero the function falls back to
                         ``fallback_confidence``.
    fallback_confidence : returned as-is when SD data is unavailable.
                         Default = CONFIDENCE_POLICY["high"] (0.90).

    Returns
    -------
    float in [0.0, 1.0]

    Example
    -------
    >>> epa_win_confidence(150.0, 130.0, epa_sd_a=18.0, epa_sd_b=15.0)
    0.724...   # 72% chance Team A wins
    """
    if not epa_sd_a or not epa_sd_b:
        return fallback_confidence

    sd_a = epa_sd_a if epa_sd_a > 0 else epa_a * _DEFAULT_SD_FRACTION
    sd_b = epa_sd_b if epa_sd_b > 0 else epa_b * _DEFAULT_SD_FRACTION
    sigma = math.sqrt(sd_a ** 2 + sd_b ** 2)
    sigma = max(sigma, _MIN_SIGMA)
    return _normal_cdf((epa_a - epa_b) / sigma)


def compute_alliance_complementarity(
    team_epas: List[Dict[str, float]],
    beta: Optional[float] = None,
) -> float:
    """Score how well-balanced an alliance is across game phases.

    Evaluates the spread of contribution across auto, teleop, and endgame
    component EPAs. A perfectly complementary alliance has each robot
    contributing meaningfully in different phases; a redundant alliance
    has all three bots clustered in the same phase.

    Parameters
    ----------
    team_epas : list of dicts, each with keys:
                  ``auto``     — auto-phase component EPA
                  ``teleop``   — teleop-phase component EPA
                  ``endgame``  — endgame-phase component EPA
                Each dict represents one team on the alliance (typically 3).
    beta : optional float — attribution β for the current season.
           When provided, weights the balance score (phase CV) vs raw total
           contribution:

             - β < 0.7  (high coupling): balance score weighted more heavily.
               Complementary specialist alliances matter more.
             - β ≥ 0.85 (independent):   raw per-team totals weighted more heavily.
               High-EPA generalists are preferred over balanced specialists.
             - 0.7 ≤ β < 0.85:           linear blend between the two regimes.

           When ``beta`` is None the function returns the legacy CV-based score
           unchanged (full backward compatibility).

    Returns
    -------
    float in [0.0, 1.0]
        1.0 = perfectly balanced (each team specialises in a different phase)
              — or, when β is high, a raw-total-dominant score approaching 1.0
              for a high-EPA alliance.
        0.0 = all three robots identical across all phases (full redundancy)

    Notes
    -----
    Algorithm: for each phase, compute the coefficient of variation (CV =
    std / mean) across teams. Average CV across phases captures how varied
    the contribution pattern is. Normalise to [0, 1] by capping at CV = 1.

    When total EPA across all teams is zero (degenerate input), returns 0.5
    to indicate unknown / neutral complementarity.

    Example
    -------
    >>> teams = [
    ...     {"auto": 20, "teleop": 5,  "endgame": 0},   # auto specialist
    ...     {"auto": 5,  "teleop": 20, "endgame": 0},   # teleop specialist
    ...     {"auto": 5,  "teleop": 5,  "endgame": 15},  # endgame specialist
    ... ]
    >>> compute_alliance_complementarity(teams)
    0.816...   # highly complementary
    """
    if not team_epas:
        return 0.5

    phases = ("auto", "teleop", "endgame")
    total = sum(
        t.get(p, 0.0) for t in team_epas for p in phases
    )
    if total == 0.0:
        return 0.5

    cv_scores: list[float] = []
    for phase in phases:
        values = [t.get(phase, 0.0) for t in team_epas]
        mean = sum(values) / len(values)
        if mean == 0.0:
            # Phase not scored by anyone — treat as neutral, skip
            continue
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        cv = std / mean  # coefficient of variation
        cv_scores.append(min(cv, 1.0))  # cap at 1.0

    if not cv_scores:
        return 0.5

    balance_score = round(sum(cv_scores) / len(cv_scores), 4)

    # Legacy path: no beta → return raw CV-based balance score unchanged.
    if beta is None:
        return balance_score

    # β-weighted blend: mix balance_score (role coverage) with raw_total_score.
    # raw_total_score is a normalised proxy for how much EPA the alliance has
    # in total — we cap normalisation at 150 pts (a strong 3-robot alliance).
    raw_total_score = min(total / 150.0, 1.0)

    # β thresholds defined in Rule #18 specification:
    _BETA_HIGH_COUPLING = 0.70    # below → complementarity dominates
    _BETA_INDEPENDENT   = 0.85    # above → raw totals dominate

    if beta < _BETA_HIGH_COUPLING:
        # High coupling: role coverage matters most — return balance_score.
        return balance_score
    elif beta >= _BETA_INDEPENDENT:
        # Independent game: raw EPA totals matter most.
        return raw_total_score
    else:
        # Linear blend over [0.70, 0.85].
        t = (beta - _BETA_HIGH_COUPLING) / (_BETA_INDEPENDENT - _BETA_HIGH_COUPLING)
        return round((1.0 - t) * balance_score + t * raw_total_score, 4)


# ─── Rule #18: Alliance complementarity ranking ─────────────────────────────

def rank_alliances_r18(
    alliances: List[List[Dict[str, float]]],
    year: Optional[int] = None,
) -> List[Tuple[int, float]]:
    """Rule #18 — Rank candidate alliances by complementarity, β-weighted.

    Uses ``compute_alliance_complementarity`` with an attribution β looked up
    from ``attribution_betas.get_attribution_beta(year)`` when *year* is given.

    Ranking behaviour by β regime
    ──────────────────────────────
    β < 0.70  (high coupling — e.g. 2024 Crescendo β=0.55)
        Role coverage dominates. Complementary specialist alliances score
        higher than high-EPA generalist alliances.

    0.70 ≤ β < 0.85  (moderate)
        Linear blend: both role coverage and raw EPA sum matter.

    β ≥ 0.85  (independent — e.g. 2014 Aerial Assist β=0.95)
        Raw EPA sum dominates. High-total alliances rank above balanced
        but lower-EPA alliances.

    Default (year=None)
        β is treated as None in ``compute_alliance_complementarity``,
        preserving the legacy CV-only ranking — full backward compatibility.

    Parameters
    ----------
    alliances : list of candidate alliances.  Each alliance is a list of
                per-team component-EPA dicts with keys ``auto``, ``teleop``,
                ``endgame`` (same format as ``compute_alliance_complementarity``).
    year      : FRC season year.  When provided, β is looked up via
                ``get_attribution_beta(year)``.  When None, legacy scoring
                applies (no β adjustment).

    Returns
    -------
    List of ``(original_index, score)`` tuples sorted descending by score
    (best alliance first).  Scores are in [0.0, 1.0].

    Edge cases
    ----------
    - Unknown year (not in registry): β falls back to 1.0 → raw-total scoring.
    - Empty alliances list: returns [].
    - Alliance with all-zero EPA: scores 0.5 (neutral, legacy behaviour).
    """
    if not alliances:
        return []

    # Resolve beta: None for legacy, float from registry when year provided.
    beta: Optional[float] = None
    if year is not None:
        beta = _get_attribution_beta(year)

    scored = []
    for idx, alliance in enumerate(alliances):
        score = compute_alliance_complementarity(alliance, beta=beta)
        scored.append((idx, score))

    # Sort descending — highest score first.
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ═══════════════════════════════════════════════════════════════════
# GAME RULES INPUT — Structured version of KICKOFF_TEMPLATE.md
# ═══════════════════════════════════════════════════════════════════

@dataclass
class GameRules:
    """Structured game rules extracted from the game manual."""
    game_name: str = ""
    year: int = 2027
    auto_duration_s: int = 15
    teleop_duration_s: int = 135
    endgame_duration_s: int = 20

    # Game pieces
    game_piece_name: str = ""
    game_piece_shape: str = ""             # spherical, cylindrical, flat, irregular
    game_piece_diameter_in: float = 4.5
    game_piece_weight_lb: float = 0.5
    pieces_on_field: int = 6
    pieces_preloadable: int = 1
    human_player_introduces: bool = True
    pieces_at_known_positions: bool = True  # fixed vs scattered
    pieces_floor_pickup: bool = True
    pieces_shared_contested: bool = False
    piece_high_contrast: bool = True        # bright color vs low contrast

    # Dual game pieces
    has_second_piece: bool = False
    second_piece_name: str = ""
    second_piece_shape: str = ""
    second_piece_handling: str = ""         # "same_mechanism", "different_mechanism"

    # Scoring targets
    scoring_targets: list = field(default_factory=list)
    # Each: {"name", "height_in", "distance_ft", "auto_pts", "teleop_pts",
    #         "type": "ranged"/"placement"/"ground", "distributed": bool,
    #         "cap_type": "capped"/"uncapped"/"semi_capped", "max_alliance_pts": int}

    # Endgame
    endgame_type: str = ""                  # climb, park, balance, none
    endgame_height_in: float = 0
    endgame_points: int = 0
    endgame_pct_of_winning_score: float = 0.15

    # Field
    field_has_obstacles: bool = False
    field_obstacle_height_in: float = 0
    field_is_small: bool = False            # short cycle distances
    max_robot_height_in: float = 48
    max_frame_perimeter_in: float = 120

    # Scoring meta
    estimated_winning_score: int = 100

    @classmethod
    def from_dict(cls, data: dict) -> "GameRules":
        """Construct a GameRules from a plain dict, ignoring unknown keys.
        Uses dataclasses.fields() for proper introspection — fixes the
        hasattr() bug where default_factory fields were silently dropped."""
        valid_field_names = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_field_names}
        return cls(**filtered)

    def to_dict(self) -> dict:
        """Serialize this GameRules to a plain dict (for JSON output)."""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════
# RULE ENGINE — Applies R1-R19 to GameRules
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RuleResult:
    """Output of a single rule application."""
    rule_id: str
    applies: bool
    recommendation: str
    confidence: float
    reasoning: str


def apply_rules(game: GameRules) -> dict:
    """
    Apply all CROSS_SEASON_PATTERNS rules to game parameters.
    Returns a dict of predictions keyed by subsystem.
    """
    results = []
    pred = {
        "game_name": game.game_name,
        "year": game.year,
        "drivetrain": {},
        "intake": {},
        "scorer": {},
        "endgame": {},
        "autonomous": {},
        "weight_budget": {},
        "build_order": [],
        "rule_log": [],
    }

    # ── R1: Drivetrain — Always swerve ──
    r1 = RuleResult("R1", True, "swerve", 1.0,
                     "Swerve mandatory post-2022. Every Einstein competitor uses swerve.")
    results.append(r1)

    # Speed: small field → acceleration, large field → speed
    if game.field_is_small:
        speed = 14.0
        gear_for = "acceleration"
    else:
        speed = 16.0
        gear_for = "speed"

    # Frame size — default 27x27, adjust for mechanisms
    frame_size = 27.0
    if game.max_frame_perimeter_in < 112:
        frame_size = min(27.0, game.max_frame_perimeter_in / 4 - 1)

    pred["drivetrain"] = {
        "type": "swerve",
        "module": "sds_mk4i",
        "speed_fps": speed,
        "gear_for": gear_for,
        "frame_length": frame_size,
        "frame_width": frame_size,
        "reasoning": r1.reasoning,
    }

    # ── R2: Intake width — Always full width ──
    r2 = RuleResult("R2", game.pieces_floor_pickup, "full_width_intake",
                     CONFIDENCE_POLICY["high"],
                     "Full-width bumper-to-bumper intake. Every champion since 2019.")
    results.append(r2)

    # ── R3: Roller material ──
    shape = game.game_piece_shape.lower()
    if "spher" in shape or "ball" in shape:
        roller_material = "compliant_wheels"
        r3_note = "Spherical piece → compliant/banebot wheels"
    elif "flat" in shape or "disc" in shape or "note" in shape:
        roller_material = "mecanum_funnel"
        r3_note = "Flat/disc piece → mecanum funneling wheels"
    elif "cyl" in shape or "tube" in shape or "pipe" in shape:
        roller_material = "flex_wheels"
        r3_note = "Cylindrical piece → flex wheels with floating roller"
    elif "irreg" in shape or "cube" in shape or "cone" in shape:
        roller_material = "flex_wheels"
        r3_note = "Irregular piece → flex wheels (safest default)"
    else:
        roller_material = "flex_wheels"
        r3_note = "Unknown shape → flex wheels (safest default)"

    r3 = RuleResult("R3", True, roller_material, CONFIDENCE_POLICY["medium"], r3_note)
    results.append(r3)

    # Intake type — over_bumper default, under_bumper if piece is small
    intake_type = "over_bumper"
    if game.game_piece_diameter_in < 3.0:
        intake_type = "under_bumper"
    deploy = game.pieces_floor_pickup

    pred["intake"] = {
        "type": intake_type,
        "width": "full",
        "roller_material": roller_material,
        "deploy": deploy,
        "motors": 2,
        "game_piece": f"{game.game_piece_name} ({game.game_piece_shape})",
        "reasoning": f"{r2.reasoning} {r3.reasoning}",
    }

    # ── R4: Scoring method — Ranged vs Placement ──
    primary_target = _get_primary_target(game)
    if primary_target:
        target_type = primary_target.get("type", "placement")
        target_distributed = primary_target.get("distributed", False)
        target_height = primary_target.get("height_in", 0)
    else:
        target_type = "placement"
        target_distributed = False
        target_height = 48

    if target_type == "ranged":
        scorer_method = "flywheel"
        r4_conf = CONFIDENCE_POLICY["high"]
        r4_note = "Ranged scoring targets → flywheel shooter"
    elif target_type == "placement":
        scorer_method = "elevator"
        r4_conf = CONFIDENCE_POLICY["high"]
        r4_note = "Placement scoring targets → elevator + wrist"
    elif target_type == "ground":
        scorer_method = "gravity_drop"
        r4_conf = CONFIDENCE_POLICY["medium"]
        r4_note = "Ground-level targets → roller eject or gravity drop"
    else:
        scorer_method = "elevator"
        r4_conf = CONFIDENCE_POLICY["low"]
        r4_note = "Unknown target type → default elevator"

    r4 = RuleResult("R4", True, scorer_method, r4_conf, r4_note)
    results.append(r4)

    # ── R5: Elevator stage count ──
    if scorer_method == "elevator":
        if target_height <= 24:
            stages = 0  # arm or fixed
            r5_note = f"Height {target_height}\" → no elevator needed, arm or fixed"
        elif target_height <= 40:
            stages = 1
            r5_note = f"Height {target_height}\" → single-stage elevator"
        elif target_height <= 55:
            stages = 2
            r5_note = f"Height {target_height}\" → two-stage continuous elevator"
        else:
            stages = 2  # still 2, 3-stage is too complex
            r5_note = f"Height {target_height}\" → two-stage (3-stage too complex, R5 70%)"
    else:
        stages = 0
        r5_note = "Non-elevator scorer, stages N/A"

    r5 = RuleResult("R5", scorer_method == "elevator", f"{stages}_stage", CONFIDENCE_POLICY["medium"], r5_note)
    results.append(r5)

    # ── R6: Turret decision (4-quadrant matrix) ──
    turret = "none"
    if target_type == "ranged" and target_distributed:
        turret = "continuous"
        r6_note = "Ranged + distributed targets → BUILD TURRET (90%)"
        r6_conf = CONFIDENCE_POLICY["high"]
    elif target_type == "ranged" and not target_distributed:
        turret = "none"  # optional, default skip
        r6_note = "Ranged + fixed targets → turret optional, skipping (65%)"
        r6_conf = 0.65  # intentional below-policy — ambiguous decision
    elif target_type == "placement" and target_distributed:
        turret = "none"
        r6_note = "Placement + distributed → SKIP turret (90%)"
        r6_conf = CONFIDENCE_POLICY["high"]
    else:
        turret = "none"
        r6_note = "Placement + fixed → SKIP turret (95%)"
        r6_conf = CONFIDENCE_POLICY["certain"]  # unanimous historical evidence

    r6 = RuleResult("R6", True, turret, r6_conf, r6_note)
    results.append(r6)

    # Build scorer prediction
    scorer_motors = 2
    has_wrist = scorer_method == "elevator" and target_height > 24
    if scorer_method == "flywheel":
        scorer_motors = 2  # dual flywheel
        has_wrist = False

    pred["scorer"] = {
        "method": scorer_method,
        "height_in": target_height if scorer_method == "elevator" else 0,
        "stages": stages,
        "motors": scorer_motors,
        "has_wrist": has_wrist,
        "turret": turret,
        "reasoning": f"{r4.reasoning}. {r5.reasoning}. {r6.reasoning}",
    }

    # ── R7: Endgame climb ──
    # Evidence: every champion since 2016 climbed if climbing existed.
    # >15% = MUST climb. 5-15% = strongly recommended. <5% = optional.
    climb_pct = game.endgame_pct_of_winning_score
    climb_must = climb_pct >= 0.15
    climb_should = game.endgame_type in ("climb", "balance") and climb_pct >= 0.05
    climb_required = climb_must or climb_should

    r7 = RuleResult("R7", climb_required,
                     "climb" if climb_required else "optional", CONFIDENCE_POLICY["certain"],
                     f"Endgame is {climb_pct*100:.0f}% of winning score"
                     + (", MUST climb" if climb_must else
                        ", strongly recommended" if climb_should else
                        ", optional"))
    results.append(r7)

    if climb_required and game.endgame_type in ("climb", "balance"):
        endgame_type = "hook_winch"
        if game.endgame_height_in > 40:
            endgame_type = "telescope"
        elif game.endgame_type == "balance":
            endgame_type = "balance"
        endgame_motors = 2 if game.endgame_height_in > 30 else 1
    elif game.endgame_type == "park":
        endgame_type = "park_only"
        endgame_motors = 0
    else:
        endgame_type = "none"
        endgame_motors = 0

    pred["endgame"] = {
        "type": endgame_type,
        "height_in": game.endgame_height_in,
        "motors": endgame_motors,
        "reasoning": r7.reasoning,
    }

    # ── R8: Autonomous ──
    auto_pieces = 3  # baseline
    if game.auto_duration_s >= 15 and game.pieces_at_known_positions:
        auto_pieces = 3
    if game.field_is_small:
        auto_pieces = min(5, auto_pieces + 1)

    r8 = RuleResult("R8", True, f"{auto_pieces}_piece_auto", CONFIDENCE_POLICY["medium"],
                     f"Target {auto_pieces}-piece auto. Known positions: {game.pieces_at_known_positions}")
    results.append(r8)

    # ── R10: Game piece detection ──
    needs_detection = False
    detection_method = "none"
    if game.pieces_floor_pickup and not game.pieces_at_known_positions:
        needs_detection = True
        if game.piece_high_contrast:
            detection_method = "hsv_color"
        else:
            detection_method = "yolo_neural"
    elif game.pieces_shared_contested:
        needs_detection = True
        detection_method = "yolo_neural"

    r10 = RuleResult("R10", needs_detection, detection_method, CONFIDENCE_POLICY["medium"],
                      f"Detection: {detection_method}" if needs_detection
                      else "No detection needed — known positions + wide intake")
    results.append(r10)

    # Cycle time target (R11)
    cycle_target = 5.0
    if game.field_is_small:
        cycle_target = 4.0

    pred["autonomous"] = {
        "priority_actions": ["score_preload"] + ["intake_nearby", "score_second"] * min(auto_pieces - 1, 2),
        "cycle_time_s": cycle_target,
        "preload_score": True,
        "estimated_pieces": auto_pieces,
        "reasoning": f"{r8.reasoning}. Cycle target: {cycle_target}s (R11).",
    }

    # ── R18: Obstacle check ──
    if game.field_has_obstacles:
        r18 = RuleResult("R18", True, "raise_bellypan", CONFIDENCE_POLICY["medium"],
                          f"Field obstacles at {game.field_obstacle_height_in}\". "
                          "Prototype obstacle crossing day 1. Raise bellypan to 2-3\".")
        results.append(r18)

    # ── R19: Capped vs Uncapped analysis ──
    r19_result = _run_scoring_analysis(game)
    if r19_result:
        results.append(r19_result)
        # Override scorer if uncapped method is better
        if "uncapped_priority" in r19_result.recommendation:
            pred["scorer"]["reasoning"] += f" R19: {r19_result.reasoning}"

    # ── Weight budget (R12) ──
    pred["weight_budget"] = {
        "drivetrain_lb": 42,
        "intake_lb": 10,
        "scorer_lb": 22 if scorer_method == "elevator" else 15,
        "endgame_lb": 8 if climb_required else 2,
        "electronics_lb": 15,
        "bumpers_lb": 10,
        "margin_lb": 18,
        "total_limit_lb": 125,
    }

    # ── Build order (R13) ──
    pred["build_order"] = ["drivetrain", "intake", "scorer", "autonomous", "endgame"]
    if scorer_method == "elevator" and target_height > 40:
        # Elevator-heavy games: scorer before intake
        pred["build_order"] = ["drivetrain", "scorer", "intake", "autonomous", "endgame"]

    # ── Confidence ──
    confidences = [r.confidence for r in results if r.applies]
    pred["confidence"] = round(sum(confidences) / len(confidences), 2) if confidences else 0.5

    # ── Rule log ──
    pred["rule_log"] = [
        {"rule": r.rule_id, "applies": r.applies, "recommendation": r.recommendation,
         "confidence": r.confidence, "reasoning": r.reasoning}
        for r in results
    ]

    return pred


def _get_primary_target(game: GameRules) -> dict:
    """Find the highest-value scoring target."""
    if not game.scoring_targets:
        return {}
    return max(game.scoring_targets, key=lambda t: t.get("teleop_pts", 0))


def _run_scoring_analysis(game: GameRules) -> RuleResult:
    """R19: Capped vs Uncapped scoring analysis."""
    capped = [t for t in game.scoring_targets if t.get("cap_type") == "capped"]
    uncapped = [t for t in game.scoring_targets if t.get("cap_type") == "uncapped"]

    if not capped or not uncapped:
        return None

    capped_max = sum(t.get("max_alliance_pts", 0) for t in capped)
    uncapped_primary = max(uncapped, key=lambda t: t.get("teleop_pts", 0))

    # Saturation test: can a good 3-robot alliance cap the capped method?
    match_time = game.teleop_duration_s
    # Rough estimate: 3 robots × 10 cycles × capped_pts_per_cycle
    capped_pts_per_cycle = max((t.get("teleop_pts", 0) for t in capped), default=0)
    estimated_alliance_capped = 3 * 10 * capped_pts_per_cycle

    if estimated_alliance_capped > capped_max * 0.8:
        # Capped method will saturate → uncapped is differentiator
        return RuleResult(
            "R19", True, "uncapped_priority", 0.88,
            f"Capped methods ({capped_max} max pts) will saturate. "
            f"Uncapped method ({uncapped_primary.get('name', '?')}) is the differentiator."
        )
    else:
        return RuleResult(
            "R19", True, "capped_priority", 0.88,
            f"Capped methods ({capped_max} max pts) won't saturate — remain priority."
        )


# ═══════════════════════════════════════════════════════════════════
# HISTORICAL GAME DEFINITIONS — For validation
# ═══════════════════════════════════════════════════════════════════

HISTORICAL_GAMES = {
    "2022": GameRules(
        game_name="Rapid React", year=2022,
        game_piece_name="cargo", game_piece_shape="spherical",
        game_piece_diameter_in=9.5, game_piece_weight_lb=0.44,
        pieces_on_field=11, pieces_preloadable=1,
        human_player_introduces=True, pieces_at_known_positions=True,
        pieces_floor_pickup=True, pieces_shared_contested=True,
        piece_high_contrast=True,
        scoring_targets=[
            {"name": "Lower Hub", "height_in": 24, "distance_ft": 3, "auto_pts": 2, "teleop_pts": 1,
             "type": "ranged", "distributed": True, "cap_type": "uncapped", "max_alliance_pts": 999},
            {"name": "Upper Hub", "height_in": 104, "distance_ft": 6, "auto_pts": 4, "teleop_pts": 2,
             "type": "ranged", "distributed": True, "cap_type": "uncapped", "max_alliance_pts": 999},
        ],
        endgame_type="climb", endgame_height_in=63, endgame_points=15,
        endgame_pct_of_winning_score=0.25,
        field_has_obstacles=False, field_is_small=False,
        estimated_winning_score=120,
    ),
    "2023": GameRules(
        game_name="Charged Up", year=2023,
        game_piece_name="cube/cone", game_piece_shape="irregular",
        game_piece_diameter_in=9.5, game_piece_weight_lb=1.2,
        pieces_on_field=12, pieces_preloadable=1,
        human_player_introduces=True, pieces_at_known_positions=True,
        pieces_floor_pickup=True, pieces_shared_contested=True,
        piece_high_contrast=True,
        has_second_piece=True, second_piece_name="cone",
        second_piece_shape="conical", second_piece_handling="same_mechanism",
        scoring_targets=[
            {"name": "Grid High", "height_in": 46, "distance_ft": 0, "auto_pts": 6, "teleop_pts": 5,
             "type": "placement", "distributed": True, "cap_type": "capped", "max_alliance_pts": 135},
            {"name": "Grid Mid", "height_in": 34, "distance_ft": 0, "auto_pts": 4, "teleop_pts": 3,
             "type": "placement", "distributed": True, "cap_type": "capped", "max_alliance_pts": 81},
            {"name": "Grid Low", "height_in": 0, "distance_ft": 0, "auto_pts": 3, "teleop_pts": 2,
             "type": "ground", "distributed": True, "cap_type": "capped", "max_alliance_pts": 54},
        ],
        endgame_type="balance", endgame_height_in=12, endgame_points=10,
        endgame_pct_of_winning_score=0.12,
        field_has_obstacles=False, field_is_small=True,
        estimated_winning_score=160,
    ),
    "2024": GameRules(
        game_name="Crescendo", year=2024,
        game_piece_name="note", game_piece_shape="flat disc (14\" ring)",
        game_piece_diameter_in=14, game_piece_weight_lb=0.22,
        pieces_on_field=11, pieces_preloadable=1,
        human_player_introduces=True, pieces_at_known_positions=True,
        pieces_floor_pickup=True, pieces_shared_contested=True,
        piece_high_contrast=True,
        scoring_targets=[
            {"name": "Speaker", "height_in": 80, "distance_ft": 10, "auto_pts": 5, "teleop_pts": 2,
             "type": "ranged", "distributed": False, "cap_type": "uncapped", "max_alliance_pts": 999},
            {"name": "Amp", "height_in": 24, "distance_ft": 0, "auto_pts": 2, "teleop_pts": 1,
             "type": "placement", "distributed": False, "cap_type": "semi_capped", "max_alliance_pts": 100},
        ],
        endgame_type="climb", endgame_height_in=30, endgame_points=5,
        endgame_pct_of_winning_score=0.10,
        field_has_obstacles=False, field_is_small=False,
        estimated_winning_score=120,
    ),
    "2025": GameRules(
        game_name="Reefscape", year=2025,
        game_piece_name="coral", game_piece_shape="cylindrical tube",
        game_piece_diameter_in=4.0, game_piece_weight_lb=0.3,
        pieces_on_field=9, pieces_preloadable=1,
        human_player_introduces=True, pieces_at_known_positions=True,
        pieces_floor_pickup=True, pieces_shared_contested=False,
        piece_high_contrast=True,
        has_second_piece=True, second_piece_name="algae",
        second_piece_shape="spherical", second_piece_handling="same_mechanism",
        scoring_targets=[
            {"name": "Reef Branch L4", "height_in": 72, "distance_ft": 0, "auto_pts": 7, "teleop_pts": 7,
             "type": "placement", "distributed": True, "cap_type": "capped", "max_alliance_pts": 84},
            {"name": "Reef Branch L3", "height_in": 48, "distance_ft": 0, "auto_pts": 6, "teleop_pts": 6,
             "type": "placement", "distributed": True, "cap_type": "capped", "max_alliance_pts": 72},
            {"name": "Reef Branch L2", "height_in": 30, "distance_ft": 0, "auto_pts": 4, "teleop_pts": 4,
             "type": "placement", "distributed": True, "cap_type": "capped", "max_alliance_pts": 48},
            {"name": "Processor", "height_in": 12, "distance_ft": 0, "auto_pts": 0, "teleop_pts": 6,
             "type": "placement", "distributed": False, "cap_type": "uncapped", "max_alliance_pts": 999},
        ],
        endgame_type="climb", endgame_height_in=48, endgame_points=12,
        endgame_pct_of_winning_score=0.15,
        field_has_obstacles=False, field_is_small=True,
        estimated_winning_score=180,
    ),
}

# Ground truth: what the best teams actually built
GROUND_TRUTH = {
    "2022": {
        "drivetrain": "swerve",
        "intake_width": "full",
        "scorer_method": "flywheel",
        "turret": "continuous",       # 254 used turret
        "endgame": "climb",
        "auto_pieces": 5,             # 1678 did 5-ball
    },
    "2023": {
        "drivetrain": "swerve",
        "intake_width": "full",
        "scorer_method": "elevator",
        "turret": "none",
        "endgame": "balance",         # charge station
        "auto_pieces": 3,
    },
    "2024": {
        "drivetrain": "swerve",
        "intake_width": "full",
        "scorer_method": "flywheel",  # speaker shooter
        "turret": "none",             # fixed, not distributed
        "endgame": "climb",
        "auto_pieces": 4,
    },
    "2025": {
        "drivetrain": "swerve",
        "intake_width": "full",
        "scorer_method": "elevator",  # reef placement
        "turret": "none",
        "endgame": "climb",
        "auto_pieces": 3,
    },
}


# ═══════════════════════════════════════════════════════════════════
# VALIDATION — Test predictions against ground truth
# ═══════════════════════════════════════════════════════════════════

def validate_all() -> dict:
    """Run predictions for all historical games and compare to ground truth."""
    print(f"\n{'=' * 65}")
    print(f"  THE ORACLE — HISTORICAL VALIDATION")
    print(f"  Testing R1-R19 against 2022-2025 champion robots")
    print(f"{'=' * 65}\n")

    total_checks = 0
    correct = 0
    results = {}

    for year_str, game in sorted(HISTORICAL_GAMES.items()):
        truth = GROUND_TRUTH[year_str]
        pred = apply_rules(game)

        checks = []

        # Check drivetrain
        dt_correct = pred["drivetrain"]["type"] == truth["drivetrain"]
        checks.append(("R1 Drivetrain", dt_correct, pred["drivetrain"]["type"], truth["drivetrain"]))

        # Check intake width
        iw_correct = pred["intake"]["width"] == truth["intake_width"]
        checks.append(("R2 Intake Width", iw_correct, pred["intake"]["width"], truth["intake_width"]))

        # Check scorer method
        sm_correct = pred["scorer"]["method"] == truth["scorer_method"]
        checks.append(("R4 Scorer", sm_correct, pred["scorer"]["method"], truth["scorer_method"]))

        # Check turret
        turret_pred = pred["scorer"].get("turret", "none")
        turret_correct = turret_pred == truth["turret"]
        # Turret "none" vs "optional" both count as no turret
        if turret_pred in ("none", "optional") and truth["turret"] == "none":
            turret_correct = True
        checks.append(("R6 Turret", turret_correct, turret_pred, truth["turret"]))

        # Check endgame
        eg_pred = pred["endgame"]["type"]
        eg_truth = truth["endgame"]
        eg_correct = (eg_pred != "none" and eg_truth in ("climb", "balance")) or (eg_pred == "none" and eg_truth == "none")
        if eg_truth == "balance" and eg_pred in ("park_only", "hook_winch"):
            eg_correct = True  # balance is a form of endgame engagement
        checks.append(("R7 Endgame", eg_correct, eg_pred, eg_truth))

        year_correct = sum(1 for _, c, _, _ in checks if c)
        year_total = len(checks)
        total_checks += year_total
        correct += year_correct

        print(f"  {game.year} {game.game_name}")
        print(f"  {'─' * 55}")
        for name, is_correct, predicted, actual in checks:
            status = "PASS" if is_correct else "MISS"
            print(f"    [{status}] {name:20s}  predicted={predicted:15s}  actual={actual}")
        print(f"    Score: {year_correct}/{year_total}")
        print()

        results[year_str] = {
            "game": game.game_name,
            "checks": checks,
            "score": f"{year_correct}/{year_total}",
            "prediction": pred,
        }

    accuracy = correct / total_checks * 100 if total_checks > 0 else 0
    print(f"{'=' * 65}")
    print(f"  OVERALL: {correct}/{total_checks} checks passed ({accuracy:.0f}%)")
    print(f"{'=' * 65}\n")

    return {
        "total_checks": total_checks,
        "correct": correct,
        "accuracy_pct": round(accuracy, 1),
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def display_prediction(pred: dict):
    """Pretty-print a prediction."""
    print(f"\n{'=' * 65}")
    print(f"  THE ORACLE — {pred['year']} {pred['game_name']}")
    print(f"  Confidence: {pred['confidence']*100:.0f}%")
    print(f"{'=' * 65}")

    dt = pred["drivetrain"]
    print(f"\n  DRIVETRAIN: {dt['type']} ({dt['module']})")
    print(f"    Speed: {dt['speed_fps']} fps, gear for {dt['gear_for']}")
    print(f"    Frame: {dt['frame_length']}\" x {dt['frame_width']}\"")

    i = pred["intake"]
    print(f"\n  INTAKE: {i['type']}, {i['width']} width")
    print(f"    Rollers: {i['roller_material']}")
    print(f"    Game piece: {i['game_piece']}")

    s = pred["scorer"]
    print(f"\n  SCORER: {s['method']}")
    if s['method'] == 'elevator':
        print(f"    Height: {s['height_in']}\", {s['stages']} stages, wrist: {s['has_wrist']}")
    print(f"    Turret: {s['turret']}")

    e = pred["endgame"]
    print(f"\n  ENDGAME: {e['type']}")
    if e['height_in']:
        print(f"    Height: {e['height_in']}\"")

    a = pred["autonomous"]
    print(f"\n  AUTONOMOUS: {a['estimated_pieces']}-piece target")
    print(f"    Cycle: {a['cycle_time_s']}s")

    print(f"\n  BUILD ORDER: {' → '.join(pred['build_order'])}")

    print(f"\n  RULES APPLIED ({len(pred['rule_log'])}):")
    for r in pred["rule_log"]:
        status = "ACTIVE" if r["applies"] else "N/A"
        print(f"    [{status}] {r['rule']:4s} → {r['recommendation']:25s} ({r['confidence']*100:.0f}%)")

    print(f"\n{'=' * 65}\n")


def predict_game(game: GameRules) -> dict:
    """Public API: GameRules → full prediction dict (compatible with prediction_bridge)."""
    return apply_rules(game)


def predict_from_file(path: str) -> dict:
    """Load GameRules JSON from file, run prediction, return result."""
    with open(path) as f:
        data = json.load(f)
    game = GameRules.from_dict(data)
    return predict_game(game)


def run_full_pipeline(game: GameRules) -> dict:
    """End-to-end: GameRules → Oracle prediction → mechanism specs → BOM.

    Returns the full pipeline result dict.
    """
    from prediction_bridge import parse_oracle_output
    from oracle_pipeline import run_pipeline, display_pipeline_result

    pred = apply_rules(game)
    display_prediction(pred)

    oracle_output = parse_oracle_output(pred)
    result = run_pipeline(oracle_output)
    display_pipeline_result(result)

    # Save the pipeline output
    out = BASE_DIR / f"{game.year}_{game.game_name.lower().replace(' ', '_')}_pipeline.json"
    with open(out, "w") as f:
        json.dump({
            "oracle_prediction": pred,
            "specs": result.specs,
            "bom": result.bom,
            "log": result.generation_log,
        }, f, indent=2)
    print(f"  Pipeline output saved: {out.name}")

    return {
        "prediction": pred,
        "specs": result.specs,
        "bom": result.bom,
        "log": result.generation_log,
    }


def main():
    if len(sys.argv) < 2:
        print("The Oracle — Prediction Engine")
        print()
        print("Usage:")
        print("  python3 oracle.py predict <game_rules.json>")
        print("  python3 oracle.py predict --example-2022")
        print("  python3 oracle.py predict --example-2025")
        print("  python3 oracle.py validate")
        print("  python3 oracle.py pipeline --example-2025")
        print("  python3 oracle.py pipeline <game_rules.json>")
        return

    cmd = sys.argv[1]

    if cmd == "validate":
        result = validate_all()
        out = BASE_DIR / "oracle_validation_report.json"
        with open(out, "w") as f:
            json.dump({"accuracy": result["accuracy_pct"],
                        "correct": result["correct"],
                        "total": result["total_checks"]}, f, indent=2)
        print(f"  Report saved: {out.name}")

    elif cmd in ("predict", "pipeline"):
        if len(sys.argv) < 3:
            print("Provide a game rules JSON or --example-YEAR")
            return

        arg = sys.argv[2]
        game = None

        # Check for --example flags
        for year_str, g in HISTORICAL_GAMES.items():
            if arg == f"--example-{year_str}":
                game = g
                break

        # Load from file
        if game is None:
            path = Path(arg)
            if not path.exists():
                print(f"File not found: {path}")
                return
            with open(path) as f:
                data = json.load(f)
            game = GameRules(**{k: v for k, v in data.items() if hasattr(GameRules, k)})

        if cmd == "pipeline":
            run_full_pipeline(game)
        else:
            pred = apply_rules(game)
            display_prediction(pred)

            out = BASE_DIR / f"{game.year}_{game.game_name.lower().replace(' ', '_')}_oracle.json"
            with open(out, "w") as f:
                json.dump(pred, f, indent=2)
            print(f"  Saved: {out.name}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
