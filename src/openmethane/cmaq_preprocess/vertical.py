"""Remap a profile on pressure levels onto CMAQ's sigma layers.

CAMS reports mixing ratios at a handful of pressure levels; CMAQ wants a mean
for each of its sigma layers. Above about 400 hPa CMAQ's layers are finer than
the CAMS levels, so picking the nearest level gives several layers the same
number and turns a smooth profile into a staircase, with the steps landing where
the vertical gradient is largest.

The remapping here reconstructs the profile as linear in log pressure between
levels and averages that reconstruction over each layer's pressure thickness.
Weighting by pressure thickness is weighting by air mass, so the column burden
of the reconstruction survives the remapping exactly.
"""

import numpy


def layer_edge_pressure(
    surface_pressure: numpy.ndarray, sigma: numpy.ndarray, model_top_pressure: float
) -> numpy.ndarray:
    """Pressure at the edges of each CMAQ layer

    CMAQ's vertical coordinate is sigma, so a layer's pressure depends on the
    surface pressure of the column it sits above.

    Args:
        surface_pressure: surface pressure (Pa) of each column, any shape
        sigma: the domain's `VGLVLS`, one entry per layer edge, 1.0 at the
            surface descending to 0.0 at the model top
        model_top_pressure: the domain's `VGTOP` (Pa)

    Returns:
        Edge pressures (Pa) with the layer edges on the leading axis, ordered
        from the surface upwards, and the shape of `surface_pressure` trailing
    """
    surface_pressure = numpy.asarray(surface_pressure, dtype=float)
    sigma = numpy.asarray(sigma, dtype=float).reshape((-1,) + (1,) * surface_pressure.ndim)

    return (surface_pressure[numpy.newaxis, ...] - model_top_pressure) * sigma + model_top_pressure


def surface_pressure_from_layer(
    layer_pressure: numpy.ndarray, sigma: numpy.ndarray, model_top_pressure: float, layer: int = 0
) -> numpy.ndarray:
    """Recover a column's surface pressure from the mid-point pressure of one layer

    MCIP writes surface pressure on the interior grid only (`PRSFC` in
    METCRO2D), but the boundary columns need it too. METBDY3D carries mid-layer
    pressures on the perimeter, and inverting the sigma coordinate recovers the
    surface pressure they were built from.

    Args:
        layer_pressure: mid-point pressure (Pa) of `layer` for each column
        sigma: the domain's `VGLVLS`
        model_top_pressure: the domain's `VGTOP` (Pa)
        layer: which layer `layer_pressure` belongs to, counting from the surface

    Returns:
        Surface pressure (Pa), the shape of `layer_pressure`
    """
    sigma = numpy.asarray(sigma, dtype=float)
    mid_sigma = (sigma[layer] + sigma[layer + 1]) / 2.0

    return (numpy.asarray(layer_pressure, dtype=float) - model_top_pressure) / mid_sigma + (
        model_top_pressure
    )


def _cumulative_burden(level_pressure: numpy.ndarray, level_value: numpy.ndarray) -> numpy.ndarray:
    """Integral of the reconstructed profile from the top level down to each level

    Between levels the profile is linear in log pressure, so with
    `s = (c1 - c0) / log(p1 / p0)` the integral over a segment is

        c0 * (p - p0) + s * (p * log(p / p0) - (p - p0))

    which is what this accumulates, and what `_burden_at` evaluates part way
    through a segment.
    """
    p0 = level_pressure[:-1]
    p1 = level_pressure[1:]
    c0 = level_value[:-1]
    slope = numpy.diff(level_value, axis=0) / numpy.log(p1 / p0).reshape(
        (-1,) + (1,) * (level_value.ndim - 1)
    )

    p0 = p0.reshape((-1,) + (1,) * (level_value.ndim - 1))
    p1 = p1.reshape((-1,) + (1,) * (level_value.ndim - 1))
    segment = c0 * (p1 - p0) + slope * (p1 * numpy.log(p1 / p0) - (p1 - p0))

    burden = numpy.zeros_like(level_value)
    numpy.cumsum(segment, axis=0, out=burden[1:])

    return burden


def _burden_at(
    pressure: numpy.ndarray,
    level_pressure: numpy.ndarray,
    level_value: numpy.ndarray,
    burden: numpy.ndarray,
) -> numpy.ndarray:
    """Integral of the reconstructed profile from the top level down to `pressure`

    Outside the levels the profile is held at its end value, which matters below
    the lowest CAMS level (1000 hPa) since surface pressure often exceeds it.
    """
    # Each pressure sits in the segment starting at the last level at or above it.
    segment = numpy.clip(
        numpy.searchsorted(level_pressure, pressure, side="right") - 1,
        0,
        level_pressure.size - 2,
    )

    p0 = level_pressure[segment]
    p1 = level_pressure[segment + 1]
    c0 = numpy.take_along_axis(level_value, segment, axis=0)
    c1 = numpy.take_along_axis(level_value, segment + 1, axis=0)
    slope = (c1 - c0) / numpy.log(p1 / p0)

    within = numpy.take_along_axis(burden, segment, axis=0) + (
        c0 * (pressure - p0) + slope * (pressure * numpy.log(pressure / p0) - (pressure - p0))
    )

    # Constant extension past either end of the levels.
    above = level_value[0] * (pressure - level_pressure[0])
    below = burden[-1] + level_value[-1] * (pressure - level_pressure[-1])

    return numpy.where(
        pressure < level_pressure[0],
        above,
        numpy.where(pressure > level_pressure[-1], below, within),
    )


def mass_weighted_layer_mean(
    level_pressure: numpy.ndarray, level_value: numpy.ndarray, edge_pressure: numpy.ndarray
) -> numpy.ndarray:
    """Average a profile on pressure levels over each of a column's layers

    The profile is reconstructed linear in log pressure between levels and held
    at its end value beyond them, then integrated over each layer's pressure
    thickness. The integral is analytic rather than sampled, so the column
    burden of the reconstruction is preserved to rounding.

    Args:
        level_pressure: pressure (Pa) of each input level, strictly monotonic,
            one axis only and shared by every column
        level_value: value at each level, levels on the leading axis and columns
            trailing
        edge_pressure: layer edge pressures (Pa) per column, edges on the
            leading axis, as `layer_edge_pressure` returns them

    Returns:
        The layer means, one fewer entry on the leading axis than
        `edge_pressure`, with the column axes of `level_value` trailing
    """
    level_pressure = numpy.asarray(level_pressure, dtype=float)
    level_value = numpy.asarray(level_value, dtype=float)
    edge_pressure = numpy.asarray(edge_pressure, dtype=float)

    if level_pressure.ndim != 1:
        raise ValueError("level_pressure must be one-dimensional")
    if level_value.shape[0] != level_pressure.size:
        raise ValueError("level_value must have one entry per level on its leading axis")
    if level_value.shape[1:] != edge_pressure.shape[1:]:
        raise ValueError("level_value and edge_pressure must describe the same columns")

    # CAMS lists its levels from the surface upwards; the integral runs the other way.
    if level_pressure[0] > level_pressure[-1]:
        level_pressure = level_pressure[::-1]
        level_value = level_value[::-1]
    if numpy.any(numpy.diff(level_pressure) <= 0.0):
        raise ValueError("level_pressure must be strictly monotonic")

    burden = _cumulative_burden(level_pressure, level_value)
    edge_burden = _burden_at(edge_pressure, level_pressure, level_value, burden)

    # Edge 0 is the surface, so thickness is the drop from one edge to the next.
    return numpy.diff(edge_burden, axis=0) / numpy.diff(edge_pressure, axis=0)
