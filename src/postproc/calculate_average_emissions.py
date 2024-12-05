import glob
import pathlib

import numpy as np
import xarray as xr

from fourdvar.datadef import PhysicalData

SPECIES_MOLEMASS = {"CH4": 16}  # molar mass in gram
G2KG = 1e-3  # conv factor kg to g


def calculate_average_emissions(
    posterior_multipliers: PhysicalData,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
    species: str = "CH4",
):
    prior_emis_files = list_emis_template_files(template_dir, emis_template)
    if len(prior_emis_files) == 0:
        raise ValueError(f"no emission template files found at {template_dir}")
    prior_emis_list = []
    for filename in prior_emis_files:
        with xr.open_dataset(filename) as xrds:
            prior_emis_list.append(xrds[species].to_numpy())
    prior_emis_array = np.array(prior_emis_list)
    prior_emis_mean_3d = prior_emis_array.mean(axis=(0, 1))
    prior_emis_mean_surf = prior_emis_mean_3d[0, ...]

    posterior_multiplier = posterior_multipliers.emis[species]

    if posterior_multipliers.emis[species].ndim > 2:
        averaged_dimensions = posterior_multipliers.emis[species].ndim - 2
        averaged_axes = tuple(range(averaged_dimensions))
        posterior_multiplier = posterior_multipliers.emis[species].mean(axis=averaged_axes)

    posterior_emis_mean_surf = posterior_multiplier * prior_emis_mean_surf

    # create output based on an emis file input
    with xr.open_dataset(prior_emis_files[0]) as in_ds:
        out_ds = xr.Dataset()
        copy_attributes(in_ds, out_ds, delete_attrs=["NVARS", "NLAYS"])
        cell_area = in_ds.XCELL * in_ds.YCELL
        conv_fac = SPECIES_MOLEMASS[species] * G2KG
        posterior_emis_mean_output = posterior_emis_mean_surf * conv_fac / cell_area
        # now create coordinates, missing from input
        x = in_ds.XORIG + 0.5 * in_ds.XCELL + np.arange(in_ds.NCOLS) * in_ds.XCELL
        y = in_ds.YORIG + 0.5 * in_ds.YCELL + np.arange(in_ds.NROWS) * in_ds.YCELL
        posterior_emis_mean_xr = xr.DataArray(posterior_emis_mean_output, coords={"y": y, "x": x})
        posterior_emis_mean_xr.attrs["units"] = "kg/m**2/s"
        out_ds[species] = posterior_emis_mean_xr
        return out_ds


def copy_attributes(
    in_ds: xr.Dataset,
    out_ds: xr.Dataset,
    override_attrs=None,
    delete_attrs=None,
):
    # make sure nothing is in mutually exclusive dicts
    if (delete_attrs is not None) and (override_attrs is not None):
        delete_keys = set(delete_attrs.keys())
        override_keys = set(override_attrs.keys())
        if override_keys.intersection(delete_keys) is not None:
            raise ValueError("keys appearing in both delete and override dictionaries")
    for k in in_ds.attrs:
        if k not in delete_attrs:
            out_ds.attrs[k] = in_ds.attrs[k]


def list_emis_template_files(
    template_dir: pathlib.Path,
    emis_template: str,
) -> list:
    prior_emis_glob = pathlib.Path(template_dir, "record", emis_template)
    prior_emis_files = glob.glob(str(prior_emis_glob))
    prior_emis_files.sort()
    return prior_emis_files
