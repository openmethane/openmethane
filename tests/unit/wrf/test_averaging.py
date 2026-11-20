import datetime

import netCDF4
import numpy
import pytest

from openmethane.wrf.averaging import (
    AveragingError,
    average_file,
    average_window,
    parse_raw_name,
)

FIRST_KEPT = datetime.datetime(2022, 12, 7)
RUN_END = datetime.datetime(2022, 12, 8)


def write_raw(path, frames: int) -> None:
    """A raw WRF output file with a float, an integer and a constant variable."""
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as raw:
        raw.setncattr("TITLE", " OUTPUT FROM WRF V4.5.1 MODEL")
        raw.createDimension("Time", None)
        raw.createDimension("DateStrLen", 19)
        raw.createDimension("south_north", 2)
        raw.createDimension("west_east", 3)
        times = raw.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[:] = numpy.array([list("2022-12-07_13:00:00")] * frames, dtype="S1")
        temperature = raw.createVariable("T2", "f4", ("Time", "south_north", "west_east"))
        temperature.units = "K"
        temperature[:] = numpy.arange(frames * 6, dtype="f4").reshape(frames, 2, 3) + 280
        category = raw.createVariable("LU_INDEX", "i4", ("Time", "south_north", "west_east"))
        category[:] = numpy.full((frames, 2, 3), 7, dtype="i4")
        constant = raw.createVariable("ZNU", "f4", ("south_north",))
        constant[:] = [0.9, 0.5]


def test_parses_a_raw_file_name():
    assert parse_raw_name("wrfout_d02_2022-12-07_13:00:00") == (
        "d02",
        datetime.datetime(2022, 12, 7, 13),
    )


def test_rejects_other_file_names():
    with pytest.raises(AveragingError, match="Not a raw WRF output file"):
        parse_raw_name("wrfinput_d01_2022-12-07_13:00:00")


def test_averages_every_frame_into_one(tmp_path):
    write_raw(tmp_path / "raw", frames=12)

    average_file(tmp_path / "raw", tmp_path / "averaged.nc", "2022-12-07_13:00:00")

    with netCDF4.Dataset(tmp_path / "averaged.nc") as averaged:
        assert len(averaged.dimensions["Time"]) == 1
        assert averaged.TITLE == " OUTPUT FROM WRF V4.5.1 MODEL"
        expected = (numpy.arange(72, dtype="f4").reshape(12, 2, 3) + 280).mean(axis=0)
        numpy.testing.assert_array_equal(averaged.variables["T2"][0], expected)
        assert averaged.variables["T2"].units == "K"
        assert averaged.variables["LU_INDEX"][0, 0, 0] == 7
        numpy.testing.assert_array_equal(
            averaged.variables["ZNU"][:], numpy.array([0.9, 0.5], "f4")
        )
        assert b"".join(averaged.variables["Times"][0]).decode() == "2022-12-07_13:00:00"


def test_only_float32_variables_are_compressed(tmp_path):
    write_raw(tmp_path / "raw", frames=12)

    average_file(tmp_path / "raw", tmp_path / "averaged.nc", "2022-12-07_13:00:00")

    with netCDF4.Dataset(tmp_path / "averaged.nc") as averaged:
        assert averaged.data_model == "NETCDF4"
        assert averaged.variables["T2"].filters()["zlib"]
        assert not averaged.variables["LU_INDEX"].filters()["zlib"]


def test_averages_a_window_and_removes_the_raw_files(tmp_path):
    write_raw(tmp_path / "wrfout_d01_2022-12-07_13:00:00", frames=12)
    write_raw(tmp_path / "wrfout_d01_2022-12-08_00:00:00", frames=1)

    averaged = average_window(tmp_path, 12, FIRST_KEPT, RUN_END)

    assert [path.name for path in averaged] == [
        "WRFOUT_d01_2022-12-07T1300Z.nc",
        "WRFOUT_d01_2022-12-08T0000Z.nc",
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == [path.name for path in averaged]


def test_spin_up_files_are_removed_without_averaging(tmp_path):
    write_raw(tmp_path / "wrfout_d01_2022-12-06_23:00:00", frames=12)

    averaged = average_window(tmp_path, 12, FIRST_KEPT, RUN_END)

    assert averaged == []
    assert list(tmp_path.iterdir()) == []


def test_a_file_with_too_few_frames_means_wrf_stopped_early(tmp_path):
    write_raw(tmp_path / "wrfout_d01_2022-12-07_13:00:00", frames=7)

    with pytest.raises(AveragingError, match="has 7 frames, expected 12"):
        average_window(tmp_path, 12, FIRST_KEPT, RUN_END)

    # The raw file is kept for a look, and no averaged file appears
    assert [path.name for path in tmp_path.iterdir()] == ["wrfout_d01_2022-12-07_13:00:00"]
