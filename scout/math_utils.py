"""scout/math_utils.py — shared mathematical utilities for The Engine.

Single source of truth for numerical helpers used across scout/ and blueprint/.
"""

from __future__ import annotations

import math


def normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erfc — no scipy required.

    P(Z <= z) = 0.5 * erfc(-z / sqrt(2))

    Parameters
    ----------
    z : float
        Standard-normal variate.

    Returns
    -------
    float
        Probability in [0, 1].
    """
    return 0.5 * math.erfc(-z / math.sqrt(2.0))
