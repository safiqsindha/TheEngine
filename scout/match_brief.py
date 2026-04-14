#!/usr/bin/env python3
"""
The Engine — Match Brief Generator
Team 2950 — The Devastators

Generates a pre-match PDF/markdown brief surfacing key synergies, anomaly
flags, β-adjusted predictions, complementarity regime, and per-robot expected
contribution for team strategists and drive-team coaching.

Usage:
  from scout.match_brief import generate_match_brief, render_markdown

  brief = generate_match_brief(
      event_key="2025wor",
      match_key="qm1",
      year=2025,
      our_team_number=2950,
  )
  md = render_markdown(brief)

CLI:
  python -m scout.match_brief --event 2025wor --match qm1 --team 2950
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path bootstrapping — allow `from scout.match_brief import ...` and also
# direct execution from inside the scout/ directory.
# ---------------------------------------------------------------------------
_SCOUT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SCOUT_DIR.parent
_BLUEPRINT_DIR = _ROOT_DIR / "blueprint"

for _p in (_SCOUT_DIR, _ROOT_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# β regime classification thresholds
# ---------------------------------------------------------------------------
_BETA_REGIME_LABELS = [
    (0.90, "raw EPA"),          # β ≥ 0.90: near-linear, raw EPA dominates
    (0.75, "moderate coupling"),  # β ∈ [0.75, 0.90)
    (0.60, "role specialists"),  # β ∈ [0.60, 0.75)
    (0.00, "specialists"),       # β < 0.60: heavy role specialisation
]


def _beta_regime(beta: float) -> str:
    for threshold, label in _BETA_REGIME_LABELS:
        if beta >= threshold:
            return label
    return "specialists"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TeamBrief:
    """Per-robot section within an AllianceBrief."""
    team_number: int
    epa: float
    attributed_credit: float          # β-adjusted credit share (0–1 fraction)
    anomaly_flags: list[str] = field(default_factory=list)
    synergy_partners: list[int] = field(default_factory=list)
    role_label: str = ""              # e.g. "scorer", "defender", "generalist"


@dataclass
class AllianceBrief:
    """Red or blue alliance summary."""
    color: str                        # "red" or "blue"
    teams: list[TeamBrief] = field(default_factory=list)
    total_epa: float = 0.0
    win_probability: float = 0.0


@dataclass
class Matchup:
    """One important per-robot matchup (e.g. defense × scorer pair)."""
    attacker_team: int
    defender_team: int
    description: str
    importance_score: float = 0.0    # higher = more critical


@dataclass
class MatchBrief:
    """Full pre-match brief for a single match."""
    event_key: str
    match_key: str
    year: int
    our_team_number: int
    not_participating: bool = False

    # Predicted outcome
    predicted_outcome: dict[str, Any] = field(default_factory=dict)
    # e.g. {"red_win_prob": 0.62, "blue_win_prob": 0.38, "label": "Lean Red",
    #        "confidence": "medium"}

    # Attribution β
    attribution_beta: float = 1.0
    beta_regime: str = "raw EPA"

    # Per-alliance breakdowns
    red_alliance: AllianceBrief = field(default_factory=lambda: AllianceBrief("red"))
    blue_alliance: AllianceBrief = field(default_factory=lambda: AllianceBrief("blue"))

    # Top matchup pairs
    key_matchups: list[Matchup] = field(default_factory=list)

    # Coaching bullets
    recommendations: list[str] = field(default_factory=list)

    # Data quality flags
    data_sources_used: list[str] = field(default_factory=list)
    fallback_epa_only: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_blueprint_attribution_beta(year: int) -> float:
    """Load get_attribution_beta from blueprint/attribution_betas.py."""
    try:
        spec = importlib.util.spec_from_file_location(
            "attribution_betas",
            _BLUEPRINT_DIR / "attribution_betas.py",
        )
        if spec is None or spec.loader is None:
            return 1.0
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return float(mod.get_attribution_beta(year))
    except Exception as exc:
        log.warning("attribution_betas load failed: %s — using β=1.0", exc)
        return 1.0


def _safe_import(module_name: str, path: Optional[Path] = None) -> Optional[Any]:
    """
    Import a module by name (optionally from an explicit path).
    Returns None on failure; caller handles graceful degradation.

    When path is given the module is registered in sys.modules under
    module_name so that dataclass forward-references resolve correctly
    on Python 3.9 (which evaluates annotations at class body time).
    """
    try:
        # Return cached module if already loaded
        if module_name in sys.modules:
            return sys.modules[module_name]

        if path is not None:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            # Register BEFORE exec so forward references inside the module resolve
            sys.modules[module_name] = mod
            try:
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
            except Exception:
                sys.modules.pop(module_name, None)
                raise
            return mod
        return importlib.import_module(module_name)
    except Exception as exc:
        log.debug("Optional import %s failed: %s", module_name, exc)
        return None


def _teams_for_match(
    match_key: str,
    event_key: str,
) -> Optional[dict[str, list[int]]]:
    """
    Try to resolve {red: [...], blue: [...]} from TBA cache or stand_scout state.
    Returns None if no data available.
    """
    # Try stand_scout state
    state_path = _SCOUT_DIR / ".state" / "stand_scout" / f"{event_key}_matches.json"
    if state_path.exists():
        import json
        try:
            data = json.loads(state_path.read_text())
            for m in data:
                if m.get("key") == match_key or m.get("match_key") == match_key:
                    alliances = m.get("alliances", {})
                    red = [int(t.replace("frc", "")) for t in alliances.get("red", {}).get("team_keys", [])]
                    blue = [int(t.replace("frc", "")) for t in alliances.get("blue", {}).get("team_keys", [])]
                    if red or blue:
                        return {"red": red, "blue": blue}
        except Exception as exc:
            log.debug("match state read failed: %s", exc)

    return None


def _get_team_epa(
    team_num: int,
    year: int,
    teams_db: Optional[dict],
) -> tuple[float, float]:
    """Return (epa, sd) for a team. Falls back to 0.0 if unavailable."""
    if teams_db:
        rec = teams_db.get(str(team_num), teams_db.get(team_num, {}))
        epa = float(rec.get("epa", 0.0))
        sd = float(rec.get("sd", epa * 0.25))
        return epa, sd
    return 0.0, 0.0


def _get_anomaly_flags(
    team_num: int,
    all_observations: list[dict],
) -> list[str]:
    """Run anomaly detection for one team and return human-readable flag strings."""
    anom_mod = _safe_import("anomaly", _SCOUT_DIR / "anomaly.py")
    if anom_mod is None:
        return []
    try:
        team_obs = [o for o in all_observations if int(o.get("team", 0)) == team_num]
        flags = anom_mod.detect_anomalies_robust(team_obs)
        return [f.reason for f in flags[:3]]  # top 3
    except Exception as exc:
        log.debug("anomaly detection failed for team %d: %s", team_num, exc)
        return []


def _get_synergy_partners(
    team_num: int,
    alliance_teams: list[int],
    event_matches: list[dict],
    team_epas: dict[int, dict],
) -> list[int]:
    """Return list of team numbers that have positive synergy with team_num."""
    syn_mod = _safe_import("synergy", _SCOUT_DIR / "synergy.py")
    if syn_mod is None:
        return []
    try:
        profile = syn_mod.compute_team_synergy_profile(team_num, alliance_teams, event_matches)
        partners = syn_mod.best_synergy_partners(team_num, profile, top_n=2)
        return [p for p, s in partners if s.get("overall", 0) > 0]
    except Exception as exc:
        log.debug("synergy failed for team %d: %s", team_num, exc)
        return []


def _build_team_brief(
    team_num: int,
    epa: float,
    beta: float,
    alliance_epas: list[float],
    all_obs: list[dict],
    event_matches: list[dict],
    alliance_teams: list[int],
    team_epas_db: dict[int, dict],
) -> TeamBrief:
    """Build a TeamBrief for one robot."""
    # β-adjusted credit share
    adc_mod = _safe_import("alliance_decomposition", _SCOUT_DIR / "alliance_decomposition.py")
    if adc_mod is not None and alliance_epas:
        try:
            weights = adc_mod.power_normalize(alliance_epas, beta=beta)
            idx = next((i for i, t in enumerate(alliance_teams) if t == team_num), None)
            credited = weights[idx] if idx is not None else 1.0 / len(alliance_epas)
        except Exception:
            credited = 1.0 / max(len(alliance_epas), 1)
    else:
        credited = 1.0 / max(len(alliance_epas), 1)

    anomaly_flags = _get_anomaly_flags(team_num, all_obs)
    synergy_partners = _get_synergy_partners(team_num, alliance_teams, event_matches, team_epas_db)

    # Role classification based on EPA share and play style
    epa_share = epa / max(sum(alliance_epas), 1e-6)
    if epa_share > 0.4:
        role_label = "primary scorer"
    elif epa_share < 0.15:
        role_label = "support/defender"
    else:
        role_label = "generalist"

    return TeamBrief(
        team_number=team_num,
        epa=round(epa, 1),
        attributed_credit=round(credited, 3),
        anomaly_flags=anomaly_flags,
        synergy_partners=synergy_partners,
        role_label=role_label,
    )


def _build_matchups(
    red_teams: list[TeamBrief],
    blue_teams: list[TeamBrief],
    our_team: int,
) -> list[Matchup]:
    """Generate top 3 most important per-robot matchups."""
    matchups: list[Matchup] = []

    # Pair highest EPA scorers vs each other
    red_sorted = sorted(red_teams, key=lambda t: t.epa, reverse=True)
    blue_sorted = sorted(blue_teams, key=lambda t: t.epa, reverse=True)

    for i, (r, b) in enumerate(zip(red_sorted[:3], blue_sorted[:3])):
        importance = (r.epa + b.epa) / max(r.epa + b.epa + 1, 1)
        if r.role_label == "primary scorer" and b.role_label in ("support/defender", "generalist"):
            desc = f"T{r.team_number} ({r.role_label}, EPA {r.epa}) vs T{b.team_number} ({b.role_label}) — consider assigning defender"
        elif b.role_label == "primary scorer" and r.role_label in ("support/defender", "generalist"):
            desc = f"T{b.team_number} ({b.role_label}, EPA {b.epa}) vs T{r.team_number} ({r.role_label}) — consider assigning defender"
        else:
            desc = f"T{r.team_number} (EPA {r.epa}) vs T{b.team_number} (EPA {b.epa}) — key head-to-head"
        matchups.append(Matchup(
            attacker_team=r.team_number,
            defender_team=b.team_number,
            description=desc,
            importance_score=round(importance * (1.0 - i * 0.1), 3),
        ))

    return sorted(matchups, key=lambda m: m.importance_score, reverse=True)[:3]


def _build_recommendations(
    brief: "MatchBrief",
    our_team: int,
) -> list[str]:
    """Generate 3-5 coaching bullets tailored to our team."""
    recs: list[str] = []

    # Determine which alliance we're on
    our_alliance = None
    opp_alliance = None
    for team in brief.red_alliance.teams:
        if team.team_number == our_team:
            our_alliance = brief.red_alliance
            opp_alliance = brief.blue_alliance
            break
    for team in brief.blue_alliance.teams:
        if team.team_number == our_team:
            our_alliance = brief.blue_alliance
            opp_alliance = brief.red_alliance
            break

    if our_alliance is None:
        return ["Team not found in this match — double-check alliance assignment."]

    our_team_brief = next((t for t in our_alliance.teams if t.team_number == our_team), None)

    # Win probability guidance
    our_win_prob = our_alliance.win_probability
    if our_win_prob < 0.4:
        recs.append(
            f"Underdog match ({our_win_prob*100:.0f}% win probability) — play for points, avoid risky maneuvers."
        )
    elif our_win_prob > 0.7:
        recs.append(
            f"Favored match ({our_win_prob*100:.0f}% win probability) — maintain rhythm and don't take unnecessary risks."
        )

    # Highest-EPA opponent to consider defending
    if opp_alliance and opp_alliance.teams:
        top_opp = max(opp_alliance.teams, key=lambda t: t.epa)
        if top_opp.epa > 0 and (our_team_brief is None or our_team_brief.role_label != "primary scorer"):
            recs.append(
                f"Defend team {top_opp.team_number} (opponent EPA {top_opp.epa}) — their primary scorer."
            )

    # Anomaly flags on opponents
    flagged_opps = [t for t in (opp_alliance.teams if opp_alliance else []) if t.anomaly_flags]
    for ft in flagged_opps[:1]:
        recs.append(
            f"Team {ft.team_number} has anomaly flags ({ft.anomaly_flags[0][:80]}) — may be inconsistent."
        )

    # β regime coaching
    if brief.beta_regime == "specialists":
        recs.append(
            "Low-β season (specialists regime) — rely on attributed credit shares, not raw EPA totals."
        )
    elif brief.beta_regime == "raw EPA":
        recs.append(
            "High-β season (raw EPA regime) — EPA predictions are reliable; execute your standard cycle plan."
        )

    # Synergy reminder
    if our_team_brief and our_team_brief.synergy_partners:
        partners_str = ", ".join(str(p) for p in our_team_brief.synergy_partners)
        recs.append(
            f"Positive synergy with teammate(s) {partners_str} — coordinate your cycles early."
        )

    # Fallback
    if not recs:
        recs.append("Execute standard match plan — no strong signals from available data.")

    return recs[:5]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_match_brief(
    event_key: str,
    match_key: str,
    year: int,
    our_team_number: int,
    *,
    teams_db: Optional[dict] = None,
    all_observations: Optional[list[dict]] = None,
    event_matches: Optional[list[dict]] = None,
    red_teams: Optional[list[int]] = None,
    blue_teams: Optional[list[int]] = None,
) -> MatchBrief:
    """
    Generate a pre-match brief for the given match.

    Parameters
    ----------
    event_key        : TBA event key (e.g. "2025wor")
    match_key        : TBA match key (e.g. "qm1" or "2025wor_qm1")
    year             : FRC season year
    our_team_number  : Our team number for tailored recommendations
    teams_db         : Optional dict of {team_num: {"epa": float, "sd": float}}
    all_observations : Optional list of stand_scout observation dicts
    event_matches    : Optional list of TBA match dicts (for synergy calc)
    red_teams        : Explicit red alliance team numbers (overrides auto-lookup)
    blue_teams       : Explicit blue alliance team numbers (overrides auto-lookup)

    Returns
    -------
    MatchBrief dataclass with all sections populated (degrades gracefully on
    missing data sources).
    """
    if not event_key or not match_key:
        raise ValueError("event_key and match_key are required")

    # Normalise match_key to short form (drop event prefix if present)
    short_match_key = match_key
    if match_key.startswith(event_key + "_"):
        short_match_key = match_key[len(event_key) + 1:]

    brief = MatchBrief(
        event_key=event_key,
        match_key=short_match_key,
        year=year,
        our_team_number=our_team_number,
    )

    # --- β lookup ---
    beta = _load_blueprint_attribution_beta(year)
    brief.attribution_beta = round(beta, 3)
    brief.beta_regime = _beta_regime(beta)

    # --- Resolve alliance teams ---
    if red_teams is None or blue_teams is None:
        resolved = _teams_for_match(short_match_key, event_key)
        if resolved:
            red_teams = resolved.get("red", red_teams or [])
            blue_teams = resolved.get("blue", blue_teams or [])
        else:
            red_teams = red_teams or []
            blue_teams = blue_teams or []

    all_alliance_teams = (red_teams or []) + (blue_teams or [])

    if not red_teams and not blue_teams:
        raise ValueError(f"No alliance data found for match {match_key} at {event_key}")

    # --- not_participating check ---
    if our_team_number not in all_alliance_teams:
        brief.not_participating = True
        # Still populate what we can — the brief is still useful for watching
        brief.recommendations = [
            f"Team {our_team_number} is NOT listed in this match — verify alliance assignments."
        ]

    # --- Load data sources ---
    obs = all_observations or []
    ev_matches = event_matches or []
    data_sources: list[str] = []

    if obs:
        data_sources.append("stand_scout")
    if teams_db:
        data_sources.append("teams_db")
    if ev_matches:
        data_sources.append("event_matches")
    if not data_sources:
        data_sources.append("epa_fallback")
        brief.fallback_epa_only = True

    brief.data_sources_used = data_sources

    # --- Build EPA lookup ---
    team_epas_db: dict[int, dict] = {}
    if teams_db:
        for k, v in teams_db.items():
            try:
                team_epas_db[int(k)] = v
            except (TypeError, ValueError):
                pass

    def _epa(t: int) -> float:
        rec = team_epas_db.get(t, {})
        return float(rec.get("epa", 0.0))

    def _sd(t: int) -> float:
        rec = team_epas_db.get(t, {})
        e = _epa(t)
        return float(rec.get("sd", e * 0.25))

    # --- Alliance breakdowns ---
    red_epas = [_epa(t) for t in (red_teams or [])]
    blue_epas = [_epa(t) for t in (blue_teams or [])]

    red_briefs = [
        _build_team_brief(
            t, _epa(t), beta, red_epas, obs, ev_matches,
            red_teams or [], team_epas_db,
        )
        for t in (red_teams or [])
    ]
    blue_briefs = [
        _build_team_brief(
            t, _epa(t), beta, blue_epas, obs, ev_matches,
            blue_teams or [], team_epas_db,
        )
        for t in (blue_teams or [])
    ]

    brief.red_alliance = AllianceBrief(
        color="red",
        teams=red_briefs,
        total_epa=round(sum(red_epas), 1),
    )
    brief.blue_alliance = AllianceBrief(
        color="blue",
        teams=blue_briefs,
        total_epa=round(sum(blue_epas), 1),
    )

    # --- Win probability ---
    win_mod = _safe_import("win_probability", _SCOUT_DIR / "win_probability.py")
    if win_mod is not None:
        try:
            red_tdicts = [{"epa": _epa(t), "sd": _sd(t)} for t in (red_teams or [])]
            blue_tdicts = [{"epa": _epa(t), "sd": _sd(t)} for t in (blue_teams or [])]
            wp = win_mod.win_prob_from_team_data(red_tdicts, blue_tdicts)
            label = win_mod.label_from_prob(wp)
            confidence = "high" if abs(wp - 0.5) > 0.25 else "medium" if abs(wp - 0.5) > 0.10 else "low"
            brief.predicted_outcome = {
                "red_win_prob": round(wp, 4),
                "blue_win_prob": round(1.0 - wp, 4),
                "label": label,
                "confidence": confidence,
            }
            brief.red_alliance.win_probability = round(wp, 4)
            brief.blue_alliance.win_probability = round(1.0 - wp, 4)
        except Exception as exc:
            log.warning("win_probability failed: %s", exc)
            brief.predicted_outcome = {"label": "Unknown", "red_win_prob": 0.5, "blue_win_prob": 0.5, "confidence": "low"}
    else:
        brief.predicted_outcome = {"label": "Unknown", "red_win_prob": 0.5, "blue_win_prob": 0.5, "confidence": "low"}

    # --- Key matchups ---
    brief.key_matchups = _build_matchups(red_briefs, blue_briefs, our_team_number)

    # --- Recommendations ---
    if not brief.not_participating:
        brief.recommendations = _build_recommendations(brief, our_team_number)
    # (not_participating sets recommendations to a warning above)

    return brief


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_markdown(brief: MatchBrief) -> str:
    """Render a MatchBrief as a markdown string."""
    lines: list[str] = []

    lines.append(f"# Match Brief: {brief.event_key} — {brief.match_key}")
    lines.append(f"**Year:** {brief.year}  |  **Our Team:** {brief.our_team_number}")
    if brief.not_participating:
        lines.append("\n> **WARNING:** Our team is NOT listed in this match.")
    lines.append("")

    # Predicted outcome
    lines.append("## Predicted Outcome")
    po = brief.predicted_outcome
    lines.append(f"- **{po.get('label', 'N/A')}**")
    lines.append(f"  - Red win probability: {po.get('red_win_prob', 0.5)*100:.1f}%")
    lines.append(f"  - Blue win probability: {po.get('blue_win_prob', 0.5)*100:.1f}%")
    lines.append(f"  - Confidence: {po.get('confidence', 'low')}")
    lines.append("")

    # β attribution
    lines.append("## Attribution β")
    lines.append(f"- **β = {brief.attribution_beta}** — Regime: **{brief.beta_regime}**")
    if brief.beta_regime == "specialists":
        lines.append("  - _Low β: role specialists dominate; individual EPA less predictive_")
    elif brief.beta_regime == "raw EPA":
        lines.append("  - _High β: raw EPA is highly predictive; linear attribution_")
    lines.append("")

    # Alliance breakdowns
    for alliance in (brief.red_alliance, brief.blue_alliance):
        lines.append(f"## {alliance.color.capitalize()} Alliance (EPA: {alliance.total_epa})")
        lines.append(f"Win Probability: {alliance.win_probability*100:.1f}%")
        lines.append("")
        lines.append("| Team | EPA | Credit Share | Role | Anomalies | Synergy Partners |")
        lines.append("|------|-----|-------------|------|-----------|-----------------|")
        for t in alliance.teams:
            anom = "; ".join(t.anomaly_flags[:2]) if t.anomaly_flags else "—"
            syn = ", ".join(str(p) for p in t.synergy_partners) if t.synergy_partners else "—"
            lines.append(
                f"| **{t.team_number}** | {t.epa} | {t.attributed_credit:.1%} "
                f"| {t.role_label} | {anom[:60]} | {syn} |"
            )
        lines.append("")

    # Key matchups
    lines.append("## Key Matchups")
    for i, m in enumerate(brief.key_matchups, 1):
        lines.append(f"{i}. {m.description}")
    if not brief.key_matchups:
        lines.append("_No matchup data available._")
    lines.append("")

    # Recommendations
    lines.append("## Coaching Recommendations")
    for bullet in brief.recommendations:
        lines.append(f"- {bullet}")
    if not brief.recommendations:
        lines.append("_No recommendations generated._")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"_Data sources: {', '.join(brief.data_sources_used) or 'none'}_")
    if brief.fallback_epa_only:
        lines.append("_⚠ EPA-only fallback path — live scout data unavailable._")
    lines.append("")

    return "\n".join(lines)


def render_pdf(brief: MatchBrief, output_path: Path) -> None:
    """
    Render a MatchBrief to a PDF file.

    Tries reportlab first, then weasyprint (via markdown→HTML).
    If neither is available, logs a warning and skips PDF generation.
    """
    output_path = Path(output_path)

    # Try reportlab
    try:
        from reportlab.lib.pagesizes import letter  # noqa: F401
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        md_text = render_markdown(brief)
        for line in md_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                story.append(Paragraph(stripped[2:], styles["Title"]))
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:], styles["Heading2"]))
            elif stripped.startswith("- "):
                story.append(Paragraph(stripped[2:], styles["BodyText"]))
            elif stripped and not stripped.startswith("|") and not stripped.startswith("---"):
                story.append(Paragraph(stripped, styles["BodyText"]))
            story.append(Spacer(1, 0.05 * inch))

        doc.build(story)
        log.info("PDF written via reportlab: %s", output_path)
        return
    except ImportError:
        pass

    # Try weasyprint
    try:
        import weasyprint  # type: ignore

        md_text = render_markdown(brief)
        # Minimal HTML wrapper
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{font-family:sans-serif;max-width:900px;margin:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:4px}}</style>
</head><body><pre>{md_text}</pre></body></html>"""
        weasyprint.HTML(string=html).write_pdf(str(output_path))
        log.info("PDF written via weasyprint: %s", output_path)
        return
    except ImportError:
        pass

    warnings.warn(
        "Neither reportlab nor weasyprint is installed — PDF generation skipped. "
        "Install one with: pip install reportlab  OR  pip install weasyprint",
        RuntimeWarning,
        stacklevel=2,
    )
    log.warning("PDF generation skipped: no PDF backend available")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a pre-match brief for drive-team coaching.",
        prog="python -m scout.match_brief",
    )
    parser.add_argument("--event", required=True, help="TBA event key (e.g. 2025wor)")
    parser.add_argument("--match", required=True, help="Match key (e.g. qm1)")
    parser.add_argument("--team", required=True, type=int, help="Our team number")
    parser.add_argument("--year", type=int, default=None, help="Season year (default: inferred from event key)")
    parser.add_argument("--output", default=None, help="Output markdown file path")
    parser.add_argument("--pdf", default=None, help="Output PDF file path")
    parser.add_argument(
        "--red", nargs="+", type=int, metavar="TEAM",
        help="Red alliance team numbers (manual override)",
    )
    parser.add_argument(
        "--blue", nargs="+", type=int, metavar="TEAM",
        help="Blue alliance team numbers (manual override)",
    )

    args = parser.parse_args()

    # Infer year from event key if not provided
    year = args.year
    if year is None:
        try:
            year = int(args.event[:4])
        except (ValueError, IndexError):
            year = 2025

    try:
        brief = generate_match_brief(
            event_key=args.event,
            match_key=args.match,
            year=year,
            our_team_number=args.team,
            red_teams=args.red,
            blue_teams=args.blue,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        print("Hint: use --red and --blue to specify teams manually.")
        raise SystemExit(1)

    md = render_markdown(brief)
    print(md)

    if args.output:
        Path(args.output).write_text(md)
        print(f"Markdown written to {args.output}")

    if args.pdf:
        render_pdf(brief, Path(args.pdf))


if __name__ == "__main__":
    _cli()
