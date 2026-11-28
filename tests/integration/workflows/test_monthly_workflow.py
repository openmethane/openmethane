"""Run the monthly workflow for au-test over 2022-12-07, then check its result.

The steps after the prior in scripts/docker-e2e-monthly.sh, configured as
there: CMAQ preprocessing without MCIP or ICON/BCON, the CAMS bias correction
and the inversion, reading a daily run's output. The CAMS download is left out.
Every output is written under the test's temporary folder.

Needs the adjoint program, so it only runs in the openmethane image. Each step
runs as its own process, as in production, because several of the scripts do
their work when imported.
"""

# Runs our own scripts with fixed arguments
# ruff: noqa: S603
import shutil
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

# Every test in this module runs the adjoint
pytestmark = [pytest.mark.adjoint, pytest.mark.slow]


@pytest.fixture
def daily_output(tmp_path, daily_run_data) -> None:
    """
    Lay out a daily run's output for 2022-12-07 where the monthly workflow
    reads it, under `STORE_PATH` (`tmp_path / "store"`).

    MCIP and the observations come from the `daily_run` test data. ICON and
    BCON are the profile templates, since that holds no ICON or BCON made from
    CAMS.
    """
    day = tmp_path / "store" / "au-test" / "daily" / "2022" / "12" / "07"
    shutil.copytree(daily_run_data / "mcip" / "2022-12-07", day / "mcip" / "2022-12-07")
    ctm_day = day / "cmaq" / "2022-12-07" / "d01"
    ctm_day.mkdir(parents=True)
    # Copied, because the bias correction edits them in place
    shutil.copy(
        daily_run_data / "cmaq" / "template_icon_profile_CH4only_d01.nc",
        ctm_day / "ICON.d01.au-test_v1.CH4only.nc",
    )
    shutil.copy(
        daily_run_data / "cmaq" / "template_bcon_profile_CH4only_d01.nc",
        ctm_day / "BCON.d01.au-test_v1.CH4only.nc",
    )
    (day / "input").mkdir()
    shutil.copy(
        daily_run_data / "obs" / "test_obs_2022-12-07.pic.gz", day / "input" / "test_obs.pic.gz"
    )


def test_inverts_the_daily_run(au_test_config, daily_output, tmp_path, root_dir):
    store = tmp_path / "store"
    daily = store / "au-test" / "daily"
    ctm_day = daily / "<YYYY>" / "<MM>" / "<DD>" / "cmaq" / "<YYYY-MM-DD>" / "d01"
    # The paths .env.docker-monthly sets, under this test's STORE_PATH
    au_test_config(
        FORCE_UPDATE="false",
        OBS_FILE_GLOB=daily / "*" / "*" / "*" / "input" / "test_obs.pic.gz",
        MET_DIR=daily / "<YYYY>" / "<MM>" / "<DD>" / "mcip",
        CTM_DIR=daily / "<YYYY>" / "<MM>" / "<DD>" / "cmaq",
        TEMPLATE_DIR=None,
        ICON_FILE=ctm_day / "ICON.d01.au-test_v1.CH4only.nc",
        BCON_FILE=ctm_day / "BCON.d01.au-test_v1.CH4only.nc",
        # One MPI rank, because the rank count changes the model's output
        NUM_PROC_COLS="1",
        NUM_PROC_ROWS="1",
    )
    scripts = root_dir / "scripts"
    # Bias correction writes a scratch file to the working directory
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # cmaq_preprocess-run: run-cmaq-preprocess.sh with SKIP_CMAQ_SETUP, without
    # the CAMS download
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "make_emis_template.py"],
        cwd=work_dir,
        check=True,
    )
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "make_template.py"],
        cwd=work_dir,
        check=True,
    )
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "make_prior.py"],
        cwd=work_dir,
        check=True,
    )
    # cmaq_preprocess-bias_correct
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "bias_correct_cams.py"],
        cwd=work_dir,
        check=True,
    )
    # fourdvar-monthly
    subprocess.run([sys.executable, root_dir / "runscript.py"], cwd=work_dir, check=True)

    results = store / "archive" / "openmethane-latest"
    assert (results / "posterior-emissions.nc").is_file()
    multipliers = xr.open_dataset(results / "posterior-multipliers.nc", group="emis")["CH4"]
    assert np.isfinite(multipliers).all()
    # Negative emissions aren't allowed by default
    assert (multipliers >= 0).all()
    # The prior is all ones, so the inversion moved something
    assert (multipliers != 1).any()
