import pytest
from scripts.cmaq_preprocess.make_emis_template import make_emissions_templates


@pytest.fixture
def emission_template(test_data_dir, tmpdir):
    data_dir = tmpdir.mkdir("data")

    emis_template = str(data_dir / "emis_record_<YYYY-MM-DD>.nc")
    make_emissions_templates(
        prior_filename=str(test_data_dir / "prior" / "out-om-domain-info.nc"),
        metcro_template=str(
            test_data_dir / "mcip" / "2022-07-22" / "d01" / "METCRO3D_220701_aust-test"
        ),
        emis_template=emis_template,
    )

    yield emis_template
