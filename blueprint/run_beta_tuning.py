"""
blueprint/run_beta_tuning.py
------------------------------
Driver script: pulls Statbotics data for 2013-2025 and tunes β per season.

Usage:
    python -m blueprint.run_beta_tuning

Writes empirical_beta + empirical_ci + tuned_on_match_count back into
blueprint/attribution_betas.py (editing the dict in place) and updates
the results table in design-intelligence/ATTRIBUTION_BETA_TUNING.md.

Season coverage:
  2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025
  (2021 skipped — COVID year, no in-person competition; folded into 2020 note)

If a year fails entirely:
  empirical_beta = None, status = "FAILED: <reason>" (continues to next year).
"""

from __future__ import annotations

import ast
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Allow running as `python -m blueprint.run_beta_tuning` from repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from blueprint.statbotics_client import (
    fetch_season_matches,
    fetch_team_epas,
    cache_size_bytes,
    api_call_count,
)
from blueprint.tune_attribution_beta import (
    build_match_records,
    tune_beta_for_season,
    TuningResult,
)
from blueprint.attribution_betas import ATTRIBUTION_BETAS

# ---------------------------------------------------------------------------
# Season list
# ---------------------------------------------------------------------------
SEASONS = [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025]

# Beta tuning parameters
BETA_RANGE = (0.4, 1.0, 0.05)
N_BOOTSTRAP = 100

# Validation: 2025 expected near β=0.70 ± 0.10
VALIDATION_YEAR = 2025
VALIDATION_EXPECTED = 0.70
VALIDATION_TOLERANCE = 0.15  # flag if outside ±0.15


# ---------------------------------------------------------------------------
# Data pull
# ---------------------------------------------------------------------------

def pull_year(year: int) -> tuple[list[dict], dict[int, float], str]:
    """
    Fetch matches + team EPAs for one year.

    Returns (match_records, epa_map, error_message).
    error_message is "" on success, otherwise a human-readable reason.
    """
    try:
        raw_matches = fetch_season_matches(year)
    except Exception as e:
        return [], {}, f"matches fetch failed: {e}"

    if not raw_matches:
        return [], {}, "no matches returned"

    try:
        epa_map = fetch_team_epas(year)
    except Exception as e:
        return [], {}, f"team EPA fetch failed: {e}"

    if not epa_map:
        return [], {}, "no team EPA data returned"

    match_records = build_match_records(raw_matches, epa_map, comp_level="qm")

    if not match_records:
        return [], epa_map, "no qual match records after filtering"

    return match_records, epa_map, ""


# ---------------------------------------------------------------------------
# Results back-write to attribution_betas.py
# ---------------------------------------------------------------------------

def _update_attribution_betas_file(
    results: dict[int, TuningResult],
    path: Path,
) -> None:
    """
    Edit attribution_betas.py in-place to populate empirical_beta,
    empirical_ci, and tuned_on_match_count for each year.

    Uses targeted string replacement to avoid breaking the rest of the file.
    """
    content = path.read_text()

    for year, result in results.items():
        if result.status != "OK" or result.best_beta is None:
            # Mark as FAILED but don't overwrite a prior good value
            continue

        emp_beta = result.best_beta
        emp_ci = (result.ci_low, result.ci_high)
        n = result.n_matches

        # Replace: empirical_beta": None, ... # TODO lines
        # We do targeted replacements per-year block.
        # Strategy: find the year block then replace the three fields.

        # Replace empirical_beta: None → actual value
        old_emp = f'"empirical_beta": None,   # TODO(Item 1 data run): fill after Statbotics pull'
        new_emp = f'"empirical_beta": {emp_beta},'
        if old_emp in content:
            # Only replace ONCE per year — find year context
            content = _replace_in_year_block(content, year, old_emp, new_emp)

        # Also handle the shorter TODO variant
        old_emp2 = f'"empirical_beta": None,   # TODO(Item 1 data run)'
        new_emp2 = f'"empirical_beta": {emp_beta},'
        content = _replace_in_year_block(content, year, old_emp2, new_emp2)

        # Replace empirical_ci: None
        old_ci = '"empirical_ci": None,     # TODO(Item 1 data run): bootstrap CI (low, high)'
        new_ci = f'"empirical_ci": {emp_ci},'
        content = _replace_in_year_block(content, year, old_ci, new_ci)

        old_ci2 = '"empirical_ci": None,     # TODO(Item 1 data run)'
        new_ci2 = f'"empirical_ci": {emp_ci},'
        content = _replace_in_year_block(content, year, old_ci2, new_ci2)

        # Replace tuned_on_match_count: 0
        old_cnt = '"tuned_on_match_count": 0,'
        new_cnt = f'"tuned_on_match_count": {n},'
        content = _replace_in_year_block(content, year, old_cnt, new_cnt)

    path.write_text(content)


def _replace_in_year_block(
    content: str,
    year: int,
    old_str: str,
    new_str: str,
) -> str:
    """
    Replace the FIRST occurrence of old_str that appears AFTER the year's
    section header in the attribution_betas.py dict.

    This prevents accidentally replacing the same field for a different year.
    """
    # Find the year block start
    year_marker = f"    {year}: {{"
    year_pos = content.find(year_marker)
    if year_pos == -1:
        return content

    # Find the next year block start (or end of dict) so we scope the replace
    next_year_pos = len(content)
    for candidate_year in [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025]:
        if candidate_year == year:
            continue
        m = content.find(f"    {candidate_year}: {{", year_pos + 1)
        if m != -1 and m < next_year_pos:
            next_year_pos = m

    # Only replace within this year's block
    block = content[year_pos:next_year_pos]
    if old_str in block:
        block = block.replace(old_str, new_str, 1)
        content = content[:year_pos] + block + content[next_year_pos:]

    return content


# ---------------------------------------------------------------------------
# Update methodology doc results table
# ---------------------------------------------------------------------------

def _update_methodology_doc(
    results: dict[int, TuningResult],
    path: Path,
) -> None:
    """
    Rewrite the Results Table section of ATTRIBUTION_BETA_TUNING.md.
    """
    content = path.read_text()

    # Build the new table
    game_names = {
        year: ATTRIBUTION_BETAS[year]["game_name"]
        for year in SEASONS
        if year in ATTRIBUTION_BETAS
    }
    prior_betas = {
        year: ATTRIBUTION_BETAS[year]["prior_expected_beta"]
        for year in SEASONS
        if year in ATTRIBUTION_BETAS
    }

    rows = []
    rows.append("| Year    | Game              | prior_β (documented) | empirical_β* | CI (90% bootstrap) | n_matches | status |")
    rows.append("|---------|-------------------|----------------------|--------------|--------------------|-----------|--------|")

    display_years = SEASONS[:]
    for year in display_years:
        result = results.get(year)
        game = game_names.get(year, "Unknown")
        prior = prior_betas.get(year, "—")
        if isinstance(prior, dict):
            prior_str = " / ".join(f"{k}:{v}" for k, v in prior.items())
        else:
            prior_str = str(prior)

        if result is None:
            emp_str = "TBD"
            ci_str = "TBD"
            n_str = "TBD"
            status_str = "not run"
        elif result.status != "OK":
            emp_str = "—"
            ci_str = "—"
            n_str = str(result.n_matches)
            status_str = result.status
        else:
            emp_str = str(result.best_beta)
            if result.ci_low is not None and result.ci_high is not None:
                ci_str = f"({result.ci_low}, {result.ci_high})"
            else:
                ci_str = "—"
            n_str = str(result.n_matches)
            status_str = "OK"

        rows.append(f"| {year:<7} | {game:<17} | {prior_str:<20} | {emp_str:<12} | {ci_str:<18} | {n_str:<9} | {status_str} |")

    new_table = "\n".join(rows)

    # Replace the existing table
    table_start_pattern = r"\| Year\s+\| Game.*\n\|[-| ]+\|.*"
    # Find the table section and replace it
    table_header = "| Year    | Game              | prior_β (documented) |"
    start = content.find(table_header)
    if start == -1:
        # Append table if not found
        content += "\n\n## Results Table (Empirical)\n\n" + new_table + "\n"
    else:
        # Find end of table (next blank line after the table)
        end = start
        lines = content[start:].split("\n")
        table_line_count = 0
        for i, line in enumerate(lines):
            if i == 0:
                table_line_count += 1
                continue
            if line.startswith("|"):
                table_line_count += 1
            else:
                break
        end = start + len("\n".join(lines[:table_line_count]))
        content = content[:start] + new_table + content[end:]

    path.write_text(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Attribution β Tuning — FRC 2013–2025")
    print("=" * 70)
    wall_start = time.time()

    results: dict[int, TuningResult] = {}

    for year in SEASONS:
        print(f"\n[{year}] Fetching data...")
        try:
            match_records, _, error = pull_year(year)
        except Exception as e:
            error = str(e)
            match_records = []

        if error or not match_records:
            reason = error or "empty match list"
            print(f"[{year}] FAILED: {reason}")
            results[year] = TuningResult(
                best_beta=1.0,
                score_by_beta={},
                ci_low=None,
                ci_high=None,
                n_matches=0,
                status=f"FAILED: {reason}",
            )
            continue

        print(f"[{year}] {len(match_records)} alliance-match records. Tuning β...")
        result = tune_beta_for_season(
            year,
            match_records,
            beta_range=BETA_RANGE,
            n_bootstrap=N_BOOTSTRAP,
        )
        results[year] = result
        ci_str = (
            f"CI=({result.ci_low}, {result.ci_high})"
            if result.ci_low is not None
            else "CI=n/a"
        )
        print(
            f"[{year}] β*={result.best_beta:.2f}  {ci_str}  "
            f"n={result.n_matches}  status={result.status}"
        )

    wall_elapsed = time.time() - wall_start

    # ---------------------------------------------------------------------------
    # Validation: 2025 Reefscape sanity check
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Validation")
    print("=" * 70)
    r2025 = results.get(2025)
    if r2025 and r2025.status == "OK":
        delta = abs(r2025.best_beta - VALIDATION_EXPECTED)
        if delta > VALIDATION_TOLERANCE:
            print(
                f"WARNING: 2025 β*={r2025.best_beta:.2f} is far from "
                f"expected ~{VALIDATION_EXPECTED} (delta={delta:.2f} > tolerance={VALIDATION_TOLERANCE}). "
                "Objective may be wrong — review before shipping."
            )
            # Don't sys.exit — still write results but flag clearly
        else:
            print(
                f"OK: 2025 β*={r2025.best_beta:.2f} (expected ~{VALIDATION_EXPECTED}, "
                f"delta={delta:.2f} within tolerance)"
            )
    else:
        status = r2025.status if r2025 else "not run"
        print(f"WARN: 2025 result unavailable — {status}")

    # Sanity: at least 3 seasons should have β != 1.0
    non_linear = [
        y for y, r in results.items()
        if r.status == "OK" and r.best_beta < 0.99
    ]
    if len(non_linear) < 3:
        print(
            f"WARNING: only {len(non_linear)} seasons have β != 1.0 — "
            "objective may be misconfigured."
        )
    else:
        print(f"OK: {len(non_linear)} seasons have β < 1.0: {non_linear}")

    # ---------------------------------------------------------------------------
    # Write back results
    # ---------------------------------------------------------------------------
    betas_path = Path(__file__).parent / "attribution_betas.py"
    doc_path = Path(__file__).parent.parent / "design-intelligence" / "ATTRIBUTION_BETA_TUNING.md"

    print(f"\nWriting results to {betas_path.name}...")
    _update_attribution_betas_file(results, betas_path)

    print(f"Updating {doc_path.name}...")
    _update_methodology_doc(results, doc_path)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    cache_mb = cache_size_bytes() / (1024 * 1024)
    n_cache_files = api_call_count()

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Wall time: {wall_elapsed:.1f}s")
    print(f"Cache files: {n_cache_files} (~= API calls)")
    print(f"Cache size: {cache_mb:.1f} MB")
    print()
    print(f"{'Year':<6} {'Game':<20} {'β*':<6} {'CI':<20} {'n':<8} {'status'}")
    print("-" * 72)
    for year in SEASONS:
        r = results.get(year)
        game = ATTRIBUTION_BETAS.get(year, {}).get("game_name", "?")
        if r is None:
            print(f"{year:<6} {game:<20} {'—':<6} {'—':<20} {'—':<8} not run")
        elif r.status != "OK":
            print(f"{year:<6} {game:<20} {'—':<6} {'—':<20} {r.n_matches:<8} {r.status}")
        else:
            ci = (
                f"({r.ci_low},{r.ci_high})"
                if r.ci_low is not None
                else "—"
            )
            print(f"{year:<6} {game:<20} {r.best_beta:<6.2f} {ci:<20} {r.n_matches:<8} {r.status}")


if __name__ == "__main__":
    main()
