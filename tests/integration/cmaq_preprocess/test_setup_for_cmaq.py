import os
from pathlib import Path

import pytest
from scripts.cmaq_preprocess import setup_for_cmaq

from cmaq_preprocess.read_config_cmaq import load_cmaq_config


@pytest.fixture
def wrf_run(root_dir):
    # Verify that WRF has been successfully run previously
    wrf_output_dir = Path(root_dir) / "tests" / "test-data" / "wrf" / "aust-test" / "2022072200"

    try:
        assert (wrf_output_dir / "WRFOUT_d01_2022-07-22T0000Z.nc").exists()
        # Check that the 25th hour exists
        assert (wrf_output_dir / "WRFOUT_d01_2022-07-23T0000Z.nc").exists()
    except AssertionError:
        pytest.fail("WRF has not been run successfully. Failing test.")

    return wrf_output_dir


def _get_filelisting(directory: Path):
    return sorted([os.path.relpath(i, directory) for i in directory.rglob("*") if i.is_file()])


def test_setup_for_cmaq(
    tmpdir,
    root_dir,
    wrf_run,
    file_regression,
    request,
    data_regression,
    compare_dataset,
):
    config = load_cmaq_config(os.path.join(root_dir, "config/cmaq_preprocess/config.docker.json"))

    cmaq_dir = Path(tmpdir / "cmaq")
    mcip_dir = Path(tmpdir / "mcip")

    # Override some settings
    config.metDir = str(mcip_dir)
    config.ctmDir = str(cmaq_dir)
    config.wrfDir = str(wrf_run.parent)

    # Run the CMAQ preprocessing scripts
    setup_for_cmaq.main(config)

    assert (cmaq_dir / "template_bcon_profile_CH4only_d01.nc").exists()
    assert (cmaq_dir / "template_icon_profile_CH4only_d01.nc").exists()

    assert (mcip_dir / "2022-07-22" / "d01" / "METCRO2D_220701_aust-test").exists()
    assert (mcip_dir / "2022-07-22" / "d01" / "METCRO3D_220701_aust-test").exists()

    # Compare the generated list of files
    data_regression.check(_get_filelisting(cmaq_dir), basename=f"{request.node.name}_cmaq_files")
    data_regression.check(_get_filelisting(mcip_dir), basename=f"{request.node.name}_mcip_files")

    # Check the grid definition
    file_regression.check(
        open(mcip_dir / "2022-07-22" / "d01" / "GRIDDESC").read(),
        basename=f"{request.node.name}_griddesc",
    )

    # Compare the structure of a select set of files
    compare_dataset(
        cmaq_dir / "template_bcon_profile_CH4only_d01.nc",
        basename=f"{request.node.name}_bcon",
    )
    compare_dataset(
        mcip_dir / "2022-07-22" / "d01" / "METCRO3D_220701_aust-test",
        basename=f"{request.node.name}_metcro3d",
    )
