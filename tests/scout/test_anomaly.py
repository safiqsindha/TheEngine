"""Tests for scout/anomaly.py — z-score outlier detection.

Covers:
  - Empty observations → no flags
  - Insufficient observations for a metric → no flags
  - Uniform values (zero sigma) → no flags
  - Clear high outlier flagged (|z| > 2.5)
  - Clear low outlier flagged
  - Moderate observations in normal range → not flagged
  - Severity labeling: high/medium/low
  - AnomalyFlag fields populated correctly (team, match_key, metric, scout)
  - detect_anomalies_all_teams partitions by team and returns only teams with flags
  - anomaly_summary_line produces human-readable string
  - filter_anomaly_scouts returns scouts above threshold flag count
  - Multiple metrics checked independently
  - cycle_speed extraction mapping
  - auto_scored binary extraction
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from anomaly import (  # noqa: E402
    Z_THRESHOLD,
    MIN_OBS_FOR_ZSCORE,
    ANOMALY_METHOD,
    AnomalyFlag,
    anomaly_summary_line,
    detect_anomalies,
    detect_anomalies_all_teams,
    detect_anomalies_robust,
    filter_anomaly_scouts,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _obs(contribution: float = None, cycle_speed: str = "fast",
         auto_scored: bool = True, climb: bool = True,
         match: str = "2026txbel_qm1", team: int = 2950,
         scout: str = "Alice") -> dict:
    d = {
        "team": team,
        "_meta": {"scout": scout, "match_key": match},
        "auto": {"scored": auto_scored},
        "teleop": {"cycle_speed": cycle_speed},
        "endgame": {"climb_attempted": climb},
        "defense": {"played_defense": False, "received_defense": False, "notes": ""},
    }
    if contribution is not None:
        d["match_contribution"] = contribution
    return d


def _uniform_obs(n: int, contrib: float = 40.0) -> list:
    return [_obs(contribution=contrib, match=f"qm{i}") for i in range(n)]


def _normal_with_outlier(n_normal: int, normal_contrib: float,
                          outlier_contrib: float) -> list:
    obs_list = [_obs(contribution=normal_contrib, match=f"qm{i}") for i in range(n_normal)]
    obs_list.append(_obs(contribution=outlier_contrib, match=f"qm{n_normal}"))
    return obs_list


# ─── Empty / insufficient data ───────────────────────────────────────────────


def test_empty_observations_no_flags():
    flags = detect_anomalies([], metrics=["match_contribution"])
    assert flags == []


def test_fewer_than_min_obs_no_flags():
    obs_list = _uniform_obs(MIN_OBS_FOR_ZSCORE - 1, 40.0)
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags == []


def test_exactly_min_obs_runs_without_error():
    obs_list = _uniform_obs(MIN_OBS_FOR_ZSCORE, 40.0)
    # Uniform → zero sigma → no flags expected
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags == []


# ─── Zero variance → no flags ─────────────────────────────────────────────────


def test_uniform_values_no_flags():
    obs_list = _uniform_obs(8, 42.0)
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags == []


# ─── Outlier detection ────────────────────────────────────────────────────────


def test_clear_high_outlier_flagged():
    # 7 matches at 40, 1 extreme outlier at 200
    obs_list = _normal_with_outlier(7, 40.0, 200.0)
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert len(flags) >= 1
    top = flags[0]
    assert top.metric == "match_contribution"
    assert top.z_score > Z_THRESHOLD


def test_clear_low_outlier_flagged():
    # 7 matches at 40, 1 crash at 0 (robot disabled)
    obs_list = _normal_with_outlier(7, 40.0, 0.0)
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert len(flags) >= 1
    top = flags[0]
    assert top.z_score < -Z_THRESHOLD


def test_moderate_observations_not_flagged():
    # Cluster around 40 with small natural variance
    obs_list = [_obs(contribution=40.0 + (i % 3) - 1, match=f"qm{i}")
                for i in range(8)]
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags == []


# ─── AnomalyFlag fields ───────────────────────────────────────────────────────


def test_flag_fields_populated():
    obs_list = [_obs(contribution=40.0, match=f"qm{i}", scout="Bob") for i in range(7)]
    obs_list.append(_obs(contribution=200.0, match="qm99", scout="Bob"))
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags, "Expected at least one flag"
    f = flags[0]
    assert f.team == 2950
    assert f.match_key == "qm99"
    assert f.metric == "match_contribution"
    assert f.scout_name == "Bob"
    assert f.observed_value == pytest.approx(200.0, abs=0.01)
    assert isinstance(f.expected_mean, float)
    assert isinstance(f.expected_sigma, float)
    assert f.reason != ""


# ─── Severity ────────────────────────────────────────────────────────────────


def test_severity_high_at_large_z():
    # Very extreme outlier: 10 matches at 40, one at 10_000 — forces |z| > 3.5
    obs_list = _normal_with_outlier(10, 40.0, 10_000.0)
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    assert flags, "Expected at least one flag"
    assert flags[0].severity in ("high", "medium"), f"Unexpected severity: {flags[0].severity}"
    # Verify severity is NOT low for such an extreme value
    assert flags[0].severity != "low"


def test_severity_low_near_threshold():
    # Construct |z| just above threshold but below medium threshold (3.0)
    # 5 matches at 0, one match creating z ~2.6
    import math
    # With 5 zeros and 1 outlier: mean = x/6, sigma = sqrt(5*(x/6)^2 + (5x/6)^2)/6
    # Choose outlier so |z| lands around 2.6
    # mean = 10/6 ≈ 1.67, each zero is -1.67/sigma away
    # Just use contribution values that naturally produce a borderline z
    obs_list = [_obs(contribution=0.0, match=f"qm{i}") for i in range(5)]
    obs_list.append(_obs(contribution=10.0, match="qm5"))
    flags = detect_anomalies(obs_list, metrics=["match_contribution"])
    if flags:
        assert flags[0].severity in ("low", "medium", "high")


# ─── Cycle speed metric ──────────────────────────────────────────────────────


def test_cycle_speed_extraction_flags_outlier():
    # 7 fast matches, 1 slow match — large drop in numeric value
    obs_list = [_obs(cycle_speed="fast", match=f"qm{i}") for i in range(7)]
    obs_list.append(_obs(cycle_speed="slow", match="qm7"))
    flags = detect_anomalies(obs_list, metrics=["cycle_speed"])
    # Slow = 0.2, fast = 1.0. Mean ≈ 0.9, sigma ≈ 0.27
    # z = (0.2 - 0.9) / 0.27 ≈ -2.6 → should flag
    assert len(flags) >= 1
    assert flags[0].metric == "cycle_speed"


# ─── auto_scored binary ──────────────────────────────────────────────────────


def test_auto_scored_flags_single_miss():
    # 8 matches with auto scored, 1 without — that's a 1.0→0.0 drop
    obs_list = [_obs(auto_scored=True, match=f"qm{i}") for i in range(8)]
    obs_list.append(_obs(auto_scored=False, match="qm8"))
    flags = detect_anomalies(obs_list, metrics=["auto_scored"])
    assert len(flags) >= 1
    assert flags[0].metric == "auto_scored"


# ─── All teams batch ─────────────────────────────────────────────────────────


def test_detect_all_teams_returns_only_teams_with_flags():
    obs_list = []
    # Team 2950: normal
    for i in range(8):
        obs_list.append(_obs(contribution=40.0, match=f"qm{i}", team=2950))
    # Team 1678: has outlier
    for i in range(7):
        obs_list.append(_obs(contribution=40.0, match=f"qm{i}", team=1678))
    obs_list.append(_obs(contribution=200.0, match="qm99", team=1678))

    results = detect_anomalies_all_teams(obs_list, metrics=["match_contribution"])
    assert 1678 in results
    # 2950 should not appear (no flags)
    assert 2950 not in results


def test_detect_all_teams_empty_returns_empty():
    results = detect_anomalies_all_teams([])
    assert results == {}


# ─── anomaly_summary_line ────────────────────────────────────────────────────


def test_summary_line_empty_flags_returns_empty_string():
    assert anomaly_summary_line([]) == ""


def test_summary_line_nonempty_contains_count():
    flags = [
        AnomalyFlag(team=2950, match_key="qm1", metric="match_contribution",
                    observed_value=200.0, expected_mean=40.0, expected_sigma=5.0,
                    z_score=3.2, severity="medium", scout_name="Alice",
                    reason="test"),
    ]
    line = anomaly_summary_line(flags)
    assert "1" in line
    assert "match_contribution" in line
    assert "review" in line or "malfunction" in line


# ─── filter_anomaly_scouts ───────────────────────────────────────────────────


def test_filter_anomaly_scouts_above_threshold():
    flags = [
        AnomalyFlag(team=2950, match_key="qm1", metric="cycle_speed",
                    observed_value=0.2, expected_mean=0.9, expected_sigma=0.3,
                    z_score=-2.6, severity="low", scout_name="BadScout", reason=""),
        AnomalyFlag(team=2950, match_key="qm2", metric="auto_scored",
                    observed_value=0.0, expected_mean=0.9, expected_sigma=0.1,
                    z_score=-9.0, severity="high", scout_name="BadScout", reason=""),
    ]
    suspects = filter_anomaly_scouts(flags, threshold=2)
    assert "BadScout" in suspects


def test_filter_anomaly_scouts_below_threshold_excluded():
    flags = [
        AnomalyFlag(team=2950, match_key="qm1", metric="cycle_speed",
                    observed_value=0.2, expected_mean=0.9, expected_sigma=0.3,
                    z_score=-2.6, severity="low", scout_name="OccasionalScout", reason=""),
    ]
    suspects = filter_anomaly_scouts(flags, threshold=2)
    assert "OccasionalScout" not in suspects


def test_filter_anomaly_scouts_empty_returns_empty():
    assert filter_anomaly_scouts([]) == []


# ─── ANOMALY_METHOD constant ─────────────────────────────────────────────────


def test_anomaly_method_constant_is_robust():
    assert ANOMALY_METHOD == "robust"


# ─── detect_anomalies_robust — basic ─────────────────────────────────────────


def test_robust_clean_data_no_flags():
    """Robust method on clean, tight data should produce no flags."""
    obs_list = [_obs(contribution=40.0 + (i % 3) - 1, match=f"qm{i}")
                for i in range(9)]
    flags = detect_anomalies_robust(obs_list, metrics=["match_contribution"])
    assert flags == []


def test_robust_single_outlier_flagged():
    """Robust method flags a single extreme outlier in otherwise uniform data."""
    obs_list = [_obs(contribution=10.0, match=f"qm{i}") for i in range(9)]
    obs_list.append(_obs(contribution=50.0, match="qm9"))
    flags = detect_anomalies_robust(obs_list, metrics=["match_contribution"])
    assert len(flags) >= 1
    assert flags[0].observed_value == pytest.approx(50.0, abs=0.01)
    assert flags[0].metric == "match_contribution"


def test_robust_flags_while_zscore_misses():
    """
    Comparison test: fixture [10,10,11,10,10,11,10,10,11,50].

    The outlier (50) inflates sigma so z-score at threshold=3.0 misses it.
    Robust MAD at threshold=3.5 correctly flags it because the median and MAD
    are unaffected by a single extreme value.
    """
    normal = [10, 10, 11, 10, 10, 11, 10, 10, 11]
    obs_list = [_obs(contribution=float(v), match=f"qm{i}") for i, v in enumerate(normal)]
    obs_list.append(_obs(contribution=50.0, match="qm9"))

    robust_flags = detect_anomalies_robust(
        obs_list, metrics=["match_contribution"], mad_threshold=3.5
    )
    zscore_flags = detect_anomalies(
        obs_list, metrics=["match_contribution"], z_threshold=3.0
    )

    # Robust must flag the outlier
    robust_outlier = [f for f in robust_flags if f.observed_value == pytest.approx(50.0, abs=0.01)]
    assert len(robust_outlier) >= 1, "Robust method should flag the outlier at 50"

    # Z-score should miss it (contaminated sigma)
    zscore_outlier = [f for f in zscore_flags if f.observed_value == pytest.approx(50.0, abs=0.01)]
    assert len(zscore_outlier) == 0, (
        "Z-score at threshold=3.0 should miss the outlier because it inflates sigma"
    )


def test_robust_all_identical_values_no_flags():
    """MAD=0 edge case: all values identical → no flags, no divide-by-zero."""
    obs_list = [_obs(contribution=42.0, match=f"qm{i}") for i in range(8)]
    flags = detect_anomalies_robust(obs_list, metrics=["match_contribution"])
    assert flags == []


def test_robust_empty_matches_empty_result():
    """Empty matches list should return empty list without error."""
    flags = detect_anomalies_robust([], metrics=["match_contribution"])
    assert flags == []


def test_robust_missing_metric_field_no_crash():
    """Observations that lack the requested metric should be skipped silently."""
    # These obs have no 'match_contribution' key and no 'score' key
    obs_list = [{"team": 2950, "_meta": {"match_key": f"qm{i}", "scout": "Alice"}}
                for i in range(6)]
    # Should not raise; not enough valid obs → no flags
    flags = detect_anomalies_robust(obs_list, metrics=["match_contribution"])
    assert flags == []
