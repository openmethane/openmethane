# adapted from python/TROPOMI_operator.py from https://github.com/hannahnesser/TROPOMI_inversion
# published in https://doi.org/10.5194/acp-24-5069-2024

"""Vertical part of the TROPOMI CH4 column observation operator.

The operational TROPOMI CH4 retrieval reports a column-averaged dry-air mole
fraction together with a column averaging kernel ``A`` and the a-priori profile
it was retrieved against. Simulating that quantity from a model profile is

    y = sum_j pw_j [ x_a,j + A_j ( x_m,j - x_a,j ) ]                       (1)

where ``j`` indexes the retrieval layers, ``pw_j`` are the retrieval's pressure
weights and ``x_m,j`` is the model profile mapped onto the retrieval grid. This
follows the reference implementation at
https://github.com/hannahnesser/TROPOMI_inversion/blob/main/python/TROPOMI_operator.py
(``GC_to_sat_levels`` and ``apply_avker``).

The mapping of the model onto the retrieval grid is by pressure overlap,

    O_ji = max( 0, min(p_j+1, P_i) - max(p_j, P_i+1) )                     (2)

with ``p`` the retrieval level pressures and ``P`` the model level pressures.

Equation (1) is *affine* in the model state, which is what makes it cheap to use
inside fourdvar: it can be written

    y = sum_i w_i x_i + c                                                  (3)

so the per-model-layer weights ``w`` slot straight into the existing
``weight_grid`` machinery, ``c`` is a per-observation constant, and the adjoint
forcing (which only needs dy/dx = w) is unchanged.

Partial vertical coverage
-------------------------
CMAQ's top (VGTOP, 5000 Pa in the Australian domain) lies well below the top of
the retrieval grid, so the model does not span the whole column: roughly the top
5% of the air mass is missing. Each retrieval layer therefore has a covered
fraction ``f_j``, and the uncovered part must be filled from somewhere:

    x_m,j = sum_i (O_ji / dp_j) x_i  +  (1 - f_j) x_fill,j                 (4)

Three fill strategies are supported, selected by ``fill``:

``"prior_offset"`` (default)
    Assume CMAQ gets the vertical *structure* right up to its top and the
    retrieval prior gets the structure but not the magnitude right above it.
    The prior profile is shifted by the constant needed to make it continuous
    with the CMAQ profile at the model top:

        x_fill,j = u_j + ( x_top - a_top )

    where ``u_j`` is the prior averaged over the uncovered part of layer j,
    ``x_top`` is the topmost CMAQ layer, and ``a_top`` is the prior averaged
    over that same CMAQ layer (so that like is compared with like). The fill
    still depends linearly on the model state, through ``x_top``, so (3) holds.

``"prior"``
    ``x_fill,j = u_j``: trust the retrieval prior above the model top and make
    no claim about air the model does not simulate.

``"model_top"``
    ``x_fill,j = x_top``: extend the topmost model layer to the top of the
    atmosphere. This is what the reference implementation does, and is
    appropriate when the model top is high enough that the extension is
    harmless. It is a poor choice for CMAQ, whose top layer sits in the lower
    stratosphere where methane is still falling steeply with altitude.

Vertical conventions
--------------------
Retrieval quantities are ordered top-of-atmosphere first, matching the S5P CH4
product (``level`` and ``layer`` both carry ``positive = "down"``, and
``altitude_levels[0]`` is ~65 km); ``sat_edge`` is therefore *ascending* in
pressure. Model quantities are ordered surface first, matching CMAQ's layer
indexing and ``ModelSpace.get_pressure_bounds``; ``model_edge`` is therefore
*descending* in pressure. The returned weights use the CMAQ ordering.
"""

import attrs
import numpy as np

# Fill strategies for the part of the retrieval column the model does not span.
FILL_PRIOR_OFFSET = "prior_offset"
FILL_PRIOR = "prior"
FILL_MODEL_TOP = "model_top"
FILL_STRATEGIES = (FILL_PRIOR_OFFSET, FILL_PRIOR, FILL_MODEL_TOP)


@attrs.frozen
class ColumnOperator:
    """The vertical observation operator for a single sounding.

    Attributes
    ----------
    weights
        Weight applied to each model layer, surface first, dimensionless.
        The simulated column is ``weights @ model_profile + offset``, with the
        model profile in the same units as ``prior`` (ppb).
    offset
        The part of the simulated column that does not depend on the model
        state (ppb): the ``(1 - A) x_a`` term plus the fill contribution.
    pressure_weight
        Retrieval pressure weights ``pw_j``, top first. Sums to one.
    coverage
        Fraction ``f_j`` of each retrieval layer spanned by the model, top
        first. Values below one mean part of that layer was filled.
    overlap
        The ``(n_retrieval_layer, n_model_layer)`` pressure overlap matrix (Pa).
    """

    weights: np.ndarray
    offset: float
    pressure_weight: np.ndarray
    coverage: np.ndarray
    overlap: np.ndarray


def pressure_overlap(sat_edge: np.ndarray, model_edge: np.ndarray) -> np.ndarray:
    """Pressure thickness shared by each pair of retrieval and model layers.

    Parameters
    ----------
    sat_edge
        Retrieval level pressures (Pa), ascending, length ``n_sat_layer + 1``.
    model_edge
        Model level pressures (Pa), descending, length ``n_model_layer + 1``.

    Returns
    -------
        ``(n_sat_layer, n_model_layer)`` array of overlapping pressure
        thicknesses in Pa. Equation (2).
    """
    sat_lo = sat_edge[:-1][:, np.newaxis]
    sat_hi = sat_edge[1:][:, np.newaxis]
    model_lo = model_edge[1:][np.newaxis, :]
    model_hi = model_edge[:-1][np.newaxis, :]

    return np.clip(np.minimum(sat_hi, model_hi) - np.maximum(sat_lo, model_lo), 0.0, None)


def _interp_mean(lo: float, hi: float, knot_p: np.ndarray, knot_v: np.ndarray) -> float:
    """Mean of a piecewise-linear profile over a pressure interval.

    The profile is reconstructed by linear interpolation of ``knot_v`` at
    pressures ``knot_p``, held constant outside that range. The integration is
    exact for that reconstruction.
    """
    if hi <= lo:
        return float(np.interp(lo, knot_p, knot_v))

    interior = knot_p[(knot_p > lo) & (knot_p < hi)]
    points = np.concatenate(([lo], interior, [hi]))
    values = np.interp(points, knot_p, knot_v)
    integral = np.sum(0.5 * (values[1:] + values[:-1]) * np.diff(points))

    return float(integral / (hi - lo))


def build_column_operator(
    sat_edge: np.ndarray,
    avker: np.ndarray,
    prior: np.ndarray,
    model_edge: np.ndarray,
    fill: str = FILL_PRIOR_OFFSET,
) -> ColumnOperator:
    """Build the affine column operator for a single sounding.

    Parameters
    ----------
    sat_edge
        Retrieval level pressures (Pa), ascending from the top of the
        atmosphere, length ``n_sat_layer + 1``.
    avker
        Column averaging kernel, dimensionless, top first.
    prior
        Retrieval a-priori profile as a dry-air mole fraction (ppb), top first.
    model_edge
        Model level pressures (Pa), descending from the surface, length
        ``n_model_layer + 1``.
    fill
        How to fill retrieval layers the model does not span. One of
        ``FILL_STRATEGIES``; see the module docstring.

    Returns
    -------
        The operator, such that ``weights @ model_profile + offset`` is the
        simulated column-averaged dry-air mole fraction in ppb, with
        ``model_profile`` a CMAQ profile in ppb ordered surface first.
    """
    if fill not in FILL_STRATEGIES:
        raise ValueError(f"unknown fill strategy {fill!r}, expected one of {FILL_STRATEGIES}")

    sat_edge = np.asarray(sat_edge, dtype=float)
    avker = np.asarray(avker, dtype=float)
    prior = np.asarray(prior, dtype=float)
    model_edge = np.asarray(model_edge, dtype=float)

    n_sat = sat_edge.size - 1
    if avker.shape != (n_sat,) or prior.shape != (n_sat,):
        raise ValueError("averaging kernel and prior must have one value per retrieval layer")
    if np.any(np.diff(sat_edge) <= 0.0):
        raise ValueError("retrieval level pressures must ascend from the top of the atmosphere")
    if np.any(np.diff(model_edge) >= 0.0):
        raise ValueError("model level pressures must descend from the surface")

    # The retrieval grid defines the column: A and pw are only meaningful on it.
    # Clip the model levels into that range and pin the model's bottom edge to
    # the retrieval surface pressure, so that differences in surface pressure
    # between the model and the retrieval do not leave a gap at the bottom.
    # np.clip copies, so the caller's array is left alone.
    model_edge = np.clip(model_edge, sat_edge[0], sat_edge[-1])
    model_edge[0] = sat_edge[-1]

    sat_thickness = np.diff(sat_edge)
    column_thickness = sat_edge[-1] - sat_edge[0]
    pressure_weight = sat_thickness / column_thickness

    overlap = pressure_overlap(sat_edge, model_edge)
    coverage = overlap.sum(axis=1) / sat_thickness

    # The covered part of the column, equation (4) first term, folded into (3).
    # pw_j / dp_j is the same constant for every layer, hence the simple form.
    weights = (avker[:, np.newaxis] * overlap).sum(axis=0) / column_thickness

    # The model spans a contiguous pressure range, so the uncovered part of each
    # retrieval layer is the slice above the model top.
    model_top = model_edge[-1]
    uncovered_lo = sat_edge[:-1]
    uncovered_hi = np.minimum(sat_edge[1:], model_top)
    uncovered = np.clip(uncovered_hi - uncovered_lo, 0.0, None)
    if not np.allclose(uncovered, sat_thickness * (1.0 - coverage)):
        raise AssertionError("model coverage of the retrieval column is not contiguous")

    # Piecewise-linear reconstruction of the prior, so that the prior can be
    # averaged over pressure ranges finer than a retrieval layer. Layer means
    # are treated as values at layer mid-pressures, the same convention used
    # elsewhere in the preprocessor.
    knot_p = 0.5 * (sat_edge[:-1] + sat_edge[1:])

    # x_fill,j = fill_const_j + fill_model_gain * x_top
    if fill == FILL_MODEL_TOP:
        fill_const = np.zeros(n_sat)
        fill_model_gain = 1.0
    else:
        fill_const = np.array(
            [
                _interp_mean(lo, hi, knot_p, prior) if width > 0.0 else 0.0
                for lo, hi, width in zip(uncovered_lo, uncovered_hi, uncovered)
            ]
        )
        if fill == FILL_PRIOR:
            fill_model_gain = 0.0
        else:
            # Shift the prior so that it is continuous with the model at the
            # model top, comparing like with like: the topmost model layer mean
            # against the prior averaged over that same layer.
            prior_at_model_top = _interp_mean(model_edge[-1], model_edge[-2], knot_p, prior)
            fill_const = fill_const - prior_at_model_top
            fill_model_gain = 1.0

    uncovered_weight = pressure_weight * avker * (1.0 - coverage)
    weights[-1] += fill_model_gain * uncovered_weight.sum()

    offset = float(
        (pressure_weight * (1.0 - avker) * prior).sum() + (uncovered_weight * fill_const).sum()
    )

    return ColumnOperator(
        weights=weights,
        offset=offset,
        pressure_weight=pressure_weight,
        coverage=coverage,
        overlap=overlap,
    )
