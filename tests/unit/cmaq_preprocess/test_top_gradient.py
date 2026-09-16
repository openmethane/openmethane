"""Tests for the top-gradient rescaling used by the model-top experiment (#248)."""

import shutil

import netCDF4 as nc
import numpy as np
import pytest
import xarray as xr

from openmethane.cmaq_preprocess.top_gradient import (
    ANCHOR_ATTR,
    LAYER_DIM,
    SCALE_ATTR,
    scale_top_gradient,
)

BCON_FILE_NAME = "template_bcon_profile_CH4only_d01.nc"
ICON_FILE_NAME = "template_icon_profile_CH4only_d01.nc"
ANCHOR = 23


@pytest.fixture(params=[BCON_FILE_NAME, ICON_FILE_NAME])
def cmaq_file(request, test_data_dir, tmp_path):
    """A boundary or initial condition file somewhere it can be rewritten in place.

    Both layouts are covered because the rescaling indexes the layer dimension
    by name: BCON is (TSTEP, LAY, PERIM) and ICON is (TSTEP, LAY, ROW, COL), and
    the experiment rewrites both.
    """
    destination = tmp_path / request.param
    shutil.copy(test_data_dir / "cmaq" / request.param, destination)
    return destination


def layer_axis(field):
    return field.dims.index(LAYER_DIM)


def test_gradient_is_removed_at_zero(cmaq_file):
    """Every layer above the anchor takes the anchor's value, column by column."""
    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.0)

    with xr.open_dataset(cmaq_file) as ds:
        field = ds["CH4"]
        values = field.to_numpy()
        anchor = np.take(values, ANCHOR, axis=layer_axis(field))
        for layer in range(ANCHOR + 1, ds.sizes[LAYER_DIM]):
            above = np.take(values, layer, axis=layer_axis(field))
            np.testing.assert_allclose(above, anchor, rtol=1e-6)


def test_scale_of_one_changes_nothing(cmaq_file):
    """The baseline arm runs the same code, so it has to be a numerical no-op."""
    with xr.open_dataset(cmaq_file) as ds:
        before = ds["CH4"].to_numpy()

    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=1.0)

    with xr.open_dataset(cmaq_file) as ds:
        np.testing.assert_array_equal(ds["CH4"].to_numpy(), before)


def test_departure_from_the_anchor_scales(cmaq_file):
    """Halving the scale halves the distance from the anchor, and only that."""
    with xr.open_dataset(cmaq_file) as ds:
        field = ds["CH4"]
        before = field.to_numpy()
        axis = layer_axis(field)

    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.5)

    with xr.open_dataset(cmaq_file) as ds:
        after = ds["CH4"].to_numpy()

    anchor = np.take(before, ANCHOR, axis=axis)
    for layer in range(ANCHOR + 1, before.shape[axis]):
        expected = anchor + 0.5 * (np.take(before, layer, axis=axis) - anchor)
        np.testing.assert_allclose(np.take(after, layer, axis=axis), expected, rtol=1e-6)


def test_layers_below_the_anchor_are_untouched(cmaq_file):
    with xr.open_dataset(cmaq_file) as ds:
        field = ds["CH4"]
        before = field.to_numpy()
        axis = layer_axis(field)

    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.0)

    with xr.open_dataset(cmaq_file) as ds:
        after = ds["CH4"].to_numpy()

    below = [slice(None)] * before.ndim
    below[axis] = slice(None, ANCHOR + 1)
    np.testing.assert_array_equal(after[tuple(below)], before[tuple(below)])


def test_other_variables_and_metadata_survive(cmaq_file):
    """The rewritten file must still be readable by CMAQ."""
    with xr.open_dataset(cmaq_file) as ds:
        original = ds.load()

    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.0)

    with xr.open_dataset(cmaq_file) as ds:
        rewritten = ds.load()

    assert set(rewritten.variables) == set(original.variables)
    assert rewritten["CH4"].dims == original["CH4"].dims
    assert rewritten["CH4"].attrs == original["CH4"].attrs
    for attr in ("NCOLS", "NROWS", "NTHIK", "NLAYS", "SDATE", "STIME", "TSTEP"):
        assert rewritten.attrs[attr] == original.attrs[attr]
    for name, variable in original.variables.items():
        if name != "CH4":
            np.testing.assert_array_equal(rewritten[name].to_numpy(), variable.to_numpy())


@pytest.mark.parametrize("data_model", ["NETCDF3_CLASSIC", "NETCDF4"])
def test_netcdf_format_survives(cmaq_file, data_model):
    """IOAPI reads whichever format CMAQ wrote, so the rewrite must not change it."""
    with xr.open_dataset(cmaq_file) as ds:
        contents = ds.load()
    contents.to_netcdf(cmaq_file, mode="w", format=data_model)

    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.0)

    with nc.Dataset(cmaq_file) as dataset:
        assert dataset.data_model == data_model


def test_the_scaling_is_recorded(cmaq_file):
    """An arm that read the wrong files is otherwise invisible in its output."""
    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.0)

    with xr.open_dataset(cmaq_file) as ds:
        assert ds.attrs[SCALE_ATTR] == 0.0
        assert ds.attrs[ANCHOR_ATTR] == ANCHOR


def test_a_second_application_is_refused(cmaq_file):
    """Scalings compound, so a repeat has to fail rather than silently apply."""
    scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.5)

    with pytest.raises(ValueError, match="already had its top gradient scaled"):
        scale_top_gradient([cmaq_file], anchor_layer=ANCHOR, scale=0.5)


def test_nothing_is_written_if_any_file_is_missing(cmaq_file, tmp_path):
    """All days or none: a profile that changes shape mid-run is not a perturbation."""
    with xr.open_dataset(cmaq_file) as ds:
        before = ds["CH4"].to_numpy()

    with pytest.raises(FileNotFoundError):
        scale_top_gradient([cmaq_file, tmp_path / "absent.nc"], anchor_layer=ANCHOR, scale=0.0)

    with xr.open_dataset(cmaq_file) as ds:
        np.testing.assert_array_equal(ds["CH4"].to_numpy(), before)
        assert SCALE_ATTR not in ds.attrs


def test_an_anchor_with_nothing_above_it_is_refused(cmaq_file):
    with xr.open_dataset(cmaq_file) as ds:
        top = ds.sizes[LAYER_DIM] - 1

    with pytest.raises(ValueError, match="leaves nothing above it"):
        scale_top_gradient([cmaq_file], anchor_layer=top, scale=0.0)
