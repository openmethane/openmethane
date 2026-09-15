"""Tests for the boundary-condition perturbation used by the boundary-response experiment."""

import shutil

import netCDF4 as nc
import numpy as np
import pytest
import xarray as xr

from openmethane.cmaq_preprocess.bcon_perturbation import (
    OFFSET_ATTR,
    PPB_PER_PPM,
    perturb_bcon_files,
)

BCON_FILE_NAME = "template_bcon_profile_CH4only_d01.nc"


@pytest.fixture
def bcon_file(test_data_dir, tmp_path):
    """A BCON file somewhere it can be perturbed in place."""
    destination = tmp_path / BCON_FILE_NAME
    shutil.copy(test_data_dir / "cmaq" / BCON_FILE_NAME, destination)
    return destination


def test_offset_is_uniform_and_in_ppm(bcon_file):
    """Every perimeter cell, layer and timestep moves by the offset, converted to ppm."""
    with xr.open_dataset(bcon_file) as ds:
        before = ds["CH4"].to_numpy()

    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with xr.open_dataset(bcon_file) as ds:
        after = ds["CH4"].to_numpy()

    np.testing.assert_allclose(after - before, 20.0 / PPB_PER_PPM, rtol=1e-5)


def test_other_variables_and_metadata_survive(bcon_file):
    """The perturbed file must still be readable by CMAQ as a boundary file."""
    with xr.open_dataset(bcon_file) as ds:
        original = ds.load()

    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with xr.open_dataset(bcon_file) as ds:
        perturbed = ds.load()

    assert set(perturbed.variables) == set(original.variables)
    assert perturbed["CH4"].dims == original["CH4"].dims
    assert perturbed["CH4"].attrs == original["CH4"].attrs
    # the grid description IOAPI reads the perimeter layout from
    for attr in ("NCOLS", "NROWS", "NTHIK", "NLAYS", "SDATE", "STIME", "TSTEP"):
        assert perturbed.attrs[attr] == original.attrs[attr]
    for name, variable in original.variables.items():
        if name != "CH4":
            np.testing.assert_array_equal(perturbed[name].to_numpy(), variable.to_numpy())


@pytest.mark.parametrize("data_model", ["NETCDF3_CLASSIC", "NETCDF4"])
def test_netcdf_format_survives(bcon_file, data_model):
    """IOAPI reads whichever format CMAQ wrote, so the rewrite must not change it."""
    with xr.open_dataset(bcon_file) as ds:
        contents = ds.load()
    contents.to_netcdf(bcon_file, mode="w", format=data_model)

    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with nc.Dataset(bcon_file) as dataset:
        assert dataset.data_model == data_model


def test_applied_offset_is_recorded(bcon_file):
    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with xr.open_dataset(bcon_file) as ds:
        assert ds.attrs[OFFSET_ATTR] == pytest.approx(20.0)


def test_perturbing_twice_is_refused(bcon_file):
    """Offsets compound, so a file that already carries one is not perturbed again."""
    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with pytest.raises(ValueError, match="already carries a boundary offset"):
        perturb_bcon_files([bcon_file], offset_ppb=20.0)

    with xr.open_dataset(bcon_file) as ds:
        assert ds.attrs[OFFSET_ATTR] == pytest.approx(20.0)


def test_unexpected_units_are_refused(bcon_file):
    """The ppb-to-ppm conversion is only right for a file in ppmV."""
    with xr.open_dataset(bcon_file) as ds:
        contents = ds.load()
    contents["CH4"].attrs["units"] = "ppbV"
    contents.to_netcdf(bcon_file, mode="w")

    with pytest.raises(ValueError, match="units are 'ppbV'"):
        perturb_bcon_files([bcon_file], offset_ppb=20.0)


def test_no_leftover_temporary_file(bcon_file):
    perturb_bcon_files([bcon_file], offset_ppb=20.0)

    assert sorted(p.name for p in bcon_file.parent.iterdir()) == [BCON_FILE_NAME]


def test_nothing_is_written_when_a_later_file_is_bad(bcon_file, tmp_path):
    """All days or none: a bad file must stop the first file being touched.

    A failure part way through would leave the forward model reading a boundary
    field that steps partway through the run, which is not a perturbation of any
    describable size.
    """
    with xr.open_dataset(bcon_file) as ds:
        before = ds["CH4"].to_numpy()

    missing = tmp_path / "absent" / BCON_FILE_NAME
    with pytest.raises(FileNotFoundError, match="does not exist"):
        perturb_bcon_files([bcon_file, missing], offset_ppb=20.0)

    with xr.open_dataset(bcon_file) as ds:
        np.testing.assert_array_equal(ds["CH4"].to_numpy(), before)
        assert OFFSET_ATTR not in ds.attrs
