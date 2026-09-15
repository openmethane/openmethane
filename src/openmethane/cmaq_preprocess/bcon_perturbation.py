"""Apply a known offset to the boundary concentration field.

The forward model reads boundary concentrations from `BNDY_GASC_1` and does not
care how they were produced, so the response of the simulated columns to a
genuine boundary perturbation can be measured with forward runs alone. That is
what the boundary-response experiment needs, and it needs no boundary
sensitivity in the adjoint.

The offset is applied in place, to the files the forward run will read, in the
same position in the pipeline as the CAMS bias correction: after
`cmaq_preprocess` has written BCON and before `fourdvar` runs the model.
"""

import os
import pathlib

import netCDF4 as nc
import xarray as xr

from openmethane.util.logger import get_logger

logger = get_logger(__name__)

# CMAQ carries mixing ratios in ppm; the boundary error is argued in ppb
PPB_PER_PPM = 1e3

# Units the perturbation assumes, and so the units it checks for. A file in
# anything else would be silently perturbed by the wrong amount.
EXPECTED_UNITS = "ppmV"

# Records the offset on each file it is applied to. The whole experiment is a
# difference between runs that differ only in the boundary field, so a run that
# used the wrong file is otherwise invisible in its output. Reading it back also
# makes a second application fail rather than silently double the offset.
OFFSET_ATTR = "OM_BCON_OFFSET_PPB"


def perturb_bcon_files(
    bcon_files: list[pathlib.Path],
    offset_ppb: float,
    species: str = "CH4",
) -> None:
    """Add a uniform offset to the boundary concentrations, in place.

    Parameters
    ----------
    bcon_files
        The BCON files the forward run will read, one per day.
    offset_ppb
        Offset added to every perimeter cell, layer and timestep, in ppb.
    species
        Species to perturb.
    """
    for file in bcon_files:
        _perturb_file(file, offset_ppb, species)
        logger.info(f"{file}: {species} offset by {offset_ppb:+g} ppb")


def _perturb_file(file: pathlib.Path, offset_ppb: float, species: str) -> None:
    # the file is rewritten whole, so the format it came in has to be carried
    # over explicitly; xarray writes NETCDF4 by default whatever it read
    with nc.Dataset(file) as dataset:
        data_model = dataset.data_model

    with xr.open_dataset(file) as ds:
        contents = ds.load()

    applied = contents.attrs.get(OFFSET_ATTR)
    if applied is not None:
        raise ValueError(
            f"{file} already carries a boundary offset of {applied:+g} ppb. "
            "Perturb a freshly generated BCON file rather than an already "
            "perturbed one; offsets applied twice compound."
        )

    units = contents[species].attrs.get("units", "").strip()
    if units != EXPECTED_UNITS:
        raise ValueError(
            f"{file}: {species} units are {units!r}, expected {EXPECTED_UNITS!r}; "
            "the offset would be applied in the wrong units"
        )

    contents[species] += offset_ppb / PPB_PER_PPM
    contents.attrs[OFFSET_ATTR] = float(offset_ppb)

    # written beside the original so the replacement stays on one filesystem
    temp_file = file.with_name(f"{file.name}.perturbed")
    contents.to_netcdf(temp_file, format=data_model)
    os.replace(temp_file, file)
