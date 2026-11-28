import xarray as xr

from openmethane.util.cf import get_grid_mappings


def test_cf_get_grid_mappings(daily_run_data):
    prior_file = str(daily_run_data / "prior" / "prior-emissions.nc")
    prior_ds = xr.open_dataset(prior_file)

    grid_mappings = get_grid_mappings(prior_ds)

    assert grid_mappings == ["lambert_conformal"]
