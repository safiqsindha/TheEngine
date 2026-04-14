"""Tests for scout/shot_model.py — 1678-style regression shooter model."""

from __future__ import annotations

import csv
import math
import os
import tempfile

import numpy as np
import pytest

from scout.shot_model import ShotModel, ShotSample, from_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quadratic_samples(
    a2: float, a1: float, a0: float,
    b2: float, b1: float, b0: float,
    distances=None,
    made: bool = True,
):
    """Generate synthetic ShotSamples whose hood/rpm follow exact quadratics."""
    if distances is None:
        distances = [1.0, 2.0, 3.0, 4.0, 5.0]
    return [
        ShotSample(
            distance_m=d,
            hood_angle_deg=a2 * d**2 + a1 * d + a0,
            flywheel_rpm=b2 * d**2 + b1 * d + b0,
            made=made,
        )
        for d in distances
    ]


# ---------------------------------------------------------------------------
# 1. Fit on synthetic quadratic data recovers coefficients within tolerance
# ---------------------------------------------------------------------------

def test_fit_recovers_hood_coefficients():
    """Fitted hood polynomial should match generating coefficients closely."""
    a2, a1, a0 = 0.5, 2.0, 10.0
    samples = _quadratic_samples(a2, a1, a0, 0, 0, 0)
    model = ShotModel()
    model.fit(samples)
    assert model._hood_coeffs is not None
    np.testing.assert_allclose(model._hood_coeffs, [a2, a1, a0], rtol=1e-6)


def test_fit_recovers_rpm_coefficients():
    """Fitted RPM polynomial should match generating coefficients closely."""
    b2, b1, b0 = -30.0, 500.0, 2000.0
    samples = _quadratic_samples(0, 0, 0, b2, b1, b0)
    model = ShotModel()
    model.fit(samples)
    assert model._rpm_coeffs is not None
    np.testing.assert_allclose(model._rpm_coeffs, [b2, b1, b0], rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. Predictions at training points are within 5 % of training value
# ---------------------------------------------------------------------------

def test_predict_hood_angle_within_5pct():
    samples = _quadratic_samples(0.4, 1.5, 8.0, 0, 0, 0)
    model = ShotModel()
    model.fit(samples)
    for s in samples:
        pred = model.predict_hood_angle(s.distance_m)
        assert math.isclose(pred, s.hood_angle_deg, rel_tol=0.05), (
            f"pred={pred:.3f}, truth={s.hood_angle_deg:.3f}"
        )


def test_predict_flywheel_rpm_within_5pct():
    samples = _quadratic_samples(0, 0, 0, -20.0, 400.0, 1800.0)
    model = ShotModel()
    model.fit(samples)
    for s in samples:
        pred = model.predict_flywheel_rpm(s.distance_m)
        assert math.isclose(pred, s.flywheel_rpm, rel_tol=0.05), (
            f"pred={pred:.3f}, truth={s.flywheel_rpm:.3f}"
        )


# ---------------------------------------------------------------------------
# 3. shot_probability returns correct make rate for in-window samples
# ---------------------------------------------------------------------------

def test_shot_probability_all_made():
    samples = [ShotSample(2.0, 30.0, 3000.0, True) for _ in range(5)]
    model = ShotModel()
    assert model.shot_probability(2.0, samples) == 1.0


def test_shot_probability_half_made():
    samples = (
        [ShotSample(2.0, 30.0, 3000.0, True) for _ in range(3)]
        + [ShotSample(2.0, 30.0, 3000.0, False) for _ in range(3)]
    )
    model = ShotModel()
    prob = model.shot_probability(2.0, samples)
    assert math.isclose(prob, 0.5, rel_tol=1e-9)


def test_shot_probability_respects_bandwidth():
    """Samples outside the bandwidth window should not affect the result."""
    close = [ShotSample(2.0, 30.0, 3000.0, True) for _ in range(4)]
    far = [ShotSample(5.0, 45.0, 4000.0, False) for _ in range(10)]
    model = ShotModel()
    prob = model.shot_probability(2.0, close + far, bandwidth_m=0.3)
    assert prob == 1.0


# ---------------------------------------------------------------------------
# 4. Empty samples list raises ValueError on fit
# ---------------------------------------------------------------------------

def test_fit_empty_samples_raises():
    model = ShotModel()
    with pytest.raises(ValueError, match="empty list"):
        model.fit([])


# ---------------------------------------------------------------------------
# 5. Fewer than 3 samples raises ValueError
# ---------------------------------------------------------------------------

def test_fit_fewer_than_3_raises():
    two_samples = [ShotSample(1.0, 20.0, 2000.0, True),
                   ShotSample(2.0, 25.0, 2500.0, True)]
    model = ShotModel()
    with pytest.raises(ValueError, match="at least 3"):
        model.fit(two_samples)


# ---------------------------------------------------------------------------
# 6. shot_probability with no in-window samples returns 0.5
# ---------------------------------------------------------------------------

def test_shot_probability_no_window_returns_uninformative_prior():
    samples = [ShotSample(10.0, 60.0, 5000.0, True) for _ in range(5)]
    model = ShotModel()
    # Query at 2.0 m; all samples at 10.0 m — default bandwidth 0.3 m
    assert model.shot_probability(2.0, samples) == 0.5


def test_shot_probability_empty_sample_list_returns_uninformative_prior():
    model = ShotModel()
    assert model.shot_probability(3.0, []) == 0.5


# ---------------------------------------------------------------------------
# 7. Mixed made/missed fit with proper probability estimate
# ---------------------------------------------------------------------------

def test_mixed_made_missed_probability():
    made_samples = [ShotSample(3.0, 35.0, 3200.0, True) for _ in range(6)]
    missed_samples = [ShotSample(3.0, 35.0, 3200.0, False) for _ in range(4)]
    model = ShotModel()
    prob = model.shot_probability(3.0, made_samples + missed_samples)
    assert math.isclose(prob, 0.6, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 8. from_csv loader
# ---------------------------------------------------------------------------

def test_from_csv_loads_correctly():
    rows = [
        {"distance": "1.5", "hood": "22.5", "rpm": "2800", "made": "1"},
        {"distance": "2.5", "hood": "30.0", "rpm": "3100", "made": "0"},
        {"distance": "3.5", "hood": "38.5", "rpm": "3500", "made": "true"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["distance", "hood", "rpm", "made"])
        writer.writeheader()
        writer.writerows(rows)
        tmp_path = f.name

    try:
        samples = from_csv(tmp_path)
        assert len(samples) == 3
        assert samples[0].distance_m == 1.5
        assert samples[0].hood_angle_deg == 22.5
        assert samples[0].flywheel_rpm == 2800.0
        assert samples[0].made is True
        assert samples[1].made is False
        assert samples[2].made is True
    finally:
        os.unlink(tmp_path)
