
from datatree import open_datatree
from scripts.cmaq_preprocess.make_prior import make_prior


def test_make_prior(test_data_dir, tmpdir, file_regression, emission_template):
    expected_file = tmpdir / "prior.nc"
    make_prior(save_path=str(expected_file), emis_template=emission_template)

    assert expected_file.exists()

    ds = open_datatree(expected_file)

    assert ds.groups == ('/', '/emis', '/bcon')

    assert ds["emis"].dims == {'TSTEP': 1, 'LAY': 1, 'ROW': 5, 'COL': 5}

    # TODO: Check if this makes sense
    assert ds["bcon"].dims == {'TSTEP': 0, 'BCON': 8}

    file_regression.check(open(expected_file, "rb").read(), binary=True, extension=".nc")
