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
from scipy.stats import pearsonr


def kobayashi(
    a: np.ndarray | Sequence,
    b: np.ndarray | Sequence,
) -> list[float]:
    """Return [SB, SDSD, LCS] for the two series, which sum to the MSD."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    result = []
    result.append((a.mean() - b.mean()) ** 2)
    result.append((a.std() - b.std()) ** 2)
    result.append(2.0 * (1 - pearsonr(a, b).statistic) * a.std() * b.std())
    return result
