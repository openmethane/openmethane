"""Compare the output of two WRF runs, file by file.

Used to show that the WRF step's output is unchanged: against setup-wrf for
the port, and against itself for changes meant to be neutral. Every difference
is reported by file, and by variable or attribute within a file.

Values are compared exactly, with NaN equal to NaN: WRF is deterministic for
the same binary, inputs, namelist and MPI rank count.
"""

import fnmatch
import pathlib
from collections.abc import Iterable

import f90nml
import netCDF4
import numpy

NAMELISTS = ("namelist.wps", "namelist.input")
NAMELIST_IGNORED = {"geog_data_path"}
"""Namelist settings that depend on where a run was, not what it did"""

LOG_PATTERNS = ("*.log", "*.log.*", "rsl.*", "logs/*", "real-rsl/*")
"""Files that differ between runs by name or content without the output differing"""

GLOBAL_ATTRIBUTES_IGNORED = {"history"}
"""Global attributes that record when a file was made"""


def relative_files(root: pathlib.Path) -> set[str]:
    """Every file under a folder, as paths relative to it. Links count as files."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def is_log(relative_path: str) -> bool:
    """Whether a file is a log, whose name and content aren't compared."""
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in LOG_PATTERNS) or any(
        fnmatch.fnmatch(pathlib.PurePosixPath(relative_path).name, pattern)
        for pattern in LOG_PATTERNS
    )


def compare_namelists(ours: pathlib.Path, theirs: pathlib.Path) -> list[str]:
    """Settings that differ between two namelists, parsed, ignoring `NAMELIST_IGNORED`."""
    mine, other = f90nml.read(ours).todict(), f90nml.read(theirs).todict()
    differences = []
    for group in sorted(set(mine) | set(other)):
        a, b = mine.get(group, {}), other.get(group, {})
        for key in sorted(set(a) | set(b)):
            if key.startswith("_") or key in NAMELIST_IGNORED:
                continue
            if a.get(key) != b.get(key):
                differences.append(f"{group}.{key}: {a.get(key)!r} != {b.get(key)!r}")
    return differences


def _equal(a, b) -> bool:
    if isinstance(a, numpy.ndarray) or isinstance(b, numpy.ndarray):
        a, b = numpy.asarray(a), numpy.asarray(b)
        if a.shape != b.shape or a.dtype != b.dtype:
            return False
        if a.dtype.kind in "fc":
            return bool(numpy.array_equal(a, b, equal_nan=True))
        return bool(numpy.array_equal(a, b))
    return a == b


def compare_netcdf(ours: pathlib.Path, theirs: pathlib.Path) -> list[str]:
    """
    Differences between two netCDF files.

    Compares the file format, dimensions, global attributes (except
    `GLOBAL_ATTRIBUTES_IGNORED`), and for every variable its dtype,
    dimensions, attributes, compression settings and values.
    """
    differences = []
    with netCDF4.Dataset(ours) as a, netCDF4.Dataset(theirs) as b:
        if a.data_model != b.data_model:
            differences.append(f"format: {a.data_model} != {b.data_model}")

        dims_a = {name: (len(dim), dim.isunlimited()) for name, dim in a.dimensions.items()}
        dims_b = {name: (len(dim), dim.isunlimited()) for name, dim in b.dimensions.items()}
        if dims_a != dims_b:
            differences.append(f"dimensions: {dims_a} != {dims_b}")

        for name in sorted((set(a.ncattrs()) | set(b.ncattrs())) - GLOBAL_ATTRIBUTES_IGNORED):
            value_a = a.getncattr(name) if name in a.ncattrs() else None
            value_b = b.getncattr(name) if name in b.ncattrs() else None
            if not _equal(value_a, value_b):
                differences.append(f"global attribute {name}: {value_a!r} != {value_b!r}")

        for name in sorted(set(a.variables) | set(b.variables)):
            if name not in a.variables or name not in b.variables:
                differences.append(
                    f"variable {name}: only in {'ours' if name in a.variables else 'theirs'}"
                )
                continue
            differences.extend(_compare_variable(name, a.variables[name], b.variables[name]))
    return differences


def _compare_variable(name: str, a: netCDF4.Variable, b: netCDF4.Variable) -> list[str]:
    differences = []
    if a.dtype != b.dtype:
        differences.append(f"variable {name} dtype: {a.dtype} != {b.dtype}")
    if a.dimensions != b.dimensions:
        differences.append(f"variable {name} dimensions: {a.dimensions} != {b.dimensions}")
    if a.filters() != b.filters():
        differences.append(f"variable {name} compression: {a.filters()} != {b.filters()}")
    for attribute in sorted(set(a.ncattrs()) | set(b.ncattrs())):
        value_a = a.getncattr(attribute) if attribute in a.ncattrs() else None
        value_b = b.getncattr(attribute) if attribute in b.ncattrs() else None
        if not _equal(value_a, value_b):
            differences.append(f"variable {name} attribute {attribute}: {value_a!r} != {value_b!r}")
    if a.shape == b.shape and a.dtype == b.dtype:
        a.set_auto_mask(False)
        b.set_auto_mask(False)
        values_a, values_b = a[:], b[:]
        if not _equal(numpy.asarray(values_a), numpy.asarray(values_b)):
            differing = numpy.count_nonzero(
                ~((values_a == values_b) | (numpy.isnan(values_a) & numpy.isnan(values_b)))
                if values_a.dtype.kind in "fc"
                else values_a != values_b
            )
            differences.append(f"variable {name} values: {differing} of {values_a.size} differ")
    return differences


def compare_runs(
    ours: pathlib.Path, theirs: pathlib.Path, ignore: Iterable[str] = ()
) -> dict[str, list[str]]:
    """
    Compare two WRF output folders.

    Parameters
    ----------
    ours, theirs
        The two output folders, such as `${STORE_PATH}/wrf/au-test`.
    ignore
        Glob patterns of relative paths to leave out, beyond logs.

    Returns
    -------
    For each relative path with a difference, the differences. "(layout)"
    holds files present in only one folder. Empty when the runs match.
    """
    ignore = tuple(ignore)

    def kept(paths: set[str]) -> set[str]:
        return {
            path
            for path in paths
            if not is_log(path) and not any(fnmatch.fnmatch(path, pattern) for pattern in ignore)
        }

    files_ours, files_theirs = kept(relative_files(ours)), kept(relative_files(theirs))
    report = {}
    layout = [f"only in ours: {path}" for path in sorted(files_ours - files_theirs)]
    layout += [f"only in theirs: {path}" for path in sorted(files_theirs - files_ours)]
    if layout:
        report["(layout)"] = layout

    for path in sorted(files_ours & files_theirs):
        a, b = ours / path, theirs / path
        if pathlib.PurePosixPath(path).name in NAMELISTS:
            differences = compare_namelists(a, b)
        elif path.endswith(".nc"):
            differences = compare_netcdf(a, b)
        else:
            differences = [] if a.read_bytes() == b.read_bytes() else ["contents differ"]
        if differences:
            report[path] = differences
    return report
