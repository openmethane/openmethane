import os
from pathlib import Path

import pytest
import xarray as xr
from scripts.cmaq_preprocess import setup_for_cmaq

from openmethane.cmaq_preprocess.read_config_cmaq import load_config_from_env


@pytest.fixture
def wrf_run(root_dir):
    # Verify that WRF has been successfully run previously
    wrf_output_dir = Path(root_dir) / "tests" / "test-data" / "wrf" / "au-test" / "2022120700"

    try:
        assert (wrf_output_dir / "WRFOUT_d01_2022-12-07T0000Z.nc").exists()
        # Check that the 25th hour exists
        assert (wrf_output_dir / "WRFOUT_d01_2022-12-08T0000Z.nc").exists()
    except AssertionError:
        pytest.fail("WRF has not been run successfully. Failing test.")

    return wrf_output_dir


def _get_filelisting(directory: Path):
    return sorted([os.path.relpath(i, directory) for i in directory.rglob("*") if i.is_file()])


def _layer_profile(path: Path, variable: str = "CH4"):
    """Summarise a field layer by layer, in ppb

    `compare_dataset` captures a file's structure but none of its values, so the
    concentrations the CAMS to CMAQ interpolation produces need a fixture of
    their own. A per-layer summary is enough to show the shape of the profile
    and to make a change in the level mapping legible in the diff.
    """
    with xr.open_dataset(path) as ds:
        field = ds[variable].squeeze("TSTEP") * 1e3

    return {
        "layers": [
            {
                "layer": layer,
                "min": round(float(field.isel(LAY=layer).min()), 3),
                "mean": round(float(field.isel(LAY=layer).mean()), 3),
                "max": round(float(field.isel(LAY=layer).max()), 3),
            }
            for layer in range(field.sizes["LAY"])
        ]
    }


def test_setup_for_cmaq(
    tmpdir,
    root_dir,
    wrf_run,
    file_regression,
    request,
    data_regression,
    compare_dataset,
    target_environment,
):
    cmaq_dir = Path(tmpdir / "cmaq")
    mcip_dir = Path(tmpdir / "mcip")
    mcip_run_dir = mcip_dir / "2022-12-07" / "d01"

    # Override some settings
    target_environment("docker-test")
    config = load_config_from_env(
        met_dir=mcip_dir,
        ctm_dir=cmaq_dir,
        wrf_dir=wrf_run.parent,
    )

    # Run the CMAQ preprocessing scripts
    setup_for_cmaq.setup_for_cmaq(config)

    assert (cmaq_dir / "template_bcon_profile_CH4only_d01.nc").exists()
    assert (cmaq_dir / "template_icon_profile_CH4only_d01.nc").exists()

    assert (mcip_run_dir / "METCRO2D_au-test_v1").exists()
    assert (mcip_run_dir / "METCRO3D_au-test_v1").exists()

    # Compare the generated list of files
    data_regression.check(_get_filelisting(cmaq_dir), basename=f"{request.node.name}_cmaq_files")
    data_regression.check(_get_filelisting(mcip_dir), basename=f"{request.node.name}_mcip_files")

    # Check the grid definition
    file_regression.check(
        (mcip_run_dir / "GRIDDESC").read_text(),
        basename=f"{request.node.name}_griddesc",
    )

    # Run script regression.
    # The namelist embeds absolute paths that vary by run (pytest's tmpdir is
    # named after the current user) so they are replaced with placeholders.
    namelist = (
        (mcip_run_dir / "namelist.mcip")
        .read_text()
        .replace(str(tmpdir), "<tmpdir>")
        .replace(str(root_dir), "<root_dir>")
    )
    file_regression.check(
        namelist,
        basename=f"{request.node.name}_namelist",
    )

    # Compare the structure of a select set of files
    compare_dataset(
        cmaq_dir / "template_bcon_profile_CH4only_d01.nc",
        basename=f"{request.node.name}_bcon",
    )
    compare_dataset(
        cmaq_dir / "template_icon_profile_CH4only_d01.nc",
        basename=f"{request.node.name}_icon",
    )
    compare_dataset(
        mcip_run_dir / "METCRO3D_au-test_v1",
        basename=f"{request.node.name}_metcro3d",
    )

    # The concentrations interpolated from CAMS onto the CMAQ layers
    cams_dir = cmaq_dir / "2022-12-07" / "d01"
    data_regression.check(
        _layer_profile(cams_dir / "ICON.d01.au-test_v1.CH4only.nc"),
        basename=f"{request.node.name}_icon_profile",
    )
    data_regression.check(
        _layer_profile(cams_dir / "BCON.d01.au-test_v1.CH4only.nc"),
        basename=f"{request.node.name}_bcon_profile",
    )
