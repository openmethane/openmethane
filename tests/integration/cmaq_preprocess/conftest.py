import pytest
from scripts.cmaq_preprocess.make_emis_template import make_emissions_templates


@pytest.fixture
def emission_template(daily_run_data, tmpdir, metcro3d_file, au_test_config):
    data_dir = tmpdir.mkdir("data")

    emis_template = str(data_dir / "emis_record_<YYYY-MM-DD>.nc")
    make_emissions_templates(
        prior_file=str(daily_run_data / "prior" / "prior-emissions.nc"),
        metcro_template=metcro3d_file,
        emis_template=emis_template,
    )

    yield emis_template
