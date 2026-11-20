import datetime
import pathlib

import attrs
import netCDF4
import pytest

from openmethane.util.process import ProgramFailed
from openmethane.wrf import pipeline
from openmethane.wrf.outputs import day_folder, expected_files

DAY = datetime.date(2022, 12, 7)
EVERY_PROGRAM = ["link_grib.csh", "ungrib.exe", "metgrid.exe", "real.exe", "wrf.exe"]


def stub_calls(tmp_path: pathlib.Path) -> list[str]:
    """The stub programs run so far, in order, leaving out mpirun, which runs the models."""
    calls = tmp_path / "calls.log"
    return (
        [call for call in calls.read_text().split() if call != "mpirun"] if calls.exists() else []
    )


def complete_output(config) -> pathlib.Path:
    """Fill the output folder with a complete day of (empty) averaged files."""
    folder = day_folder(config.output_path, DAY)
    folder.mkdir(parents=True)
    for name in expected_files(config.domains, DAY):
        (folder / name).touch()
    return folder


def test_a_run_publishes_a_complete_day(stub_config, tmp_path):
    ran = pipeline.run(stub_config)

    assert ran
    assert stub_calls(tmp_path) == EVERY_PROGRAM
    folder = day_folder(stub_config.output_path, DAY)
    assert sorted(path.name for path in folder.glob("WRFOUT_*")) == sorted(
        expected_files(stub_config.domains, DAY)
    )
    assert not list(folder.glob("wrfout_*"))
    assert (folder / "namelist.wps").exists()
    assert (folder / "namelist.input").exists()
    assert (folder / "logs" / "wrf.log").exists()
    assert (folder / "real-rsl" / "rsl.out.0000").exists()
    assert (stub_config.output_path / "geo_em.d01.nc").exists()
    assert len(list((stub_config.output_path / "metem").glob("met_em.d01.*.nc"))) == 7
    assert not stub_config.scratch_path.exists()


def test_each_hour_is_averaged_and_the_last_is_one_frame(stub_config):
    pipeline.run(stub_config)

    folder = day_folder(stub_config.output_path, DAY)
    with netCDF4.Dataset(folder / "WRFOUT_d01_2022-12-07T0100Z.nc") as hour:
        # The stub writes 0..47 over 12 frames of 2x2 cells
        assert hour.variables["T2"][0, 0, 0] == pytest.approx(22.0)
        assert b"".join(hour.variables["Times"][0]).decode() == "2022-12-07_01:00:00"
    with netCDF4.Dataset(folder / "WRFOUT_d01_2022-12-08T0000Z.nc") as last:
        assert last.variables["T2"][0, 0, 0] == 0.0


def test_a_complete_day_exits_early(stub_config, tmp_path):
    complete_output(stub_config)

    ran = pipeline.run(stub_config)

    assert not ran
    assert stub_calls(tmp_path) == []


def test_force_runs_a_complete_day_again(stub_config, tmp_path):
    complete_output(stub_config)
    config = attrs.evolve(stub_config, force=True)

    ran = pipeline.run(config)

    assert ran
    assert stub_calls(tmp_path) == EVERY_PROGRAM


def test_a_day_missing_one_file_runs_again(stub_config, tmp_path):
    folder = complete_output(stub_config)
    (folder / "WRFOUT_d01_2022-12-07T1300Z.nc").unlink()

    ran = pipeline.run(stub_config)

    assert ran
    assert (folder / "WRFOUT_d01_2022-12-07T1300Z.nc").exists()


def test_a_day_with_raw_output_left_runs_again(stub_config, tmp_path):
    folder = complete_output(stub_config)
    (folder / "wrfout_d01_2022-12-07_13:00:00").touch()

    ran = pipeline.run(stub_config)

    assert ran
    assert stub_calls(tmp_path) == EVERY_PROGRAM


def test_a_failure_publishes_logs_and_met_em_but_no_output(stub_config, monkeypatch):
    monkeypatch.setenv("STUB_FAIL", "wrf.exe")

    with pytest.raises(ProgramFailed, match="wrf.exe exited with code 1"):
        pipeline.run(stub_config)

    folder = day_folder(stub_config.output_path, DAY)
    assert (folder / "logs" / "wrf.log").read_text() == "wrf.exe failed on request\n"
    assert not list(folder.glob("WRFOUT_*"))
    assert not list(folder.glob("wrf*_d01*"))
    assert len(list((stub_config.output_path / "metem").glob("met_em.*.nc"))) == 7
    # Scratch is kept, so a retry can reuse it
    assert stub_config.scratch_path.is_dir()


def test_a_retry_reuses_met_em_and_real_output(stub_config, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_FAIL", "wrf.exe")
    with pytest.raises(ProgramFailed):
        pipeline.run(stub_config)
    monkeypatch.delenv("STUB_FAIL")
    before = len(stub_calls(tmp_path))

    pipeline.run(stub_config)

    assert stub_calls(tmp_path)[before:] == ["wrf.exe"]


def test_a_retry_on_a_new_host_reuses_published_met_em(stub_config, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_FAIL", "real.exe")
    with pytest.raises(ProgramFailed):
        pipeline.run(stub_config)
    monkeypatch.delenv("STUB_FAIL")
    # A new host starts with an empty scratch, apart from the geo_em it downloads
    for path in sorted(stub_config.scratch_path.rglob("*"), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    (stub_config.scratch_path / "geo_em.d01.nc").touch()
    before = len(stub_calls(tmp_path))

    pipeline.run(stub_config)

    assert stub_calls(tmp_path)[before:] == ["real.exe", "wrf.exe"]


def test_fnl_analyses_already_cached_are_not_fetched(stub_config, monkeypatch):
    fetched = []
    monkeypatch.setattr(
        "openmethane.util.download.download",
        lambda url, dest, *, session: fetched.append(url),
    )

    pipeline.run(stub_config)

    assert fetched == []


def test_a_missing_success_line_fails_even_with_exit_code_0(stub_config, monkeypatch):
    real = stub_config.install.real_exe
    real.write_text(real.read_text().replace("SUCCESS COMPLETE REAL_EM INIT", "FATAL"))

    with pytest.raises(ProgramFailed, match="did not print 'SUCCESS COMPLETE REAL_EM INIT'"):
        pipeline.run(stub_config)


def test_restart_files_are_removed(stub_config, monkeypatch):
    # Stop before publishing, to look in the working folder
    monkeypatch.setattr(pipeline, "publish", lambda *args, **kwargs: None)

    pipeline.run(stub_config)

    assert not list(stub_config.scratch_path.glob("*/wrfrst*"))
