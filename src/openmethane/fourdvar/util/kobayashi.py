"""Decompose the mismatch between two sets of values.

Kobayashi & Salam (2000) split the mean squared deviation (MSD) between two
series into three non-negative parts which sum to the MSD:

- SB, squared bias: how far apart the means are
- SDSD, squared difference of standard deviations: whether one series varies
  more than the other
- LCS, lack of correlation weighted by the standard deviations: whether the
  series fail to vary together

Kobayashi, K., & Salam, M. U. (2000). Comparing simulated and measured values
using mean squared deviation and its components. Agronomy Journal, 92(2),
345-352.
"""

from collections.abc import Sequence

import numpy as np


def kobayashi(
    a: np.ndarray | Sequence,
    b: np.ndarray | Sequence,
) -> list[float]:
    """Return [SB, SDSD, LCS] for the two series, which sum to the MSD."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    sd_a = a.std()
    sd_b = b.std()
    # 2 * (1 - r) * sd_a * sd_b, written with the covariance so a constant
    # series or a single value gives LCS = 0 rather than an error or NaN
    cov = ((a - a.mean()) * (b - b.mean())).mean()
    return [
        (a.mean() - b.mean()) ** 2,
        (sd_a - sd_b) ** 2,
        2.0 * (sd_a * sd_b - cov),
    ]
