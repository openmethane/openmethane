"""The forward model must produce the same concentrations without its checkpoints.

`cmaq_preprocess.bias.calculate_emissions_bias` suppresses the checkpoints to
avoid writing what nothing reads, which is only sound if CREATE_CHK does nothing
beyond skipping the writes.
"""

import os
import shutil

import numpy as np
import pytest
import xarray as xr

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.file_handle as fh
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.params import cmaq_config, date_defn, template_defn
from openmethane.fourdvar.util import cmaq_handle

pytestmark = pytest.mark.skipif(
    not os.path.isfile(cmaq_config.fwd_prog),
    reason=f"ADJOINT_FWD not available at {cmaq_config.fwd_prog}",
)

CHK_PARAMS = (
    "chem_chk",
    "vdiff_chk",
    "aero_chk",
    "ha_rhoj_chk",
    "va_rhoj_chk",
    "hadv_chk",
    "vadv_chk",
    "emis_chk",
    "emist_chk",
    "cpl_chk",
)


def checkpoint_files(date):
    """The checkpoint files ADJOINT_FWD has written for a date."""
    paths = [dt.replace_date(getattr(cmaq_config, param), date) for param in CHK_PARAMS]
    return sorted(os.path.basename(path) for path in paths if os.path.isfile(path))


def run_fwd_day(date):
    """Run one day of the forward model the way make_template.py does.

    Returns the CONC file, copied out of reach of `wipeout_fwd`, and the
    checkpoint files the run left behind.
    """
    emis_file = dt.replace_date(cmaq_config.emis_file, date)
    fh.ensure_path(os.path.dirname(emis_file))
    ncf.copy_compress(dt.replace_date(template_defn.emis, date), emis_file)

    conc_file = dt.replace_date(cmaq_config.conc_file, date)
    fh.ensure_path(os.path.dirname(conc_file))
    fh.ensure_path(cmaq_config.chk_path)

    cmaq_handle.wipeout_fwd()
    cmaq_handle.run_fwd_single(date, is_first=True)

    assert os.path.isfile(conc_file)
    return conc_file, checkpoint_files(date)


@pytest.fixture
def fwd_run(tmp_path, monkeypatch):
    """Run one forward day at a given CREATE_CHK setting."""

    def run(create_chk, name):
        monkeypatch.setattr(cmaq_config, "create_chk", create_chk)
        conc_file, written = run_fwd_day(date_defn.start_date)
        kept = tmp_path / f"conc_{name}.nc"
        shutil.copy(conc_file, kept)
        return kept, written

    yield run

    # a later forward run in this container would otherwise start from these
    cmaq_handle.wipeout_fwd()


def test_setup_run_passes_create_chk_to_the_model(monkeypatch):
    monkeypatch.setattr(cmaq_config, "create_chk", True)
    assert cmaq_handle.setup_run()["CREATE_CHK"] == "T"

    monkeypatch.setattr(cmaq_config, "create_chk", False)
    assert cmaq_handle.setup_run()["CREATE_CHK"] == "F"


def test_concentrations_are_unchanged_without_checkpoints(fwd_run):
    """The CONC field is what `transfunc.obs_operator` reads, so it has to match exactly."""
    with_chk_file, with_chk_written = fwd_run(True, "with_chk")
    without_chk_file, without_chk_written = fwd_run(False, "without_chk")

    # the flag has to have done something, or the comparison below is vacuous
    assert with_chk_written
    assert without_chk_written == []

    with xr.open_dataset(with_chk_file) as with_chk, xr.open_dataset(without_chk_file) as without:
        assert list(with_chk.variables) == list(without.variables)
        for name in with_chk.variables:
            # suppressing a write cannot perturb the science, so any
            # difference at all means CREATE_CHK does more than skip writes
            np.testing.assert_array_equal(
                with_chk[name].to_numpy(),
                without[name].to_numpy(),
                err_msg=f"{name} differs between the two runs",
            )
        assert with_chk["CH4"].to_numpy().any()
