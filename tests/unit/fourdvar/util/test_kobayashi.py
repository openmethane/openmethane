import numpy as np
import pytest

from openmethane.fourdvar.util.kobayashi import kobayashi


def test_components_sum_to_msd():
    rng = np.random.default_rng(0)
    a = rng.normal(1850, 20, 500)
    b = 0.8 * a + rng.normal(360, 10, 500)

    sb, sdsd, lcs = kobayashi(a, b)

    assert sb + sdsd + lcs == pytest.approx(np.mean((a - b) ** 2))
    assert sb == pytest.approx((a.mean() - b.mean()) ** 2)
    assert min(sb, sdsd, lcs) >= 0


def test_offset_is_pure_bias():
    a = np.array([1.0, 2.0, 4.0, 8.0])

    sb, sdsd, lcs = kobayashi(a, a + 3)

    assert sb == pytest.approx(9)
    assert sdsd == pytest.approx(0)
    assert lcs == pytest.approx(0)


def test_accepts_sequences():
    assert kobayashi([1.0, 2.0, 3.0], [2.0, 3.0, 4.0]) == pytest.approx([1, 0, 0])


def test_weighted_components_sum_to_chisq():
    rng = np.random.default_rng(2)
    observed = rng.normal(1850, 20, 300)
    simulated = observed + rng.normal(5, 15, 300)
    uncertainty = rng.uniform(5, 20, 300)

    chisq = (((observed - simulated) / uncertainty) ** 2).sum() / observed.size
    terms = kobayashi(observed / uncertainty, simulated / uncertainty)

    assert sum(terms) == pytest.approx(chisq)
