import numpy as np
from scripts.cmaq_preprocess.make_prior import make_prior
from xarray import open_datatree


def test_make_prior(test_data_dir, tmpdir, compare_dataset, emission_template):
    expected_file = tmpdir / "prior.nc"
    make_prior(save_path=str(expected_file), emis_template=emission_template)

    assert expected_file.exists()

    ds = open_datatree(expected_file)

    assert ds.groups == ("/", "/emis", "/bcon")

    assert ds["emis"].sizes == {"TSTEP": 1, "LAY": 1, "ROW": 10, "COL": 10}

    # the 10-cell test domain is shorter than a 1000 km segment, so one segment
    # per edge, by 4 equal-mass bands
    assert ds["bcon"].sizes == {"TSTEP": 1, "BCON": 16, "LAY": 32, "PERIM": 44}
    assert ds["bcon"].attrs["units"] == "ppm"
    assert (ds["bcon"]["CH4"] == 0).all()
    assert np.allclose(ds["bcon"]["CH4_UNC"], 0.02)

    compare_dataset(ds)
