import datetime

import netCDF4
import pytest

from openmethane.util.process import ProgramFailed
from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.install import WrfInstall
from openmethane.wrf.model import (
    _check_rsl,
    link_run_files,
    metgrid_levels,
    real_outputs,
)
from openmethane.wrf.wps import met_em_name, missing_met_em, needed_met_em

TIMES = [datetime.datetime(2022, 12, 7, 0), datetime.datetime(2022, 12, 7, 6)]


def test_met_em_names():
    assert met_em_name("d01", TIMES[1]) == "met_em.d01.2022-12-07_06:00:00.nc"


def test_needed_met_em_covers_every_time_for_every_domain():
    names = needed_met_em(DomainSet.load([("au-test", "v1")]), TIMES)

    assert names == ["met_em.d01.2022-12-07_00:00:00.nc", "met_em.d01.2022-12-07_06:00:00.nc"]


def test_missing_met_em_lists_only_those_not_cached(tmp_path):
    (tmp_path / "met_em.d01.2022-12-07_00:00:00.nc").touch()

    missing = missing_met_em(tmp_path, DomainSet.load([("au-test", "v1")]), TIMES)

    assert missing == ["met_em.d01.2022-12-07_06:00:00.nc"]


def test_reads_the_level_counts_from_met_em(tmp_path):
    with netCDF4.Dataset(tmp_path / "met_em.nc", "w") as met_em:
        met_em.createDimension("num_metgrid_levels", 34)
        met_em.createDimension("num_st_layers", 4)

    assert metgrid_levels(tmp_path / "met_em.nc") == (34, 4)


def test_real_outputs_are_boundaries_once_and_inputs_per_domain(tmp_path):
    outputs = real_outputs(tmp_path, DomainSet.load([("au-test", "v1")]))

    assert [path.name for path in outputs] == ["wrfbdy_d01", "wrfinput_d01", "wrflowinp_d01"]


def test_links_wrf_data_files_but_not_the_example_namelist(tmp_path):
    run_dir = tmp_path / "wrf" / "run"
    run_dir.mkdir(parents=True)
    for name in ("RRTMG_LW_DATA", "LANDUSE.TBL", "ozone.formatted", "co2_trans", "namelist.input"):
        (run_dir / name).touch()
    window = tmp_path / "window"
    window.mkdir()

    link_run_files(window, WrfInstall(wrf_dir=tmp_path / "wrf", wps_dir=tmp_path / "wps"))

    assert sorted(path.name for path in window.iterdir()) == [
        "LANDUSE.TBL",
        "RRTMG_LW_DATA",
        "co2_trans",
        "ozone.formatted",
    ]


def test_a_missing_rsl_success_line_fails(tmp_path):
    (tmp_path / "rsl.out.0000").write_text("-------------- FATAL CALLED ---------------\n")

    with pytest.raises(ProgramFailed, match="real.exe exited with code 0 but did not print"):
        _check_rsl(tmp_path, "real.exe", "SUCCESS COMPLETE REAL_EM INIT", tmp_path / "real.log")


def test_a_missing_rsl_file_fails(tmp_path):
    with pytest.raises(ProgramFailed, match="wrf.exe"):
        _check_rsl(tmp_path, "wrf.exe", "SUCCESS COMPLETE WRF", tmp_path / "wrf.log")
