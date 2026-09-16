"""Scale the vertical methane gradient in the model's top layers.

CMAQ's lid at `VGTOP` sits at 5000 Pa, in the middle of the stratospheric
methane falloff: over the Australian domain CAMS runs from about 1768 ppb at
186 hPa to 1455 ppb at 55 hPa. Nothing is prescribed above the lid, so vertical
diffusion piles methane against it while BCON restores the correct values around
the perimeter, and vertical advection exchanges air through it using the top
layer's own value. Over a month the model's top layer ends up 150 ppb above the
field driving it, and the column carries 70% of a +0.2 ppb/day drift.

Removing the gradient removes the thing that is hypothesised to drive that, and
it can be done entirely in the files the forward model reads. For layers above
an anchor, the profile is replaced by

    x'[L] = x[anchor] + scale * ( x[L] - x[anchor] )

column by column, so horizontal structure is preserved and `scale = 1` is the
identity. See https://github.com/openmethane/openmethane/issues/248.

Applied in place, in the same position in the pipeline as the CAMS bias
correction: after `cmaq_preprocess` has written ICON and BCON, before `fourdvar`
runs the model.
"""

import os
import pathlib

import netCDF4 as nc
import xarray as xr

from openmethane.util.logger import get_logger

logger = get_logger(__name__)

# Units the rewrite assumes, and so the units it checks for. A file in anything
# else would still be scaled correctly -- the operation is affine in the
# file's own units -- but a file that is not what it claims to be is a sign
# something upstream has changed, and this experiment cannot absorb that.
EXPECTED_UNITS = "ppmV"

LAYER_DIM = "LAY"

# Recorded on each file the rewrite touches. The experiment is a difference
# between runs that differ only here, so an arm that read the wrong files is
# otherwise invisible in its output. Reading it back also makes a second
# application fail rather than silently compounding.
SCALE_ATTR = "OM_TOP_GRADIENT_SCALE"
ANCHOR_ATTR = "OM_TOP_GRADIENT_ANCHOR_LAYER"


def scale_top_gradient(
    files: list[pathlib.Path],
    anchor_layer: int,
    scale: float,
    species: str = "CH4",
) -> None:
    """Rescale the profile above `anchor_layer`, in place.

    Parameters
    ----------
    files
        The ICON and BCON files the forward run will read. Both layouts work:
        the rewrite indexes the layer dimension by name and leaves the rest of
        the shape alone.
    anchor_layer
        Zero-based layer the rescaled profile is pinned to. Layers at or below
        it are untouched; layers above it are moved towards its value.
    scale
        Multiplier on the departure from the anchor. `1` is the identity, `0`
        removes the gradient entirely.
    species
        Species to rewrite.
    """
    # Every file is checked before any is written. The run's initial and
    # boundary fields have to be treated on all days or none: a failure part way
    # through would leave the forward model reading a profile that changes
    # shape mid-run, which is not a perturbation of any describable kind.
    for file in files:
        _check_file(file, anchor_layer, species)

    for file in files:
        _rewrite_file(file, anchor_layer, scale, species)
        logger.info(f"{file}: {species} above layer {anchor_layer} scaled by {scale:g}")


def _check_file(file: pathlib.Path, anchor_layer: int, species: str) -> None:
    if not file.exists():
        raise FileNotFoundError(
            f"{file} does not exist; the forward run reads one file per day, so "
            "every day has to be present before any is rewritten"
        )

    with xr.open_dataset(file) as contents:
        applied = contents.attrs.get(SCALE_ATTR)
        if applied is not None:
            raise ValueError(
                f"{file} already had its top gradient scaled by {applied:g}. "
                "Rewrite a freshly generated file rather than an already "
                "rewritten one; the scalings compound."
            )

        if species not in contents:
            raise ValueError(f"{file} has no variable {species!r}")

        units = contents[species].attrs.get("units", "").strip()
        if units != EXPECTED_UNITS:
            raise ValueError(f"{file}: {species} units are {units!r}, expected {EXPECTED_UNITS!r}")

        dims = contents[species].dims
        if LAYER_DIM not in dims:
            raise ValueError(
                f"{file}: {species} has dimensions {dims}, with no {LAYER_DIM!r} to "
                "anchor the rescaling to"
            )

        layers = contents.sizes[LAYER_DIM]
        if not 0 <= anchor_layer < layers - 1:
            raise ValueError(
                f"{file}: anchor layer {anchor_layer} leaves nothing above it to "
                f"rescale; the file has {layers} layers"
            )


def _rewrite_file(file: pathlib.Path, anchor_layer: int, scale: float, species: str) -> None:
    # the file is rewritten whole, so the format it came in has to be carried
    # over explicitly; xarray writes NETCDF4 by default whatever it read
    with nc.Dataset(file) as dataset:
        data_model = dataset.data_model

    with xr.open_dataset(file) as ds:
        contents = ds.load()

    field = contents[species]
    values = field.to_numpy()
    axis = field.dims.index(LAYER_DIM)

    def at(layers):
        index = [slice(None)] * values.ndim
        index[axis] = layers
        return tuple(index)

    # kept as a length-1 slice rather than an index so it broadcasts back over
    # the layers above it whatever the rest of the shape is
    anchor = values[at(slice(anchor_layer, anchor_layer + 1))]
    above = at(slice(anchor_layer + 1, None))
    values[above] = anchor + scale * (values[above] - anchor)
    contents[species] = (field.dims, values, field.attrs)

    contents.attrs[SCALE_ATTR] = float(scale)
    contents.attrs[ANCHOR_ATTR] = int(anchor_layer)

    # written beside the original so the replacement stays on one filesystem
    temp_file = file.with_name(f"{file.name}.rescaled")
    contents.to_netcdf(temp_file, format=data_model)
    os.replace(temp_file, file)
