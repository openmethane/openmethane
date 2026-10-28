import numpy as np
import pytest

from openmethane.fourdvar.datadef import PhysicalAdjointData, UnknownData
from openmethane.fourdvar.datadef.abstract._physical_abstract_data import PhysicalAbstractData
from openmethane.fourdvar.params import input_defn
from openmethane.fourdvar.transfunc import condition_adjoint, uncondition, uncondition_adjoint


@pytest.fixture
def physical_params(monkeypatch):
    """Small physical shapes with uncertainties which differ in every cell."""
    rng = np.random.default_rng(0)
    params = {
        "tday_emis": 86400,
        "nstep_emis": 2,
        "nlays_emis": 1,
        "nrows": 3,
        "ncols": 4,
        "spcs": ["CH4"],
        "emis_unc": {"CH4": rng.uniform(0.5, 2.0, (2, 1, 3, 4))},
        "bcon_region": 2,
        "nstep_bcon": 1,
        "bcon_region_map": np.repeat([[0], [1]], 8, axis=0) * np.ones((1, 44), dtype=int),
        "bcon_step_start": np.array([0]),
        "bcon_step_end": np.array([86400]),
        "bcon_unc": {"CH4": rng.uniform(0.5, 2.0, (1, 2))},
    }
    if input_defn.inc_icon is True:
        params["icon_unc"] = {"CH4": 1.5}
    for name, val in params.items():
        monkeypatch.setattr(PhysicalAbstractData, name, val)
    return params


def test_uncondition_adjoint_inverts_condition_adjoint(physical_params):
    n_unknowns = 2 * 1 * 3 * 4 + 1 * 2 + (1 if input_defn.inc_icon else 0)
    gradient = np.random.default_rng(1).normal(size=n_unknowns)

    physical_gradient = uncondition_adjoint(UnknownData(gradient))

    assert isinstance(physical_gradient, PhysicalAdjointData)
    np.testing.assert_allclose(condition_adjoint(physical_gradient).get_vector(), gradient)


def test_uncondition_adjoint_divides_by_uncertainty(physical_params):
    n_unknowns = 2 * 1 * 3 * 4 + 1 * 2 + (1 if input_defn.inc_icon else 0)
    ones = UnknownData(np.ones(n_unknowns))

    gradient = uncondition_adjoint(ones)
    physical = uncondition(ones)

    emis_unc = physical_params["emis_unc"]["CH4"]
    np.testing.assert_allclose(gradient.emis["CH4"], 1 / emis_unc)
    np.testing.assert_allclose(physical.emis["CH4"], emis_unc)
