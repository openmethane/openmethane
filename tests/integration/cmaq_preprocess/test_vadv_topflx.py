"""The model-top flux diagnostic has to stay off unless it is asked for.

The inversion makes many forward runs per iteration, so a diagnostic that wrote
a file on each of them would cost storage on every production run. ADJOINT_FWD
only writes the gridded file when CTM_VADV_TOPFLX is in its environment, so
leaving the variable out is what turns it off.
"""

import os
import pathlib

import pytest

import openmethane.fourdvar.util.date_handle as dt
from openmethane.fourdvar.params import cmaq_config, date_defn
from openmethane.fourdvar.util import cmaq_handle

pytestmark = pytest.mark.skipif(
    not os.path.isfile(cmaq_config.fwd_prog),
    reason=f"ADJOINT_FWD not available at {cmaq_config.fwd_prog}",
)


def test_the_diagnostic_is_off_by_default(target_environment):
    target_environment("docker")

    assert cmaq_config.write_vadv_topflx is False


def test_the_model_is_not_told_where_to_write_it_when_off(monkeypatch):
    monkeypatch.setattr(cmaq_config, "write_vadv_topflx", False)

    assert "CTM_VADV_TOPFLX" not in cmaq_handle.setup_run()


def test_the_model_is_given_the_path_when_on(monkeypatch):
    monkeypatch.setattr(cmaq_config, "write_vadv_topflx", True)

    assert cmaq_handle.setup_run()["CTM_VADV_TOPFLX"] == (
        cmaq_config.vadv_topflx_file + " -v"
    )


def test_the_diagnostic_survives_a_forward_wipeout():
    """_cleanup wildcards the date, so listing the path would take every day.

    The driver also wipes forward output on its way out, which would leave
    nothing on disk to collect once a run finished.
    """
    assert cmaq_config.vadv_topflx_file not in cmaq_config.wipeout_fwd_list


@pytest.fixture
def forward_pass(tmp_path, monkeypatch):
    """Run forward days against temporary paths, with the model itself stubbed."""
    monkeypatch.setattr(cmaq_config, "write_vadv_topflx", True)
    monkeypatch.setattr(
        cmaq_config, "vadv_topflx_file", str(tmp_path / "VADV_TOPFLX.<YYYYMMDD>.nc")
    )
    monkeypatch.setattr(cmaq_config, "fwd_logfile", str(tmp_path / "fwd.<YYYYMMDD>.log"))
    monkeypatch.setattr(cmaq_config, "vadv_topflx_path", str(tmp_path / "vadv-topflx"))

    def write_output(date):
        """Stand in for what ADJOINT_FWD leaves behind for one day."""
        pathlib.Path(dt.replace_date(cmaq_config.vadv_topflx_file, date)).write_text(
            f"flux for {date}"
        )
        pathlib.Path(dt.replace_date(cmaq_config.fwd_logfile, date)).write_text(
            "     Some ordinary CMAQ chatter\n"
            " VADVTOP 2022341 000000 CH4      up  1.0E+00 dn  2.0E+00 net -1.0E+00 kg/s\n"
            " VADVFLX 2022341 000000 CH4      UP kg/s  0.0000E+00\n"
            "     More chatter\n"
        )

    monkeypatch.setattr(
        cmaq_handle, "run_cmaq", lambda *args, **kwargs: write_output(kwargs["date"])
    )
    return tmp_path


def test_a_stale_file_is_cleared_before_the_day_that_rewrites_it(forward_pass, monkeypatch):
    """Left in place, IO/API would reopen it for update rather than rewrite it."""
    date = date_defn.start_date
    stale = pathlib.Path(dt.replace_date(cmaq_config.vadv_topflx_file, date))
    stale.write_text("what a crashed earlier attempt left behind")

    write_output = cmaq_handle.run_cmaq
    seen = {}

    def observe(*args, **kwargs):
        seen["present_when_the_model_started"] = stale.exists()
        return write_output(*args, **kwargs)

    monkeypatch.setattr(cmaq_handle, "run_cmaq", observe)
    cmaq_handle.run_fwd_single(date, is_first=True)

    assert seen["present_when_the_model_started"] is False


def test_each_forward_pass_keeps_its_own_diagnostics(forward_pass):
    """An inversion runs a forward pass per line search evaluation.

    The flux under a trial control vector says as much about what the optimiser
    is doing as the flux under whichever vector the search tried last.
    """
    date = date_defn.start_date
    cmaq_handle.run_fwd_single(date, is_first=True)
    cmaq_handle.run_fwd_single(date, is_first=True)

    kept = sorted(p.name for p in (forward_pass / "vadv-topflx").iterdir())
    assert len(kept) == 2, f"one directory per forward pass, got {kept}"

    for pass_dir in (forward_pass / "vadv-topflx").iterdir():
        assert (pass_dir / f"VADV_TOPFLX.{date:%Y%m%d}.nc").is_file()


def test_only_the_flux_records_are_taken_from_the_log(forward_pass):
    """wipeout_fwd deletes the forward log, and the rest of it is far larger."""
    date = date_defn.start_date
    cmaq_handle.run_fwd_single(date, is_first=True)

    kept = next((forward_pass / "vadv-topflx").iterdir()) / f"vadv_flux.fwd.{date:%Y%m%d}.log"
    lines = kept.read_text().splitlines()

    assert len(lines) == 2
    assert all("VADV" in line for line in lines)
