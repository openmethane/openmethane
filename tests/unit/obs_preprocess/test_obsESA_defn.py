"""Tests for the observation ObsSRON builds from a single TROPOMI sounding."""

import numpy as np
import pytest

from openmethane.obs_preprocess.column_operator import (
    FILL_PRIOR,
    FILL_PRIOR_OFFSET,
    build_column_operator,
)
from openmethane.obs_preprocess.obsESA_defn import (
    DEFAULT_MODEL_UNCERTAINTY,
    PRECISION_INFLATION,
    ObsSRON,
    model_uncertainty,
    ppb_scale,
)

# A model column that stops short of the top of the retrieval column, as CMAQ
# does: VGTOP is 5000 Pa in the Australian domain, leaving roughly the top 5% of
# the air mass unmodelled. The layer counts are smaller than the real ones; the
# property under test does not depend on them.
N_SAT = 12
N_MODEL = 8
VGTOP = 5000.0
MODEL_SURFACE_PRESSURE = 101000.0
SAT_SURFACE_PRESSURE = 99752.0


def sat_edges():
    """Retrieval level pressures (Pa), ascending from the top of the atmosphere."""
    return SAT_SURFACE_PRESSURE * np.arange(N_SAT + 1) / N_SAT


def model_edges():
    """Model level pressures (Pa), descending from the surface.

    Sigma levels stretched towards the top, so that the topmost layer is thin in
    pressure and carries only a small share of the air mass - the shape that
    makes over-weighting it so costly.
    """
    sigma = np.linspace(1.0, 0.0, N_MODEL + 1) ** 3
    return sigma * (MODEL_SURFACE_PRESSURE - VGTOP) + VGTOP


def sounding():
    """The retrieval fields add_visibility reads, top of atmosphere first."""
    prior_ppb = np.linspace(600.0, 1850.0, N_SAT)
    # mol m-2; uniform, so that the ppb prior is recovered exactly
    dry_air = np.full(N_SAT, 1.0e4)
    return {
        "pressure_levels": sat_edges(),
        # neither uniform nor everywhere below one, so that a weight cannot come
        # out right by accident
        "obs_kernel": np.linspace(1.15, 0.8, N_SAT),
        "ch4_profile_apriori": dry_air * prior_ppb / ppb_scale,
        "dry_air_subcolumns": dry_air,
    }


def light_path():
    """Light-path proportions, spread over two cells in every model layer.

    Coordinates follow the (date, time, layer, row, column, species) convention
    ModelSpace uses, and the whole path sums to one.
    """
    path = {}
    for lay in range(N_MODEL):
        path[("20240615", 4, lay, 10, 20, "CH4")] = 0.75
        path[("20240615", 4, lay, 10, 21, "CH4")] = 0.25
    total = sum(path.values())
    return {coord: value / total for coord, value in path.items()}


class FakeModelSpace:
    """Just enough of ModelSpace for add_visibility: one column's layer edges."""

    def get_pressure_bounds(self, target_coord):
        return model_edges()


def observation():
    obs = ObsSRON(obstype="ESA_co_obs")
    obs.src_data = sounding()
    obs.out_dict["ch4_column_precision"] = 7.0
    return obs


def test_model_uncertainty_default(monkeypatch):
    monkeypatch.delenv("OPENMETHANE_MODEL_UNCERTAINTY", raising=False)
    assert model_uncertainty() == DEFAULT_MODEL_UNCERTAINTY == 10.0


def test_model_uncertainty_from_environment(monkeypatch):
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "17.5")
    assert model_uncertainty() == 17.5


def test_model_uncertainty_is_read_on_each_call(monkeypatch):
    """It must not be captured at import time, or a run cannot configure it."""
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "5")
    assert model_uncertainty() == 5.0
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "30")
    assert model_uncertainty() == 30.0


def test_uncertainty_combines_model_and_precision_in_quadrature():
    """The formula applied in add_visibility, stated independently."""
    model_unc = 10.0
    precision = 2.0
    expected = (model_unc**2 + (PRECISION_INFLATION * precision) ** 2) ** 0.5

    assert expected == pytest.approx(((10.0**2) + (4.0**2)) ** 0.5)
    # the model term dominates at realistic TropOMI precisions
    assert model_unc < expected < model_unc * 1.1


def test_preprocessor_puts_no_fill_weight_on_the_topmost_model_layer():
    """The fill above the model top must not be anchored to the model's top layer.

    CMAQ has no top boundary condition, so its topmost layer drifts: BCON
    prescribes CH4 only around the lateral perimeter, the domain top is a rigid
    lid, and nothing restores the gradient once vertical mixing erodes it. A fill
    anchored to that layer hands it the whole uncovered column on top of its own
    air mass, and because the operator weights are dy/dx the adjoint reads the
    drift as emissions. The preprocessor therefore asks for FILL_PRIOR, which
    leaves the fill entirely in `offset_term`.

    This guards the call site, not just the default: changing the `fill` argument
    in `ObsSRON.add_visibility` reinstates
    https://github.com/openmethane/openmethane/issues/236.
    """
    obs = observation()
    sat_edge = sat_edges()
    model_edge = model_edges()
    avker = obs.src_data["obs_kernel"]
    column_thickness = sat_edge[-1] - sat_edge[0]

    weight_grid = obs.add_visibility(light_path(), FakeModelSpace())

    # the topmost model layer lies wholly inside the topmost retrieval layer, so
    # the only weight it can earn is the kernel times its own pressure share
    assert model_edge[-2] < sat_edge[1]
    air_mass_share = avker[0] * (model_edge[-2] - model_edge[-1]) / column_thickness

    top_layer = sum(w for coord, w in weight_grid.items() if coord[2] == N_MODEL - 1)
    assert top_layer == pytest.approx(air_mass_share)

    # what an anchored fill would have added instead: the whole column above the
    # model top, which outweighs the layer itself several times over
    uncovered = avker[0] * (model_edge[-1] - sat_edge[0]) / column_thickness
    assert uncovered > air_mass_share
    anchored = build_column_operator(
        sat_edge, avker, obs.out_dict["prior_profile"], model_edge, fill=FILL_PRIOR_OFFSET
    )
    assert anchored.weights[-1] == pytest.approx(air_mass_share + uncovered)


def test_preprocessor_builds_the_prior_fill_operator():
    """Every term the preprocessor stores comes from the prior-fill operator."""
    obs = observation()
    avker = obs.src_data["obs_kernel"]

    obs.add_visibility(light_path(), FakeModelSpace())

    expected = build_column_operator(
        sat_edge=sat_edges(),
        avker=avker,
        prior=obs.out_dict["prior_profile"],
        model_edge=model_edges(),
        fill=FILL_PRIOR,
    )
    assert obs.out_dict["model_vis"] == pytest.approx(expected.weights)
    assert obs.out_dict["offset_term"] == pytest.approx(expected.offset)
    assert obs.out_dict["model_coverage"] == pytest.approx(expected.coverage)

    # the weights account for the covered column and nothing else; the fill is
    # wholly in the constant term
    assert expected.weights.sum() == pytest.approx(
        (avker * expected.coverage) @ expected.pressure_weight
    )
    assert expected.coverage[0] < 1.0


def test_weight_grid_spreads_each_layer_without_changing_its_total():
    """Spreading a layer's weight over the cells it crosses must conserve it."""
    obs = observation()

    weight_grid = obs.add_visibility(light_path(), FakeModelSpace())

    weights = obs.out_dict["model_vis"]
    for lay, weight in enumerate(weights):
        layer_total = sum(w for coord, w in weight_grid.items() if coord[2] == lay)
        assert layer_total == pytest.approx(weight)
    assert sum(weight_grid.values()) == pytest.approx(weights.sum())
