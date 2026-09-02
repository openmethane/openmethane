"""Tests for the moist-air to dry-air conversion of CMAQ mixing ratios.

TROPOMI reports a dry-air column mixing ratio; CMAQ carries a moist-air one.
`ModelSpace.get_dry_air_factor` bridges the two, and `ObsSRON.add_visibility`
folds it into the operator weights.
"""

import numpy as np
import pytest

from openmethane.obs_preprocess.model_space import ModelSpace

# a coordinate is (date, step, layer, row, col)
COORD = (20221207, 3, 0, 4, 5)


class FakeModelSpace:
    """The parts of ModelSpace that get_dry_air_factor touches."""

    def __init__(self, qv):
        self.qv_arr = np.asarray(qv)
        self.qv_date = COORD[0]
        self.nlay = self.qv_arr.shape[1]
        self.logger = None

    get_dry_air_factor = ModelSpace.get_dry_air_factor


def make_space(profile):
    """A model space whose QV profile at COORD is `profile`."""
    qv = np.zeros((25, len(profile), 10, 10))
    qv[COORD[1], :, COORD[3], COORD[4]] = profile
    return FakeModelSpace(qv)


def test_dry_air_factor_is_one_plus_qv():
    profile = [0.012, 0.008, 0.004, 0.0]
    factor = make_space(profile).get_dry_air_factor(COORD)

    assert factor == pytest.approx([1.012, 1.008, 1.004, 1.0])


def test_dry_air_factor_is_one_in_dry_air():
    """No water vapour means the two definitions coincide."""
    factor = make_space([0.0] * 32).get_dry_air_factor(COORD)

    assert factor == pytest.approx(np.ones(32))


def test_dry_air_factor_never_shrinks_the_mixing_ratio():
    """A dry-air mole fraction is always at least the moist-air one."""
    rng = np.random.default_rng(20221207)
    factor = make_space(rng.uniform(0.0, 0.03, 32)).get_dry_air_factor(COORD)

    assert np.all(factor >= 1.0)


def test_dry_air_factor_reads_the_requested_cell():
    """The factor must come from the sounding's own column and time step."""
    qv = np.zeros((25, 4, 10, 10))
    qv[COORD[1], :, COORD[3], COORD[4]] = 0.01
    qv[COORD[1] + 1, :, COORD[3], COORD[4]] = 0.02
    qv[COORD[1], :, COORD[3] + 1, COORD[4]] = 0.03
    space = FakeModelSpace(qv)

    assert space.get_dry_air_factor(COORD) == pytest.approx(np.full(4, 1.01))


def test_dry_air_factor_magnitude_is_physically_plausible():
    """A saturated boundary layer is a ~2% correction, not a ~20% one.

    This pins the direction and the order of magnitude of the definition, which
    is the part of the conversion that is easy to get wrong: a mole-fraction
    reading of QV would give ~1.6x this, and inverting it would give <1.
    """
    # ~30 g/kg is about as moist as the lowest model layer ever gets
    factor = make_space([0.030]).get_dry_air_factor(COORD)[0]

    assert 1.02 < factor < 1.05
    # on a 1850 ppb layer, a few tens of ppb
    assert 30.0 < 1850.0 * (factor - 1.0) < 70.0
