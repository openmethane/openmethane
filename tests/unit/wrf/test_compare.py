import netCDF4
import numpy

from openmethane.wrf.compare import compare_namelists, compare_netcdf, compare_runs, is_log


def write_netcdf(path, values, units="K", title="WRF", zlib=False) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.setncattr("TITLE", title)
        dataset.setncattr("history", f"made at {path}")
        dataset.createDimension("x", len(values))
        variable = dataset.createVariable("T2", "f4", ("x",), zlib=zlib)
        variable.units = units
        variable[:] = numpy.array(values, dtype="f4")


def test_identical_files_have_no_differences(tmp_path):
    write_netcdf(tmp_path / "a.nc", [1.0, numpy.nan])
    write_netcdf(tmp_path / "b.nc", [1.0, numpy.nan])

    # NaN is equal to NaN, and the history attribute is ignored
    assert compare_netcdf(tmp_path / "a.nc", tmp_path / "b.nc") == []


def test_reports_values_attributes_and_compression(tmp_path):
    write_netcdf(tmp_path / "a.nc", [1.0, 2.0, 3.0])
    write_netcdf(tmp_path / "b.nc", [1.0, 2.5, 3.5], units="C", title="Other", zlib=True)

    differences = compare_netcdf(tmp_path / "a.nc", tmp_path / "b.nc")

    assert "global attribute TITLE: 'WRF' != 'Other'" in differences
    assert "variable T2 attribute units: 'K' != 'C'" in differences
    assert "variable T2 values: 2 of 3 differ" in differences
    assert any(difference.startswith("variable T2 compression") for difference in differences)


def test_namelists_compare_parsed_and_ignore_geog_data_path(tmp_path):
    (tmp_path / "a").write_text("&geogrid\n e_we = 15, geog_data_path = '/a'\n/\n")
    (tmp_path / "b").write_text("&geogrid\n  geog_data_path='/b'\n  e_we=15\n/\n")
    (tmp_path / "c").write_text("&geogrid\n e_we = 16\n/\n")

    assert compare_namelists(tmp_path / "a", tmp_path / "b") == []
    assert compare_namelists(tmp_path / "a", tmp_path / "c") == ["geogrid.e_we: 15 != 16"]


def test_logs_are_not_compared():
    assert is_log("2022120700/logs/wrf.log")
    assert is_log("2022120700/rsl.out.0000")
    assert is_log("2022120700/real.log.stdout")
    assert not is_log("2022120700/WRFOUT_d01_2022-12-07T0000Z.nc")


def test_compares_two_output_folders(tmp_path):
    for run in ("ours", "theirs"):
        (tmp_path / run / "2022120700").mkdir(parents=True)
        write_netcdf(tmp_path / run / "2022120700" / "WRFOUT_d01.nc", [1.0])
        (tmp_path / run / "2022120700" / f"{run}.log").write_text(run)
    write_netcdf(tmp_path / "theirs" / "2022120700" / "WRFOUT_d02.nc", [1.0])
    (tmp_path / "theirs" / "main.sh").write_text("#!/bin/bash")

    report = compare_runs(tmp_path / "ours", tmp_path / "theirs", ignore=["main.sh"])

    assert report == {"(layout)": ["only in theirs: 2022120700/WRFOUT_d02.nc"]}
