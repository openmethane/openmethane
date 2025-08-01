import pytest
from scripts.cmaq_preprocess.make_emis_template import make_emissions_templates


@pytest.fixture
def emission_template(test_data_dir, tmpdir, metcro3d_file):
    data_dir = tmpdir.mkdir("data")

    emis_template = str(data_dir / "emis_record_<YYYY-MM-DD>.nc")
    make_emissions_templates(
        prior_file=str(test_data_dir / "prior" / "prior-emissions.nc"),
        metcro_template=metcro3d_file,
        emis_template=emis_template,
    )

    yield emis_template
