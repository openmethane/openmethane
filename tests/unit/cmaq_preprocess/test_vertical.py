import numpy
import pytest

from openmethane.cmaq_preprocess.vertical import (
    layer_edge_pressure,
    mass_weighted_layer_mean,
    surface_pressure_from_layer,
)

# The CAMS EAC4 pressure levels, in Pa, in the order the files list them.
CAMS_LEVELS = (
    numpy.array(
        [
            1000.0, 950.0, 925.0, 900.0, 850.0, 800.0, 700.0, 600.0, 500.0,
            400.0, 300.0, 250.0, 200.0, 150.0, 100.0, 70.0, 50.0, 30.0,
            20.0, 10.0, 7.0, 5.0, 3.0, 2.0, 1.0,
        ]
    )
    * 100.0
)  # fmt: skip

SIGMA = numpy.array([1.0, 0.75, 0.5, 0.25, 0.0])
MODEL_TOP = 5000.0


def _log_linear(pressure, value_at_1000hpa=1.8, slope=-0.1):
    """A profile that is exactly linear in log pressure"""
    return value_at_1000hpa + slope * numpy.log(pressure / 100000.0)


def _log_linear_layer_mean(pressure_bottom, pressure_top, value_at_1000hpa=1.8, slope=-0.1):
    """The analytic mass-weighted mean of `_log_linear` over one layer"""

    def integral(p):
        return value_at_1000hpa * (p - 100000.0) + slope * (
            p * numpy.log(p / 100000.0) - (p - 100000.0)
        )

    return (integral(pressure_bottom) - integral(pressure_top)) / (pressure_bottom - pressure_top)


def test_layer_edge_pressure_spans_surface_to_model_top():
    surface = numpy.array([[100000.0, 95000.0]])

    edges = layer_edge_pressure(surface, SIGMA, MODEL_TOP)

    assert edges.shape == (SIGMA.size, 1, 2)
    numpy.testing.assert_allclose(edges[0], surface)
    numpy.testing.assert_allclose(edges[-1], MODEL_TOP)
    # Edges descend from the surface upwards, so every layer has positive thickness.
    assert (numpy.diff(edges, axis=0) < 0.0).all()


def test_surface_pressure_from_layer_inverts_the_sigma_coordinate():
    surface = numpy.array([100000.0, 95000.0, 101300.0])
    edges = layer_edge_pressure(surface, SIGMA, MODEL_TOP)
    mid_layer = (edges[0] + edges[1]) / 2.0

    numpy.testing.assert_allclose(
        surface_pressure_from_layer(mid_layer, SIGMA, MODEL_TOP), surface
    )


def test_a_constant_profile_stays_constant():
    edges = layer_edge_pressure(numpy.array([100000.0]), SIGMA, MODEL_TOP)
    values = numpy.full((CAMS_LEVELS.size, 1), 1.8)

    numpy.testing.assert_allclose(mass_weighted_layer_mean(CAMS_LEVELS, values, edges), 1.8)


def test_a_log_linear_profile_is_reproduced_exactly():
    """The reconstruction is log-linear, so it integrates such a profile exactly"""
    edges = layer_edge_pressure(numpy.array([100000.0, 95000.0]), SIGMA, MODEL_TOP)
    values = numpy.repeat(_log_linear(CAMS_LEVELS)[:, numpy.newaxis], 2, axis=1)

    means = mass_weighted_layer_mean(CAMS_LEVELS, values, edges)

    numpy.testing.assert_allclose(means, _log_linear_layer_mean(edges[:-1], edges[1:]))


def test_the_column_burden_is_preserved():
    """Mass-weighted, so the layer means hold the same burden as the levels they came from"""
    edges = layer_edge_pressure(numpy.array([100000.0, 95000.0]), SIGMA, MODEL_TOP)
    values = numpy.repeat(_log_linear(CAMS_LEVELS)[:, numpy.newaxis], 2, axis=1)

    means = mass_weighted_layer_mean(CAMS_LEVELS, values, edges)

    thickness = -numpy.diff(edges, axis=0)
    burden = (means * thickness).sum(axis=0) / thickness.sum(axis=0)
    expected = _log_linear_layer_mean(edges[0], edges[-1])

    numpy.testing.assert_allclose(burden, expected, rtol=1e-12)


def test_the_level_order_does_not_matter():
    edges = layer_edge_pressure(numpy.array([100000.0]), SIGMA, MODEL_TOP)
    values = _log_linear(CAMS_LEVELS)[:, numpy.newaxis]

    descending = mass_weighted_layer_mean(CAMS_LEVELS, values, edges)
    ascending = mass_weighted_layer_mean(CAMS_LEVELS[::-1], values[::-1], edges)

    numpy.testing.assert_allclose(descending, ascending)


def test_the_profile_is_extended_below_the_lowest_level():
    """Surface pressure routinely exceeds the lowest CAMS level of 1000 hPa"""
    edges = layer_edge_pressure(numpy.array([103000.0]), SIGMA, MODEL_TOP)
    values = numpy.full((CAMS_LEVELS.size, 1), 1.8)
    values[0] = 2.0  # the 1000 hPa level

    means = mass_weighted_layer_mean(CAMS_LEVELS, values, edges)

    # The lowest layer reaches below 1000 hPa, where the 1000 hPa value is held,
    # so its mean sits between the two level values rather than outside them.
    assert 1.8 < means[0, 0] < 2.0


def test_layers_finer_than_the_levels_do_not_repeat():
    """The defect this replaced: nearest-level lookup gave neighbouring layers one value

    A 32 layer domain has several layers between adjacent CAMS levels near the
    tropopause, and a strictly decreasing profile must stay strictly decreasing
    across them.
    """
    sigma = numpy.linspace(1.0, 0.0, 33)
    edges = layer_edge_pressure(numpy.array([100000.0]), sigma, MODEL_TOP)
    values = _log_linear(CAMS_LEVELS)[:, numpy.newaxis]

    means = mass_weighted_layer_mean(CAMS_LEVELS, values, edges)

    assert (numpy.diff(means, axis=0) > 0.0).all()


@pytest.mark.parametrize(
    "level_pressure, level_value, message",
    [
        (
            numpy.array([[1000.0, 900.0]]),
            numpy.zeros((2, 1)),
            "level_pressure must be one-dimensional",
        ),
        (
            numpy.array([100000.0, 90000.0]),
            numpy.zeros((3, 1)),
            "level_value must have one entry per level",
        ),
        (
            numpy.array([100000.0, 90000.0]),
            numpy.zeros((2, 4)),
            "must describe the same columns",
        ),
        (
            numpy.array([100000.0, 100000.0]),
            numpy.zeros((2, 1)),
            "level_pressure must be strictly monotonic",
        ),
    ],
)
def test_mismatched_inputs_are_rejected(level_pressure, level_value, message):
    edges = layer_edge_pressure(numpy.array([100000.0]), SIGMA, MODEL_TOP)

    with pytest.raises(ValueError, match=message):
        mass_weighted_layer_mean(level_pressure, level_value, edges)
