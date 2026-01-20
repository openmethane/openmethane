
import xarray as xr

from openmethane.util.cf import get_grid_mappings


def test_cf_get_grid_mappings(test_data_dir):
    prior_file = str(test_data_dir / "prior" / "prior-emissions.nc")
    prior_ds = xr.open_dataset(prior_file)

    grid_mappings = get_grid_mappings(prior_ds)

    assert grid_mappings == ["lambert_conformal"]
