#!/usr/bin/env python3
"""
scout/game_analysis.py — Game Analysis PDF Generator (D3)
Team 2950 — The Devastators

Produces a 1690-style post-season retrospective document covering:
  - Game overview + scoring model
  - Attribution β for the season + what it revealed
  - Top teams analysis (EPA, synergy, [ELITE] flags)
  - Oracle rule performance (accuracy, confidence, per-rule contributions)
  - Regional/district insights (from cache)
  - Strategic takeaways

Usage:
  python -m scout.game_analysis --year 2025 --output reports/reefscape_2025.pdf
  python -m scout.game_analysis --year 2025 --markdown

Data sources (cache-only, no network):
  blueprint/attribution_betas  → β + CI
  .cache/statbotics/           → per-team season data
  blueprint/rule_ablation      → Oracle rule performance
  blueprint/oracle.py          → game parameters

NO new network fetches are made — all data is read from local cache.
Every number is traced to a cache file + sample size.
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Path setup ──────────────────────────────────────────────────────────────
_SCOUT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCOUT_DIR.parent
_BLUEPRINT_DIR = _REPO_ROOT / "blueprint"
_CACHE_DIR = _REPO_ROOT / ".cache" / "statbotics"

for _p in [str(_SCOUT_DIR), str(_BLUEPRINT_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Optional deps ────────────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    from attribution_betas import get_attribution_beta, ATTRIBUTION_BETAS
    HAS_ATTRIBUTION_BETAS = True
except ImportError:
    HAS_ATTRIBUTION_BETAS = False

try:
    from oracle import (
        apply_rules, HISTORICAL_GAMES, GROUND_TRUTH, CONFIDENCE_POLICY,
    )
    HAS_ORACLE = True
except ImportError:
    HAS_ORACLE = False

try:
    from rule_ablation import run_full_ablation
    HAS_ABLATION = True
except ImportError:
    HAS_ABLATION = False

# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TeamEntry:
    """Single team row in the top-teams table."""
    team: int
    name: str
    epa_total: float
    epa_auto: float
    epa_teleop: float
    epa_endgame: float
    wins: int
    losses: int
    n_events: int
    is_elite: bool          # [ELITE] flag — top-5% EPA
    district: str = ""
    state: str = ""

    @property
    def winrate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total else 0.0


@dataclass
class BetaSection:
    """Attribution β narrative for a season."""
    year: int
    game_name: str
    prior_beta: float
    empirical_beta: Optional[float]
    empirical_ci: Optional[tuple]
    tuned_on: int               # match count
    prior_reason: str
    interpretation: str         # human narrative
    data_available: bool


@dataclass
class OracleRuleRow:
    """Per-rule ablation summary row."""
    rule_id: str
    mean_confidence: float
    confidence_delta: float     # vs baseline (positive = this rule contributes)
    arch_accuracy: float
    arch_accuracy_delta: float
    is_significant: bool
    note: str = ""


@dataclass
class OracleSection:
    """Oracle rule-performance section."""
    year: int
    baseline_win_accuracy: float
    baseline_confidence: float
    n_matches: int
    rules: list[OracleRuleRow]
    ci_low: float
    ci_high: float
    data_available: bool
    note: str = ""


@dataclass
class RegionalInsight:
    """Per-district/region summary."""
    name: str                   # e.g. "FIT", "FIM", "PNW"
    team_count: int
    mean_epa: float
    top_team: int
    top_team_epa: float
    median_epa: float


@dataclass
class GameAnalysisReport:
    """Full post-season retrospective report."""
    year: int
    game_name: str

    # Section 1 — game overview
    overview: str
    scoring_model: str          # text description of scoring targets + β-model
    scoring_model_source: str   # e.g. "HISTORICAL_GAMES['2025'], oracle.py"

    # Section 2 — Attribution β
    beta: BetaSection

    # Section 3 — Top teams
    top_teams: list[TeamEntry]
    top_teams_sample_size: int  # number of teams in cache
    top_teams_source: str
    elite_threshold_epa: float  # EPA cutoff for [ELITE]

    # Section 4 — Oracle rule performance
    oracle: OracleSection

    # Section 5 — Regional insights
    regional_insights: list[RegionalInsight]
    regional_source: str

    # Section 6 — Strategic takeaways
    strategic_takeaways: list[str]
    strategic_notes: str

    # Meta
    data_sources_summary: str
    generated_at: str


# ════════════════════════════════════════════════════════════════════════════
# CACHE LOADERS (no network)
# ════════════════════════════════════════════════════════════════════════════

def _load_team_years(year: int) -> list[dict]:
    """Load all cached team-year records for *year* from statbotics cache."""
    pattern = str(_CACHE_DIR / f"team_years_{year}_*.json")
    records: list[dict] = []
    for fpath in sorted(glob.glob(pattern)):
        try:
            with open(fpath, "r") as f:
                chunk = json.load(f)
            if isinstance(chunk, list):
                records.extend(chunk)
        except (json.JSONDecodeError, OSError):
            pass
    return records


def _load_matches(year: int, qual_only: bool = True) -> list[dict]:
    """Load cached match records for *year*."""
    pattern = str(_CACHE_DIR / f"matches_{year}_*.json")
    records: list[dict] = []
    for fpath in sorted(glob.glob(pattern)):
        try:
            with open(fpath, "r") as f:
                chunk = json.load(f)
            if isinstance(chunk, list):
                records.extend(chunk)
        except (json.JSONDecodeError, OSError):
            pass
    if qual_only:
        records = [m for m in records if m.get("comp_level") == "qm"]
    return records


# ════════════════════════════════════════════════════════════════════════════
# SECTION BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def _build_overview(year: int) -> tuple[str, str, str]:
    """Return (overview_text, scoring_model_text, scoring_model_source)."""
    if not HAS_ORACLE:
        return (
            f"FRC {year} season overview. Oracle module unavailable.",
            "Scoring model data not available — oracle.py import failed.",
            "n/a",
        )

    game_key = str(year)
    if game_key not in HISTORICAL_GAMES:
        return (
            f"FRC {year} season. Game parameters not in HISTORICAL_GAMES.",
            "Scoring model data not available for this year.",
            "oracle.py::HISTORICAL_GAMES",
        )

    g = HISTORICAL_GAMES[game_key]
    targets = g.scoring_targets if hasattr(g, "scoring_targets") else []

    target_lines = []
    for t in targets:
        cap = f" (cap {t.get('max_alliance_pts')} pts)" if t.get("cap_type") == "capped" else ""
        target_lines.append(
            f"  • {t['name']}: Auto={t.get('auto_pts',0)} | "
            f"Teleop={t.get('teleop_pts',0)}{cap}"
        )

    piece_desc = getattr(g, "game_piece_name", "unknown")
    second = ""
    if getattr(g, "has_second_piece", False):
        second = f" + {getattr(g, 'second_piece_name', 'secondary piece')}"

    overview = (
        f"FRC {year}: {g.game_name}\n\n"
        f"Game pieces: {piece_desc}{second}\n"
        f"Endgame: {getattr(g, 'endgame_type', 'unknown')} "
        f"({getattr(g, 'endgame_points', 0)} pts)\n"
        f"Estimated winning score: {getattr(g, 'estimated_winning_score', 'n/a')} pts\n"
        f"Field obstacles: {'Yes' if getattr(g, 'field_has_obstacles', False) else 'No'}\n"
        f"Shared/contested pieces: {'Yes' if getattr(g, 'pieces_shared_contested', False) else 'No'}"
    )

    scoring_model = "Scoring targets:\n" + "\n".join(target_lines) if target_lines else "No scoring target data."
    source = "oracle.py::HISTORICAL_GAMES"
    return overview, scoring_model, source


def _build_beta_section(year: int) -> BetaSection:
    """Build attribution β narrative."""
    if not HAS_ATTRIBUTION_BETAS or year not in ATTRIBUTION_BETAS:
        game_name = "Unknown"
        if HAS_ORACLE and str(year) in HISTORICAL_GAMES:
            game_name = HISTORICAL_GAMES[str(year)].game_name
        return BetaSection(
            year=year,
            game_name=game_name,
            prior_beta=float("nan"),
            empirical_beta=None,
            empirical_ci=None,
            tuned_on=0,
            prior_reason="attribution_betas.py not available",
            interpretation="Beta data not available for this season.",
            data_available=False,
        )

    entry = ATTRIBUTION_BETAS[year]
    prior = entry.get("prior_expected_beta", float("nan"))
    empirical = entry.get("empirical_beta")
    ci = entry.get("empirical_ci")
    tuned_on = entry.get("tuned_on_match_count", 0)
    game_name = entry.get("game_name", "Unknown")
    prior_reason = entry.get("prior_reason", "")

    # Narrative interpretation
    if empirical is None:
        interp = (
            f"Empirical β not yet computed (TODO: run tune_attribution_beta.py). "
            f"Prior β={prior:.2f} — {prior_reason}."
        )
        avail = False
    else:
        delta = empirical - prior
        direction = "higher" if delta > 0 else "lower"
        if abs(delta) < 0.05:
            interp = (
                f"β={empirical:.2f} (prior={prior:.2f}) — seasons aligned closely with prior. "
                f"{prior_reason}. "
                f"95% CI: {ci} on {tuned_on:,} matches."
            )
        else:
            interp = (
                f"β={empirical:.2f} (prior={prior:.2f}, Δ={delta:+.2f}). "
                f"Empirical was {direction} than prior. "
                f"{prior_reason}. "
                f"95% CI: {ci} on {tuned_on:,} matches. "
                f"A {'higher' if delta>0 else 'lower'} β indicates "
                f"{'more' if delta>0 else 'less'} inter-robot coupling than expected."
            )
        avail = True

    return BetaSection(
        year=year,
        game_name=game_name,
        prior_beta=prior,
        empirical_beta=empirical,
        empirical_ci=ci,
        tuned_on=tuned_on,
        prior_reason=prior_reason,
        interpretation=interp,
        data_available=avail,
    )


def _build_top_teams(year: int, top_n: int = 25) -> tuple[list[TeamEntry], int, str, float]:
    """Return (entries, sample_size, source, elite_threshold)."""
    records = _load_team_years(year)
    if not records:
        return [], 0, f".cache/statbotics/team_years_{year}_*.json (empty)", 0.0

    # Parse EPA
    teams: list[dict] = []
    for r in records:
        epa_block = r.get("epa", {})
        bd = epa_block.get("breakdown", {})
        total = epa_block.get("total_points", {})
        epa_total = total.get("mean", bd.get("total_points", 0.0)) if isinstance(total, dict) else float(total or 0)
        if not isinstance(epa_total, (int, float)) or math.isnan(epa_total):
            continue
        record = r.get("record", {})
        season_record = r.get("season", {})
        wins = record.get("wins", season_record.get("wins", 0))
        losses = record.get("losses", season_record.get("losses", 0))
        n_events = r.get("count", {}).get("events", 0) or season_record.get("count", 0) or 0

        teams.append({
            "team": r.get("team", 0),
            "name": r.get("name", ""),
            "epa_total": float(epa_total),
            "epa_auto": float(bd.get("auto_points", 0) or 0),
            "epa_teleop": float(bd.get("teleop_points", 0) or 0),
            "epa_endgame": float(bd.get("endgame_points", 0) or 0),
            "wins": int(wins),
            "losses": int(losses),
            "n_events": int(n_events),
            "district": r.get("district", "") or "",
            "state": r.get("state", "") or "",
        })

    if not teams:
        return [], len(records), f".cache/statbotics/team_years_{year}_*.json ({len(records)} records, parse failed)", 0.0

    teams.sort(key=lambda t: t["epa_total"], reverse=True)
    sample_size = len(teams)

    # Elite threshold: top 5%
    cutoff_idx = max(0, int(len(teams) * 0.05) - 1)
    elite_threshold = teams[cutoff_idx]["epa_total"] if teams else 0.0

    entries = []
    for t in teams[:top_n]:
        entries.append(TeamEntry(
            team=t["team"],
            name=t["name"],
            epa_total=t["epa_total"],
            epa_auto=t["epa_auto"],
            epa_teleop=t["epa_teleop"],
            epa_endgame=t["epa_endgame"],
            wins=t["wins"],
            losses=t["losses"],
            n_events=t["n_events"],
            is_elite=t["epa_total"] >= elite_threshold,
            district=t["district"],
            state=t["state"],
        ))

    source = f".cache/statbotics/team_years_{year}_*.json ({sample_size} teams)"
    return entries, sample_size, source, elite_threshold


def _build_oracle_section(year: int) -> OracleSection:
    """Run rule ablation and return oracle performance section."""
    if not HAS_ABLATION or not HAS_ORACLE:
        return OracleSection(
            year=year,
            baseline_win_accuracy=0.0,
            baseline_confidence=0.0,
            n_matches=0,
            rules=[],
            ci_low=0.0,
            ci_high=0.0,
            data_available=False,
            note="Oracle or rule_ablation module not available.",
        )

    try:
        ablation = run_full_ablation(year)
    except Exception as exc:
        return OracleSection(
            year=year,
            baseline_win_accuracy=0.0,
            baseline_confidence=0.0,
            n_matches=0,
            rules=[],
            ci_low=0.0,
            ci_high=0.0,
            data_available=False,
            note=f"Ablation run failed: {exc}",
        )

    baseline = ablation.get("baseline")
    if baseline is None:
        return OracleSection(
            year=year,
            baseline_win_accuracy=0.0,
            baseline_confidence=0.0,
            n_matches=0,
            rules=[],
            ci_low=0.0,
            ci_high=0.0,
            data_available=False,
            note="Ablation returned no baseline.",
        )

    rows: list[OracleRuleRow] = []
    for key, result in ablation.items():
        if key == "baseline":
            continue
        rule_id = key.replace("disable_", "")
        # confidence_delta from ablation: baseline.conf - disabled.conf (positive = rule contributes)
        cd = baseline.mean_confidence - result.mean_confidence
        aad = baseline.arch_accuracy - result.arch_accuracy
        rows.append(OracleRuleRow(
            rule_id=rule_id,
            mean_confidence=result.mean_confidence,
            confidence_delta=cd,
            arch_accuracy=result.arch_accuracy,
            arch_accuracy_delta=aad,
            is_significant=result.is_significant,
        ))

    rows.sort(key=lambda r: r.confidence_delta, reverse=True)

    return OracleSection(
        year=year,
        baseline_win_accuracy=baseline.win_accuracy,
        baseline_confidence=baseline.mean_confidence,
        n_matches=baseline.n_matches,
        rules=rows,
        ci_low=baseline.ci_low,
        ci_high=baseline.ci_high,
        data_available=True,
    )


def _build_regional_insights(year: int, team_records: list[dict]) -> tuple[list[RegionalInsight], str]:
    """Aggregate per-district/state from cached team records."""
    if not team_records:
        return [], f".cache/statbotics/team_years_{year}_*.json (empty)"

    by_district: dict[str, list[float]] = {}
    district_teams: dict[str, list[dict]] = {}
    for r in team_records:
        epa_block = r.get("epa", {})
        total = epa_block.get("total_points", {})
        epa_total = total.get("mean", 0.0) if isinstance(total, dict) else float(total or 0)
        if not isinstance(epa_total, (int, float)) or math.isnan(epa_total) or epa_total <= 0:
            continue
        district = r.get("district", "") or "Independent"
        if not district:
            district = "Independent"
        by_district.setdefault(district, []).append(epa_total)
        district_teams.setdefault(district, []).append({
            "team": r.get("team", 0),
            "name": r.get("name", ""),
            "epa": epa_total,
        })

    insights: list[RegionalInsight] = []
    for dist, epas in by_district.items():
        if not epas:
            continue
        sorted_epas = sorted(epas, reverse=True)
        n = len(sorted_epas)
        median_val = sorted_epas[n // 2] if n else 0.0
        top_team_rec = max(district_teams[dist], key=lambda x: x["epa"])
        insights.append(RegionalInsight(
            name=dist,
            team_count=n,
            mean_epa=sum(epas) / n,
            top_team=top_team_rec["team"],
            top_team_epa=top_team_rec["epa"],
            median_epa=median_val,
        ))

    insights.sort(key=lambda x: x.mean_epa, reverse=True)
    source = f".cache/statbotics/team_years_{year}_*.json ({len(team_records)} records)"
    return insights[:15], source


def _build_strategic_takeaways(
    year: int,
    beta: BetaSection,
    top_teams: list[TeamEntry],
    oracle: OracleSection,
    regionals: list[RegionalInsight],
) -> tuple[list[str], str]:
    """Generate data-grounded strategic takeaways."""
    takeaways: list[str] = []
    notes_parts: list[str] = []

    # β takeaway
    if beta.data_available and beta.empirical_beta is not None:
        b = beta.empirical_beta
        if b >= 0.80:
            takeaways.append(
                f"High coupling game (β={b:.2f}): alliance synergy matters more than individual EPA. "
                f"Draft for role complementarity, not just peak EPA."
            )
        elif b >= 0.60:
            takeaways.append(
                f"Moderate coupling (β={b:.2f}): individual EPA remains the strongest predictor, "
                f"but alliance composition still adds ~{round((1-b)*100)}% of variance."
            )
        else:
            takeaways.append(
                f"Low coupling (β={b:.2f}): {beta.game_name} rewards independent scorers. "
                f"Three strong soloists beat three role-specialized partners."
            )
    elif not beta.data_available:
        notes_parts.append(f"Attribution β not empirically tuned for {year}; takeaways are prior-based.")
        if beta.prior_beta and not math.isnan(beta.prior_beta):
            takeaways.append(f"Prior β={beta.prior_beta:.2f} (not yet empirically confirmed): {beta.prior_reason}.")

    # Elite team takeaway
    if top_teams:
        elite_count = sum(1 for t in top_teams if t.is_elite)
        top = top_teams[0]
        takeaways.append(
            f"Top team: {top.team} ({top.name}) with EPA={top.epa_total:.1f}. "
            f"{elite_count} teams in [ELITE] tier (top 5% EPA)."
        )
        # Auto vs teleop split
        if top.epa_auto + top.epa_teleop + top.epa_endgame > 0:
            auto_pct = top.epa_auto / top.epa_total * 100 if top.epa_total else 0
            end_pct = top.epa_endgame / top.epa_total * 100 if top.epa_total else 0
            if auto_pct > 25:
                takeaways.append(
                    f"Auto scoring is load-bearing: top team earns {auto_pct:.0f}% of EPA in auto. "
                    f"Teams that skip auto are giving up structural EPA."
                )
            if end_pct > 20:
                takeaways.append(
                    f"Endgame matters: {end_pct:.0f}% of top EPA from endgame — "
                    f"consistent climbers dominate the bracket."
                )

    # Oracle takeaway
    if oracle.data_available and oracle.rules:
        top_rule = oracle.rules[0]
        takeaways.append(
            f"Most load-bearing Oracle rule: {top_rule.rule_id} "
            f"(Δconf={top_rule.confidence_delta:+.3f} vs baseline confidence {oracle.baseline_confidence:.2f}). "
            f"Architectural accuracy baseline: {oracle.arch_accuracy if hasattr(oracle, 'arch_accuracy') else 'n/a'}."
        )
        sig_count = sum(1 for r in oracle.rules if r.is_significant)
        if sig_count:
            takeaways.append(
                f"{sig_count} of {len(oracle.rules)} Oracle rules show statistically significant "
                f"confidence contribution. Statbotics win-pred accuracy: "
                f"{oracle.baseline_win_accuracy:.1%} (95% CI: {oracle.ci_low:.1%}–{oracle.ci_high:.1%}, "
                f"n={oracle.n_matches:,} qual matches)."
            )
    elif not oracle.data_available:
        notes_parts.append(f"Oracle ablation not available for {year}: {oracle.note}")

    # Regional takeaway
    if regionals:
        top_dist = regionals[0]
        takeaways.append(
            f"Strongest district by mean EPA: {top_dist.name} "
            f"(mean={top_dist.mean_epa:.1f}, n={top_dist.team_count} teams). "
            f"Top team in district: #{top_dist.top_team} (EPA={top_dist.top_team_epa:.1f})."
        )

    # Generic forward-looking note
    takeaways.append(
        f"Watch next season: game designers often swing β from high↔low in alternating cycles. "
        f"If {year} was high-coupling, expect more independent scoring in the next game."
    )

    notes = " | ".join(notes_parts) if notes_parts else "All takeaways are data-grounded from cache."
    return takeaways, notes


# ════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ════════════════════════════════════════════════════════════════════════════

def generate_game_analysis(
    year: int,
    data_sources: dict | None = None,
) -> GameAnalysisReport:
    """Generate a post-season retrospective report for *year*.

    Parameters
    ----------
    year        : FRC season year (e.g. 2025)
    data_sources: optional override dict — keys map to pre-loaded data.
                  Currently unused by default; hook for dependency injection
                  in tests. Supported keys: "team_records", "match_records".

    Returns
    -------
    GameAnalysisReport dataclass (fully populated; sections that cannot be
    populated from cache are marked "data not available").
    """
    import datetime
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Pull data sources
    ds = data_sources or {}
    team_records = ds.get("team_records") or _load_team_years(year)
    # (match_records available if needed in future sections)

    # Section 1: overview
    overview, scoring_model, scoring_source = _build_overview(year)

    # Section 2: β
    beta = _build_beta_section(year)

    # Section 3: top teams
    top_teams, sample_size, top_teams_source, elite_threshold = _build_top_teams(
        year, top_n=25
    )
    if not top_teams and team_records:
        # fallback: rebuild from injected records
        ds2 = {"team_records": team_records}
        top_teams, sample_size, top_teams_source, elite_threshold = _build_top_teams(year, top_n=25)

    # Section 4: oracle
    oracle = _build_oracle_section(year)

    # Section 5: regionals
    regional_insights, regional_source = _build_regional_insights(year, team_records)

    # Section 6: takeaways
    strategic_takeaways, strategic_notes = _build_strategic_takeaways(
        year, beta, top_teams, oracle, regional_insights
    )

    # Derive game name
    game_name = "Unknown"
    if beta.game_name and beta.game_name != "Unknown":
        game_name = beta.game_name
    elif HAS_ORACLE and str(year) in HISTORICAL_GAMES:
        game_name = HISTORICAL_GAMES[str(year)].game_name

    # Sources summary
    sources: list[str] = []
    sources.append(f"team_years: {top_teams_source}")
    sources.append(f"scoring model: {scoring_source}")
    if beta.data_available:
        sources.append(f"attribution_beta: blueprint/attribution_betas.py ({beta.tuned_on:,} matches)")
    if oracle.data_available:
        sources.append(f"rule_ablation: blueprint/rule_ablation.py ({oracle.n_matches:,} qual matches)")
    sources.append(f"regionals: {regional_source}")
    data_sources_summary = "\n".join(f"  • {s}" for s in sources)

    return GameAnalysisReport(
        year=year,
        game_name=game_name,
        overview=overview,
        scoring_model=scoring_model,
        scoring_model_source=scoring_source,
        beta=beta,
        top_teams=top_teams,
        top_teams_sample_size=sample_size,
        top_teams_source=top_teams_source,
        elite_threshold_epa=elite_threshold,
        oracle=oracle,
        regional_insights=regional_insights,
        regional_source=regional_source,
        strategic_takeaways=strategic_takeaways,
        strategic_notes=strategic_notes,
        data_sources_summary=data_sources_summary,
        generated_at=generated_at,
    )


# ════════════════════════════════════════════════════════════════════════════
# RENDERERS
# ════════════════════════════════════════════════════════════════════════════

def _hr(char: str = "═", width: int = 72) -> str:
    return char * width


def render_markdown(report: GameAnalysisReport) -> str:
    """Render report to Markdown string."""
    lines: list[str] = []

    lines.append(f"# FRC {report.year} Game Analysis — {report.game_name}")
    lines.append(f"*Team 2950 — The Devastators | Generated: {report.generated_at}*")
    lines.append("")

    # ── Data Sources ───────────────────────────────────────────────────────
    lines.append("## Data Sources")
    lines.append(report.data_sources_summary)
    lines.append("")

    # ── Section 1: Game Overview ───────────────────────────────────────────
    lines.append("## 1. Game Overview")
    lines.append(report.overview)
    lines.append("")
    lines.append("### Scoring Model")
    lines.append(report.scoring_model)
    lines.append(f"*Source: {report.scoring_model_source}*")
    lines.append("")

    # ── Section 2: Attribution β ───────────────────────────────────────────
    lines.append("## 2. Attribution β — Season Coupling Analysis")
    b = report.beta
    if b.data_available:
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Game | {b.game_name} |")
        lines.append(f"| Prior β | {b.prior_beta:.2f} |")
        empirical_str = f"{b.empirical_beta:.2f}" if b.empirical_beta is not None else "TODO"
        lines.append(f"| Empirical β | {empirical_str} |")
        ci_str = f"{b.empirical_ci[0]:.2f}–{b.empirical_ci[1]:.2f}" if b.empirical_ci else "n/a"
        lines.append(f"| 95% CI | {ci_str} |")
        lines.append(f"| Tuned on | {b.tuned_on:,} matches |")
        lines.append("")
        lines.append(f"**Interpretation:** {b.interpretation}")
    else:
        lines.append(f"> Data not available: {b.interpretation}")
    lines.append("")

    # ── Section 3: Top Teams ───────────────────────────────────────────────
    lines.append("## 3. Top Teams Analysis")
    lines.append(
        f"*Source: {report.top_teams_source} | Sample: {report.top_teams_sample_size} teams | "
        f"[ELITE] threshold: EPA ≥ {report.elite_threshold_epa:.1f}*"
    )
    lines.append("")
    if report.top_teams:
        lines.append("| Rank | Team | Name | EPA | Auto | Teleop | EG | W-L | Events | |")
        lines.append("|------|------|------|-----|------|--------|----|-----|--------|--|")
        for rank, t in enumerate(report.top_teams, 1):
            flag = "[ELITE]" if t.is_elite else ""
            dist = f"{t.district.upper()}" if t.district else t.state or ""
            lines.append(
                f"| {rank} | {t.team} | {t.name[:24]} | {t.epa_total:.1f} | "
                f"{t.epa_auto:.1f} | {t.epa_teleop:.1f} | {t.epa_endgame:.1f} | "
                f"{t.wins}-{t.losses} | {t.n_events} | {flag} {dist} |"
            )
    else:
        lines.append("> Top teams data not available — cache empty for this year.")
    lines.append("")

    # ── Section 4: Oracle Rule Performance ────────────────────────────────
    lines.append("## 4. Oracle Rule Performance")
    o = report.oracle
    if o.data_available:
        lines.append(
            f"*Baseline win accuracy: {o.baseline_win_accuracy:.1%} "
            f"(95% CI: {o.ci_low:.1%}–{o.ci_high:.1%}, n={o.n_matches:,} qual matches) | "
            f"Baseline confidence: {o.baseline_confidence:.3f}*"
        )
        lines.append("")
        lines.append("| Rule | Δ Confidence | Arch Acc | Δ Arch Acc | Significant |")
        lines.append("|------|-------------|----------|------------|-------------|")
        for r in o.rules:
            sig = "✓" if r.is_significant else ""
            lines.append(
                f"| {r.rule_id} | {r.confidence_delta:+.4f} | "
                f"{r.arch_accuracy:.2%} | {r.arch_accuracy_delta:+.4f} | {sig} |"
            )
        if o.note:
            lines.append(f"\n*Note: {o.note}*")
    else:
        lines.append(f"> Oracle data not available: {o.note}")
    lines.append("")

    # ── Section 5: Regional Insights ──────────────────────────────────────
    lines.append("## 5. Regional / District Insights")
    lines.append(f"*Source: {report.regional_source}*")
    lines.append("")
    if report.regional_insights:
        lines.append("| District | Teams | Mean EPA | Median EPA | Top Team | Top EPA |")
        lines.append("|----------|-------|----------|------------|----------|---------|")
        for ri in report.regional_insights:
            lines.append(
                f"| {ri.name.upper()} | {ri.team_count} | {ri.mean_epa:.1f} | "
                f"{ri.median_epa:.1f} | #{ri.top_team} | {ri.top_team_epa:.1f} |"
            )
    else:
        lines.append("> Regional data not available — cache empty for this year.")
    lines.append("")

    # ── Section 6: Strategic Takeaways ────────────────────────────────────
    lines.append("## 6. Strategic Takeaways")
    if report.strategic_takeaways:
        for i, t in enumerate(report.strategic_takeaways, 1):
            lines.append(f"{i}. {t}")
    else:
        lines.append("> No takeaways generated.")
    if report.strategic_notes:
        lines.append(f"\n*Notes: {report.strategic_notes}*")
    lines.append("")

    lines.append("---")
    lines.append(
        f"*Report generated by Team 2950 The Engine · scout/game_analysis.py · "
        f"All numbers traceable to cache — no fabrication.*"
    )

    return "\n".join(lines)


def _make_epa_bar_chart(report: GameAnalysisReport, output_path: Path) -> Optional[Path]:
    """Generate EPA bar chart using matplotlib. Returns path or None."""
    if not HAS_MATPLOTLIB or not report.top_teams:
        return None
    try:
        teams = report.top_teams[:20]
        labels = [str(t.team) for t in teams]
        autos = [t.epa_auto for t in teams]
        teleops = [t.epa_teleop for t in teams]
        endgames = [t.epa_endgame for t in teams]

        x = range(len(labels))
        fig, ax = plt.subplots(figsize=(12, 5))
        bar_w = 0.6
        ax.bar(x, autos, bar_w, label="Auto", color="#2196F3")
        ax.bar(x, teleops, bar_w, bottom=autos, label="Teleop", color="#4CAF50")
        bottom2 = [a + tl for a, tl in zip(autos, teleops)]
        ax.bar(x, endgames, bar_w, bottom=bottom2, label="Endgame", color="#FF9800")

        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("EPA")
        ax.set_title(f"FRC {report.year} — Top {len(teams)} Teams by EPA (stacked)")
        ax.legend()
        plt.tight_layout()
        chart_path = output_path.with_suffix(".epa_chart.png")
        fig.savefig(chart_path, dpi=120)
        plt.close(fig)
        return chart_path
    except Exception:
        return None


def render_pdf(report: GameAnalysisReport, output_path: str | Path) -> None:
    """Render report to PDF.

    Strategy (in order of preference):
      1. matplotlib multipage PDF (MatplotlibPdfPages)
      2. Text-only PDF via matplotlib (fallback)
      3. Write .txt file + raise informative exception
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not HAS_MATPLOTLIB:
        # Write markdown as .txt fallback
        txt_path = output_path.with_suffix(".md")
        txt_path.write_text(render_markdown(report))
        raise RuntimeError(
            f"matplotlib not available — wrote Markdown to {txt_path}. "
            f"Install matplotlib to generate PDF."
        )

    from matplotlib.backends.backend_pdf import PdfPages

    md_text = render_markdown(report)
    chart_path = _make_epa_bar_chart(report, output_path)

    with PdfPages(str(output_path)) as pdf:
        # ── Cover page ────────────────────────────────────────────────────
        fig = plt.figure(figsize=(8.5, 11))
        fig.patch.set_facecolor("#1a1a2e")
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.75, f"FRC {report.year}", ha="center", va="center",
                fontsize=42, color="white", fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.5, 0.65, report.game_name, ha="center", va="center",
                fontsize=28, color="#e94560",
                transform=ax.transAxes)
        ax.text(0.5, 0.55, "Post-Season Game Analysis", ha="center", va="center",
                fontsize=18, color="#a8a8b3",
                transform=ax.transAxes)
        ax.text(0.5, 0.45, "Team 2950 — The Devastators", ha="center", va="center",
                fontsize=14, color="#a8a8b3",
                transform=ax.transAxes)
        ax.text(0.5, 0.38, f"Generated: {report.generated_at}", ha="center", va="center",
                fontsize=10, color="#6c6c8a",
                transform=ax.transAxes)
        pdf.savefig(fig)
        plt.close(fig)

        # ── EPA bar chart page ────────────────────────────────────────────
        if chart_path and chart_path.exists():
            fig2, ax2 = plt.subplots(figsize=(8.5, 5))
            img = plt.imread(str(chart_path))
            ax2.imshow(img)
            ax2.axis("off")
            ax2.set_title(f"Top Teams EPA — {report.year} {report.game_name}")
            pdf.savefig(fig2, bbox_inches="tight")
            plt.close(fig2)

        # ── Text content pages ────────────────────────────────────────────
        CHARS_PER_LINE = 85
        LINES_PER_PAGE = 52
        lines = md_text.split("\n")

        page_lines: list[str] = []
        for raw_line in lines:
            # Simple word-wrap for very long lines
            if len(raw_line) > CHARS_PER_LINE:
                words = raw_line.split()
                cur = ""
                for w in words:
                    if len(cur) + len(w) + 1 <= CHARS_PER_LINE:
                        cur = cur + " " + w if cur else w
                    else:
                        page_lines.append(cur)
                        cur = w
                if cur:
                    page_lines.append(cur)
            else:
                page_lines.append(raw_line)

            if len(page_lines) >= LINES_PER_PAGE:
                _flush_text_page(pdf, page_lines[:LINES_PER_PAGE], report)
                page_lines = page_lines[LINES_PER_PAGE:]

        if page_lines:
            _flush_text_page(pdf, page_lines, report)

        # PDF metadata
        d = pdf.infodict()
        d["Title"] = f"FRC {report.year} Game Analysis — {report.game_name}"
        d["Author"] = "Team 2950 The Engine"
        d["Subject"] = "Post-Season Retrospective"

    # Cleanup temp chart
    if chart_path and chart_path.exists():
        try:
            chart_path.unlink()
        except OSError:
            pass


def _flush_text_page(pdf: "PdfPages", lines: list[str], report: GameAnalysisReport) -> None:
    """Render a page of text lines to pdf."""
    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_subplot(111)
    ax.axis("off")
    text_content = "\n".join(lines)
    ax.text(
        0.03, 0.97, text_content,
        ha="left", va="top",
        fontsize=7,
        fontfamily="monospace",
        transform=ax.transAxes,
        wrap=False,
    )
    # Footer
    ax.text(
        0.5, 0.01,
        f"FRC {report.year} · {report.game_name} · Team 2950 The Engine",
        ha="center", va="bottom",
        fontsize=6, color="gray",
        transform=ax.transAxes,
    )
    pdf.savefig(fig)
    plt.close(fig)


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Game Analysis PDF generator — Team 2950 The Engine (D3)",
        prog="python -m scout.game_analysis",
    )
    parser.add_argument("--year", type=int, default=2025, help="FRC season year (default 2025)")
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for PDF (default: reports/game_analysis_{year}.pdf)",
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Also write Markdown alongside PDF",
    )
    parser.add_argument(
        "--md-only", action="store_true",
        help="Write Markdown only (no PDF)",
    )
    args = parser.parse_args()

    year = args.year
    output = args.output or f"reports/game_analysis_{year}.pdf"
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[game_analysis] Generating FRC {year} retrospective...")
    report = generate_game_analysis(year)
    print(f"[game_analysis] Game: {report.game_name}")
    print(f"[game_analysis] Teams in cache: {report.top_teams_sample_size}")
    print(f"[game_analysis] β available: {report.beta.data_available}")
    print(f"[game_analysis] Oracle available: {report.oracle.data_available}")
    print(f"[game_analysis] Regionals: {len(report.regional_insights)}")

    md_text = render_markdown(report)

    if args.md_only:
        md_path = output_path.with_suffix(".md")
        md_path.write_text(md_text)
        print(f"[game_analysis] Markdown written to {md_path}")
        return

    if args.markdown:
        md_path = output_path.with_suffix(".md")
        md_path.write_text(md_text)
        print(f"[game_analysis] Markdown written to {md_path}")

    try:
        render_pdf(report, output_path)
        print(f"[game_analysis] PDF written to {output_path}")
    except RuntimeError as exc:
        print(f"[game_analysis] PDF skipped: {exc}")


if __name__ == "__main__":
    _cli()
