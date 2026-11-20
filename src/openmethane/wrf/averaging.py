"""Average WRF's raw output to one time step per file.

WRF writes instantaneous values every 5 minutes, an hour per file. MCIP wants
hourly means, so each raw `wrfout_<dNN>_<time>` file becomes one
`WRFOUT_<dNN>_<time>Z.nc` holding the mean of its frames. The last file of a
run holds a single frame, so its "mean" is instantaneous.

The arithmetic is setup-wrf's `average_fields`, unchanged, because MCIP's
input must not change at the level of rounding.
"""

import datetime
import logging
import pathlib

import netCDF4
import numpy

from openmethane.wrf.outputs import averaged_file_name

logger = logging.getLogger(__name__)

WRF_TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"


class AveragingError(RuntimeError):
    """A raw output file can't be averaged."""


def parse_raw_name(name: str) -> tuple[str, datetime.datetime]:
    """
    The domain id and time of a raw output file, from its name.

    For example `wrfout_d01_2022-12-07_13:00:00` gives ("d01", 13:00 on 2022-12-07).
    """
    prefix, domain_id, time_text = name.split("_", 2)
    if prefix != "wrfout":
        raise AveragingError(f"Not a raw WRF output file: {name}")
    return domain_id, datetime.datetime.strptime(time_text, WRF_TIME_FORMAT)


def average_file(raw_path: pathlib.Path, averaged_path: pathlib.Path, time_text: str) -> None:
    """
    Write the mean over time of every variable in a raw output file.

    Variables without a Time dimension are copied. `float32` variables are
    compressed with zlib and no others, as setup-wrf did. `Times` is set to
    `time_text`, the start of the averaging period.
    """
    dimensions = {}
    variables = {}
    attributes = {}

    with netCDF4.Dataset(raw_path) as source:
        for name, dimension in source.dimensions.items():
            dimensions[name] = len(dimension)
        attributes["global"] = {key: source.getncattr(key) for key in source.ncattrs()}
        for name, variable in source.variables.items():
            variables[name] = {
                "dtype": variable.dtype,
                "dimensions": variable.dimensions,
                "fill_value": variable.getncattr("_FillValue")
                if "_FillValue" in variable.ncattrs()
                else None,
                "dimlens": numpy.array([dimensions[dim] for dim in variable.dimensions]),
            }
            attributes[name] = {key: variable.getncattr(key) for key in variable.ncattrs()}

        variables["Times"]["dimlens"][0] = 1
        dimensions["Time"] = 1

        average = {}
        for name, variable in variables.items():
            if name == "Times":
                continue
            time_axes = [axis for axis, dim in enumerate(variable["dimensions"]) if dim == "Time"]
            if not time_axes:
                average[name] = source.variables[name][:]
            elif len(time_axes) == 1:
                average[name] = source.variables[name][:].mean(axis=time_axes[0], keepdims=True)
            else:
                raise AveragingError(f"Variable {name} has more than one Time dimension")

    with netCDF4.Dataset(averaged_path, mode="w") as target:
        for name, size in dimensions.items():
            target.createDimension(name, size)
        target.setncatts(attributes["global"])
        for name, variable in variables.items():
            dtype = variable["dtype"].str[1:]
            target.createVariable(
                name,
                dtype,
                variable["dimensions"],
                zlib=dtype == "f4",
                fill_value=variable["fill_value"],
            )
            target.variables[name].setncatts(attributes[name])
            if name == "Times":
                target.variables[name][:] = numpy.array(list(time_text), dtype="|S1").reshape(
                    variable["dimlens"]
                )
            else:
                target.variables[name][:] = average[name]


def average_window(
    window_dir: pathlib.Path,
    frames_per_file: int,
    first_kept: datetime.datetime,
    run_end: datetime.datetime,
) -> list[pathlib.Path]:
    """
    Average every raw output file in a window's folder, and remove the raw files.

    Raw files from the spin-up, before `first_kept`, are removed unaveraged.
    `history_begin_h` normally stops WRF writing them.

    Each averaged file is written under a temporary name and renamed once
    complete, so an interrupted run never leaves an averaged file that looks
    finished. Its raw file is removed only after that.

    Parameters
    ----------
    window_dir
        The window's working folder.
    frames_per_file
        Frames WRF writes to each file, `frames_per_outfile` in the namelist.
    first_kept
        The window's first kept hour.
    run_end
        When the window's run ends. The file starting then holds one frame;
        every other file must hold `frames_per_file`.

    Returns
    -------
    The averaged files written.

    Raises
    ------
    AveragingError
        If a file has the wrong number of frames, which means wrf.exe stopped
        part way through.
    """
    averaged = []
    for raw_path in sorted(window_dir.glob("wrfout_*")):
        domain_id, time = parse_raw_name(raw_path.name)
        if time < first_kept:
            logger.info(f"removing {raw_path.name}, from the spin-up")
            raw_path.unlink()
            continue
        expected = 1 if time == run_end else frames_per_file
        with netCDF4.Dataset(raw_path) as raw:
            frames = len(raw.dimensions["Time"])
        if frames != expected:
            raise AveragingError(f"{raw_path.name} has {frames} frames, expected {expected}")

        averaged_path = window_dir / averaged_file_name(domain_id, time)
        partial = averaged_path.with_name(averaged_path.name + ".part")
        logger.info(f"averaging {raw_path.name} to {averaged_path.name}")
        average_file(raw_path, partial, time.strftime(WRF_TIME_FORMAT))
        partial.replace(averaged_path)
        raw_path.unlink()
        averaged.append(averaged_path)
    return averaged
