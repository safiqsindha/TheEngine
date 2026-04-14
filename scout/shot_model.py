"""
1678-style regression shooter model (reference implementation).

Given distance-to-target, fits 2nd-order polynomial regressions for
hood angle and flywheel RPM.  Intended for shot-probability modeling
in future FRC ball games (Crescendo 2024, any 2026+ shooter game).

Not used for 2025 Reefscape (no shooter mechanism).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class ShotSample:
    """Single shooter data point collected during testing or a match."""

    distance_m: float
    hood_angle_deg: float
    flywheel_rpm: float
    made: bool


class ShotModel:
    """
    Polynomial regression shooter model.

    Fits separate 2nd-order polynomials:
        hood_angle(distance)  = a2*d^2 + a1*d + a0
        flywheel_rpm(distance) = b2*d^2 + b1*d + b0
    """

    _POLY_DEGREE = 2
    _MIN_SAMPLES = 3  # minimum needed for a 2nd-order fit

    def __init__(self) -> None:
        self._hood_coeffs: Optional[np.ndarray] = None
        self._rpm_coeffs: Optional[np.ndarray] = None

    def fit(self, samples: List[ShotSample]) -> None:
        """Fit hood-angle and flywheel-RPM polynomials from sample data."""
        if not samples:
            raise ValueError("fit() requires at least one sample; got empty list")
        if len(samples) < self._MIN_SAMPLES:
            raise ValueError(
                f"fit() requires at least {self._MIN_SAMPLES} samples for a "
                f"degree-{self._POLY_DEGREE} polynomial fit; got {len(samples)}"
            )

        distances = np.array([s.distance_m for s in samples], dtype=float)
        hoods = np.array([s.hood_angle_deg for s in samples], dtype=float)
        rpms = np.array([s.flywheel_rpm for s in samples], dtype=float)

        self._hood_coeffs = np.polyfit(distances, hoods, self._POLY_DEGREE)
        self._rpm_coeffs = np.polyfit(distances, rpms, self._POLY_DEGREE)

    def _require_fit(self) -> None:
        if self._hood_coeffs is None or self._rpm_coeffs is None:
            raise RuntimeError("Model has not been fitted yet; call fit() first")

    def predict_hood_angle(self, distance_m: float) -> float:
        """Return predicted hood angle (degrees) for a given distance."""
        self._require_fit()
        return float(np.polyval(self._hood_coeffs, distance_m))

    def predict_flywheel_rpm(self, distance_m: float) -> float:
        """Return predicted flywheel RPM for a given distance."""
        self._require_fit()
        return float(np.polyval(self._rpm_coeffs, distance_m))

    def shot_probability(
        self,
        distance_m: float,
        samples: List[ShotSample],
        bandwidth_m: float = 0.3,
    ) -> float:
        """
        Local make-rate within `bandwidth_m` metres of `distance_m`.

        Returns 0.5 (uninformative prior) when no samples fall in window.
        """
        window = [
            s for s in samples if abs(s.distance_m - distance_m) <= bandwidth_m
        ]
        if not window:
            return 0.5
        return sum(1 for s in window if s.made) / len(window)


def from_csv(path: str) -> List[ShotSample]:
    """
    Load shot samples from a CSV file.

    Expected columns (with header row):
        distance,hood,rpm,made

    `made` is truthy when the cell is '1', 'true', or 'yes' (case-insensitive).
    """
    samples: List[ShotSample] = []
    truthy = {"1", "true", "yes"}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            samples.append(
                ShotSample(
                    distance_m=float(row["distance"]),
                    hood_angle_deg=float(row["hood"]),
                    flywheel_rpm=float(row["rpm"]),
                    made=row["made"].strip().lower() in truthy,
                )
            )
    return samples
