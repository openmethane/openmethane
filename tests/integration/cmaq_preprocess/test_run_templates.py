from typing import Any

import xarray as xr
from scripts.cmaq_preprocess.make_emis_template import make_emissions_templates


def _squeeze_strs(values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in values.items():
        clean = value
        if isinstance(value, str):
            clean = value.strip()
        out[key] = clean
    return out


def test_make_emissions_templates(test_data_dir, tmpdir, compare_dataset, metcro3d_file):
    data_dir = tmpdir.mkdir("data")
    make_emissions_templates(
        prior_file=str(test_data_dir / "prior" / "prior-emissions.nc"),
        metcro_template=metcro3d_file,
        emis_template=str(data_dir / "emis_record_<YYYY-MM-DD>.nc"),
    )

    expected_file = data_dir / "emis_record_2022-07-22.nc"
    assert expected_file.exists()

    ds = xr.load_dataset(expected_file)

    assert ds.dims == {"TSTEP": 25, "VAR": 1, "DATE-TIME": 2, "LAY": 32, "ROW": 5, "COL": 5}
    assert list(ds.variables.keys()) == ["TFLAG", "CH4"]

    # Check TFLAG
    assert ds["TFLAG"].dims == ("TSTEP", "VAR", "DATE-TIME")
    # Check that times are set correctly
    # [integer of form YYYYDDD, HHMM]
    # Not sure who makes this up...
    assert (ds["TFLAG"].sel(TSTEP=0).values == [2022203, 0]).all()
    assert (ds["TFLAG"].sel(TSTEP=1).values == [2022203, 10000]).all()
    assert (ds["TFLAG"].sel(TSTEP=-1).values == [2022204, 0]).all()

    # Check Methane emissions
    assert ds["CH4"].dims == ("TSTEP", "LAY", "ROW", "COL")
    assert _squeeze_strs(ds["CH4"].attrs) == {
        "long_name": "CH4",
        "units": "mols/s",
        "var_desc": "Emissions of CH4",
    }

    assert ds["CH4"].sum()

    compare_dataset(ds)
