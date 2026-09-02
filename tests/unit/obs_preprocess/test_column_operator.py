"""Tests for the vertical part of the TROPOMI column operator.

The reference implementation this is checked against is
https://github.com/hannahnesser/TROPOMI_inversion/blob/main/python/TROPOMI_operator.py
"""

import numpy as np
import pytest

from openmethane.obs_preprocess.column_operator import (
    FILL_MODEL_TOP,
    FILL_PRIOR,
    FILL_PRIOR_OFFSET,
    build_column_operator,
    pressure_overlap,
)

# The Australian domain: 12 retrieval layers over ~1000 hPa, 32 CMAQ layers
# between the surface and VGTOP = 5000 Pa.
N_SAT = 12
VGTOP = 5000.0
VGLVLS = np.array(
    [
        1.0, 0.9938145, 0.9859505, 0.9760142, 0.9635575, 0.9480932, 0.9291238,
        0.9061912, 0.8789424, 0.847208, 0.8110778, 0.7709489, 0.7275254,
        0.6817555, 0.6345035, 0.5860305, 0.5366501, 0.4867301, 0.4366881,
        0.3869877, 0.3381276, 0.2906297, 0.2450226, 0.2018216, 0.1615063,
        0.1270537, 0.09814423, 0.07388596, 0.05353061, 0.03645026, 0.0221179,
        0.01009149, 0.0
    ]
)


def sat_edges(surface_pressure=99752.0, n_layer=N_SAT):
    """Retrieval level pressures, ascending from the top of the atmosphere."""
    return surface_pressure * np.arange(n_layer + 1) / n_layer


def cmaq_edges(surface_pressure=101000.0, vgtop=VGTOP, vglvls=VGLVLS):
    """CMAQ level pressures, descending from the surface."""
    return vglvls * (surface_pressure - vgtop) + vgtop


# -------------------------------------------------------------------------
# Reference implementation, transcribed from TROPOMI_operator.py.
# -------------------------------------------------------------------------
def GC_to_sat_levels(GC_CH4, GC_edges, sat_edges):
    idx_bottom = np.less(GC_edges[:, 0], sat_edges[:, 0])
    idx_top = np.greater(GC_edges[:, -1], sat_edges[:, -1])
    GC_edges[idx_bottom, 0] = sat_edges[idx_bottom, 0]
    GC_edges[idx_top, -1] = sat_edges[idx_top, -1]

    GC_lo = GC_edges[:, 1:][:, :, None]
    GC_hi = GC_edges[:, :-1][:, :, None]
    sat_lo = sat_edges[:, 1:][:, None, :]
    sat_hi = sat_edges[:, :-1][:, None, :]

    idx = np.less_equal(sat_lo, GC_hi) & np.greater_equal(sat_hi, GC_lo)

    GC_to_sat = np.minimum(sat_hi, GC_hi) - np.maximum(sat_lo, GC_lo)
    GC_to_sat[~idx] = 0

    GC_on_sat = (GC_to_sat * GC_CH4[:, :, None]).sum(axis=1)
    GC_on_sat = GC_on_sat / GC_to_sat.sum(axis=1)

    return GC_on_sat


def apply_avker(sat_avker, sat_prior, sat_pressure_weight, GC_CH4, filt=None):
    if filt is None:
        filt = np.ones(sat_avker.shape[1])
    else:
        filt = filt.astype(int)

    GC_col = filt * sat_pressure_weight * (sat_prior + sat_avker * (GC_CH4 - sat_prior))
    return GC_col.sum(axis=1)


def reference_column(avker, prior, sat_edge, model_edge, model_profile):
    """Run the reference implementation on a single sounding.

    The reference orders both grids surface first and descending in pressure,
    where we order the retrieval top first and ascending, so the retrieval
    inputs are reversed on the way in.
    """
    sat_edge_desc = sat_edge[::-1][None, :]
    model_edge_desc = model_edge[None, :].copy()
    on_sat = GC_to_sat_levels(model_profile[None, :], model_edge_desc, sat_edge_desc.copy())
    pressure_weight = (
        -np.diff(sat_edge_desc) / (sat_edge_desc[:, 0] - sat_edge_desc[:, -1])[:, None]
    )
    return apply_avker(avker[::-1][None, :], prior[::-1][None, :], pressure_weight, on_sat)[0]


# -------------------------------------------------------------------------


def test_pressure_overlap_partitions_the_shared_column():
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    overlap = pressure_overlap(sat_edge, model_edge)

    assert overlap.shape == (N_SAT, VGLVLS.size - 1)
    assert np.all(overlap >= 0.0)
    # no retrieval or model layer can be over-counted
    assert np.all(overlap.sum(axis=1) <= np.diff(sat_edge) + 1e-9)
    assert np.all(overlap.sum(axis=0) <= -np.diff(model_edge) + 1e-9)
    # the shared column is the intersection of the two: this raw call does not
    # clip or pin the model edges, so the part of the model column below the
    # retrieval surface pressure is simply not shared
    shared = min(model_edge[0], sat_edge[-1]) - max(model_edge[-1], sat_edge[0])
    assert overlap.sum() == pytest.approx(shared, rel=1e-12)


def test_full_coverage_reproduces_the_reference_implementation():
    """A model spanning the whole retrieval column must match the reference."""
    rng = np.random.default_rng(20221207)
    sat_edge = sat_edges()
    # a model grid that spans the retrieval column exactly, so that no filling
    # is needed and the two implementations are directly comparable
    model_edge = cmaq_edges(surface_pressure=sat_edge[-1], vgtop=0.0)

    for _ in range(20):
        avker = rng.uniform(0.2, 1.4, N_SAT)
        prior = rng.uniform(400.0, 1900.0, N_SAT)
        profile = rng.uniform(1500.0, 2100.0, VGLVLS.size - 1)

        operator = build_column_operator(sat_edge, avker, prior, model_edge)
        assert np.all(operator.coverage == pytest.approx(1.0))

        got = operator.weights @ profile + operator.offset
        expected = reference_column(avker, prior, sat_edge, model_edge, profile)
        assert got == pytest.approx(expected, rel=1e-10)


def test_model_top_fill_reproduces_the_reference_implementation():
    """The reference stretches the top model layer; so does FILL_MODEL_TOP."""
    rng = np.random.default_rng(20221208)
    sat_edge = sat_edges()
    model_edge = cmaq_edges()

    for _ in range(20):
        avker = rng.uniform(0.2, 1.4, N_SAT)
        prior = rng.uniform(400.0, 1900.0, N_SAT)
        profile = rng.uniform(1500.0, 2100.0, VGLVLS.size - 1)

        operator = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_MODEL_TOP)
        got = operator.weights @ profile + operator.offset
        expected = reference_column(avker, prior, sat_edge, model_edge, profile)
        assert got == pytest.approx(expected, rel=1e-10)


def test_unit_kernel_and_full_coverage_is_a_pressure_weighted_mean():
    sat_edge = sat_edges()
    model_edge = cmaq_edges(surface_pressure=sat_edge[-1], vgtop=0.0)
    avker = np.ones(N_SAT)
    prior = np.linspace(1900.0, 400.0, N_SAT)[::-1]

    operator = build_column_operator(sat_edge, avker, prior, model_edge)

    assert operator.offset == pytest.approx(0.0, abs=1e-9)
    assert operator.weights.sum() == pytest.approx(1.0)
    assert operator.pressure_weight.sum() == pytest.approx(1.0)
    # an equidistant retrieval grid has uniform pressure weights
    assert operator.pressure_weight == pytest.approx(np.full(N_SAT, 1.0 / N_SAT))


def test_constant_model_profile_matches_the_kernel_formula():
    """A constant model column reduces to apply_avker on a constant profile."""
    sat_edge = sat_edges()
    model_edge = cmaq_edges(surface_pressure=sat_edge[-1], vgtop=0.0)
    rng = np.random.default_rng(7)
    avker = rng.uniform(0.2, 1.2, N_SAT)
    prior = rng.uniform(400.0, 1900.0, N_SAT)
    value = 1850.0

    operator = build_column_operator(sat_edge, avker, prior, model_edge)

    got = operator.weights.sum() * value + operator.offset
    expected = (operator.pressure_weight * (prior + avker * (value - prior))).sum()
    assert got == pytest.approx(expected)


def test_partial_coverage_is_reported():
    sat_edge = sat_edges()
    operator = build_column_operator(
        sat_edge, np.ones(N_SAT), np.full(N_SAT, 1800.0), cmaq_edges()
    )

    # only the topmost retrieval layer reaches above VGTOP
    assert operator.coverage[0] < 1.0
    assert np.all(operator.coverage[1:] == pytest.approx(1.0))
    expected_gap = (VGTOP - sat_edge[0]) / (sat_edge[1] - sat_edge[0])
    assert 1.0 - operator.coverage[0] == pytest.approx(expected_gap)


def test_prior_offset_fill_is_continuous_with_the_model_top():
    """The filled column above the model top follows the model, not the prior.

    With a unit kernel and a prior that is constant in the region being filled,
    the fill reduces to the topmost model layer, so the simulated column is the
    pressure-weighted mean of the model column extended upwards at its top
    value - the same answer FILL_MODEL_TOP gives.
    """
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    avker = np.ones(N_SAT)
    prior = np.full(N_SAT, 1800.0)
    profile = np.linspace(1900.0, 1750.0, VGLVLS.size - 1)

    offset_fill = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_PRIOR_OFFSET)
    model_fill = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_MODEL_TOP)

    assert offset_fill.weights @ profile + offset_fill.offset == pytest.approx(
        model_fill.weights @ profile + model_fill.offset
    )


def test_prior_offset_fill_carries_the_prior_gradient():
    """A prior that falls off with altitude must pull the filled part down."""
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    avker = np.ones(N_SAT)
    # methane-like: falling towards the top of the atmosphere (index 0)
    prior = np.linspace(1000.0, 1850.0, N_SAT)
    profile = np.full(VGLVLS.size - 1, 1800.0)

    offset_fill = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_PRIOR_OFFSET)
    model_fill = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_MODEL_TOP)
    prior_fill = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_PRIOR)

    with_offset = offset_fill.weights @ profile + offset_fill.offset
    with_model = model_fill.weights @ profile + model_fill.offset
    with_prior = prior_fill.weights @ profile + prior_fill.offset

    # stretching the model top overstates the column, because it ignores the
    # fall-off the prior describes
    assert with_offset < with_model
    # but the model still sets the magnitude, and here it sits above the prior
    assert with_offset > with_prior

    # the whole difference is the prior's shape above the model top
    assert model_fill.weights == pytest.approx(offset_fill.weights)
    assert model_fill.offset - offset_fill.offset == pytest.approx(-offset_fill.offset)


def test_prior_offset_fill_tracks_the_model_top_layer():
    """Raising the model's top layer raises the filled column with it."""
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    avker = np.ones(N_SAT)
    prior = np.linspace(1000.0, 1850.0, N_SAT)

    operator = build_column_operator(sat_edge, avker, prior, model_edge, fill=FILL_PRIOR_OFFSET)

    profile = np.full(VGLVLS.size - 1, 1800.0)
    bumped = profile.copy()
    bumped[-1] += 100.0

    gap = (1.0 - operator.coverage) @ operator.pressure_weight
    change = operator.weights @ (bumped - profile)
    # the top layer now carries its own weight plus the whole filled column
    top_weight = operator.overlap[:, -1].sum() / (sat_edge[-1] - sat_edge[0])
    assert change == pytest.approx(100.0 * (top_weight + gap))


def test_prior_fill_does_not_depend_on_the_model_top():
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    prior = np.linspace(1000.0, 1850.0, N_SAT)

    operator = build_column_operator(
        sat_edge, np.ones(N_SAT), prior, model_edge, fill=FILL_PRIOR
    )

    # the top model layer only carries the part of the column it actually spans
    assert operator.weights[-1] == pytest.approx(
        operator.overlap[:, -1].sum() / (sat_edge[-1] - sat_edge[0])
    )
    assert operator.weights.sum() == pytest.approx(operator.coverage @ operator.pressure_weight)


def test_surface_pressure_mismatch_leaves_no_gap_at_the_bottom():
    """The model's bottom edge is pinned to the retrieval surface pressure."""
    sat_edge = sat_edges(surface_pressure=99752.0)

    for model_surface in (95000.0, 99752.0, 103000.0):
        operator = build_column_operator(
            sat_edge,
            np.ones(N_SAT),
            np.full(N_SAT, 1800.0),
            cmaq_edges(surface_pressure=model_surface),
        )
        # every retrieval layer below the model top is fully covered
        assert np.all(operator.coverage[1:] == pytest.approx(1.0))


def test_rejects_badly_ordered_input():
    sat_edge = sat_edges()
    model_edge = cmaq_edges()
    avker = np.ones(N_SAT)
    prior = np.full(N_SAT, 1800.0)

    with pytest.raises(ValueError, match="ascend"):
        build_column_operator(sat_edge[::-1], avker, prior, model_edge)
    with pytest.raises(ValueError, match="descend"):
        build_column_operator(sat_edge, avker, prior, model_edge[::-1])
    with pytest.raises(ValueError, match="one value per retrieval layer"):
        build_column_operator(sat_edge, avker[:-1], prior, model_edge)
    with pytest.raises(ValueError, match="unknown fill strategy"):
        build_column_operator(sat_edge, avker, prior, model_edge, fill="nonsense")
