from xarray import open_datatree
from scripts.cmaq_preprocess.make_prior import make_prior


def test_make_prior(test_data_dir, tmpdir, compare_dataset, emission_template):
    expected_file = tmpdir / "prior.nc"
    make_prior(save_path=str(expected_file), emis_template=emission_template)

    assert expected_file.exists()

    ds = open_datatree(expected_file)

    assert ds.groups == ("/", "/emis", "/bcon")

    assert ds["emis"].dims == {"TSTEP": 1, "LAY": 1, "ROW": 5, "COL": 5}

    assert ds["bcon"].dims == {"TSTEP": 1, "BCON": 8}

    compare_dataset(ds)
