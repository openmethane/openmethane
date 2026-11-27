"""Run every stage after WRF for au-test on 2022-12-07, then check the result.

Needs the MCIP, ICON, BCON and adjoint programs, so it only runs in the
openmethane image, and takes several minutes, most of it in the inversion.

Each stage runs as its own process, as in production, because several of the
scripts do their work when imported and read their configuration then. Inputs
come from `tests/test-data` and `data/`, so nothing is downloaded; every output
is written under the test's temporary folder.
"""

# Runs our own scripts with fixed arguments
# ruff: noqa: S603
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

# Every test in this module runs the CMAQ programs and the adjoint
pytestmark = [pytest.mark.cmaq, pytest.mark.adjoint, pytest.mark.slow]


def test_inverts_the_reference_day(au_test_config, tmp_path, root_dir, test_data_dir):
    store = tmp_path / "store"
    ctm_day = store / "cmaq" / "2022-12-07" / "d01"
    # Laid out as in production, so CMAQ reads the boundary conditions made
    # from CAMS and bias corrected below, rather than the profile templates
    au_test_config(
        MET_DIR=store / "mcip",
        CTM_DIR=store / "cmaq",
        TEMPLATE_DIR=store / "templates",
        ICON_FILE=ctm_day / "ICON.d01.au-test_v1.CH4only.nc",
        BCON_FILE=ctm_day / "BCON.d01.au-test_v1.CH4only.nc",
        # One MPI rank, because the rank count changes the model's output
        NUM_PROC_COLS="1",
        NUM_PROC_ROWS="1",
    )
    tropomi = test_data_dir / "tropomi" / "2022-12-07*" / "*.nc4"
    scripts = root_dir / "scripts"
    # Bias correction writes a scratch file to the working directory
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # The stages of scripts/run-all.sh, without the CAMS and TropOMI downloads
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "setup_for_cmaq.py"],
        cwd=work_dir,
        check=True,
    )
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
    subprocess.run(
        [
            sys.executable,
            scripts / "obs_preprocess" / "tropomi_methane_preprocess.py",
            "--source",
            tropomi,
        ],
        cwd=work_dir,
        check=True,
    )
    subprocess.run(
        [sys.executable, scripts / "cmaq_preprocess" / "bias_correct_cams.py"],
        cwd=work_dir,
        check=True,
    )
    subprocess.run([sys.executable, root_dir / "runscript.py"], cwd=work_dir, check=True)

    results = store / "archive" / "openmethane-latest"
    assert (results / "posterior-emissions.nc").is_file()
    multipliers = xr.open_dataset(results / "posterior-multipliers.nc", group="emis")["CH4"]
    assert np.isfinite(multipliers).all()
    # Negative emissions aren't allowed by default
    assert (multipliers >= 0).all()
    # The prior is all ones, so the inversion moved something
    assert (multipliers != 1).any()
