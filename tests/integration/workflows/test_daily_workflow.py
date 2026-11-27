"""Run the daily workflow for au-test on 2022-12-07, then check its result.

The steps after WRF and the prior in scripts/docker-e2e-daily.sh, configured as
there: CMAQ preprocessing, TropOMI preprocessing and the daily forward run. The
TropOMI and CAMS downloads are left out; their inputs come from
`tests/test-data` and `data/`. Every output is written under the test's
temporary folder.

Needs the MCIP, ICON, BCON and adjoint programs, so it only runs in the
openmethane image. Each step runs as its own process, as in production,
because several of the scripts do their work when imported.
"""

# Runs our own scripts with fixed arguments
# ruff: noqa: S603
import subprocess
import sys

import numpy as np
import pytest

from openmethane.fourdvar.util.file_handle import load_list

# Every test in this module runs the CMAQ programs and the adjoint
pytestmark = [pytest.mark.cmaq, pytest.mark.adjoint, pytest.mark.slow]


def test_simulates_the_days_observations(au_test_config, tmp_path, root_dir, test_data_dir):
    store = tmp_path / "store"
    ctm_day = store / "cmaq" / "<YYYY-MM-DD>" / "d01"
    # The paths .env.docker sets, under this test's STORE_PATH
    au_test_config(
        MET_DIR=store / "mcip",
        CTM_DIR=store / "cmaq",
        TEMPLATE_DIR=None,
        ICON_FILE=ctm_day / "ICON.d01.au-test_v1.CH4only.nc",
        BCON_FILE=ctm_day / "BCON.d01.au-test_v1.CH4only.nc",
        # One MPI rank, because the rank count changes the model's output
        NUM_PROC_COLS="1",
        NUM_PROC_ROWS="1",
    )
    tropomi = test_data_dir / "tropomi" / "2022-12-07*" / "*.nc4"
    scripts = root_dir / "scripts"
    # Run outside the checkout, so nothing can be written to it
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # cmaq_preprocess-run: run-cmaq-preprocess.sh, without the CAMS download
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
    # obs_preprocess-process_tropomi
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
    # fourdvar-daily
    subprocess.run(
        [sys.executable, scripts / "fourdvar" / "run_daily_step.py"],
        cwd=work_dir,
        check=True,
    )

    observed = load_list(store / "input" / "test_obs.pic.gz")
    simulated = load_list(store / "simulobs.pic.gz")
    # The first item of each is the domain
    assert len(observed) > 1
    assert len(simulated) == len(observed)
    assert all(np.isfinite(obs["value"]) for obs in simulated[1:])
