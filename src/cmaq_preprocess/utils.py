"""Utility functions used by a number of different functions"""

import copy
import datetime
import os
import pathlib
import subprocess

import numpy

from cmaq_preprocess.read_config_cmaq import Domain
from fourdvar.util import date_handle


def deg2rad(deg):
    """
    Convert degrees to radians

    Args:
        deg: a number in degrees (may be a numpy array)

    Returns:
        rad: the corresponding value in radians

    """
    return deg * numpy.pi / 180.0


def get_distance_from_lat_lon_in_km(lat1, lon1, lat2, lon2):
    """Calculate the distance between points based on the latitudes and longitudes

    Distances between multiple pairs of points can be calculated, so
    long as point 1 is a one value and point 2 is given as
    equally-sized numpy arrays of latitudes and longitudes.

    Args:
        lat1: latitude of point 1
        lon1: longitude of point 1
        lat2: latitude of point(s) 2
        lon2: longitude of point(s) 2

    Returns:
        d: distance(s) between point 1 and point(s) 2

    """

    R = 6371.0  ## Radius of the earth in km
    dLat = deg2rad(lat2 - lat1)  ## deg2rad below
    dLon = deg2rad(lon2 - lon1)
    a = numpy.sin(dLat / 2) * numpy.sin(dLat / 2) + numpy.cos(deg2rad(lat1)) * numpy.cos(
        deg2rad(lat2)
    ) * numpy.sin(dLon / 2) * numpy.sin(dLon / 2)
    c = 2.0 * numpy.arctan2(numpy.sqrt(a), numpy.sqrt(1 - a))
    d = R * c  ## Distance in km
    return d


def compress_nc_file(filename: str | pathlib.Path, ppc: int | None = None) -> None:
    """Compress a netCDF3 file to netCDF4 using ncks

    Args:
        filename: Path to the netCDF3 file to compress
        ppc: number of significant digits to retain (default is to retain all)

    Returns:
        Nothing
    """

    if not os.path.exists(filename):
        raise RuntimeError(f"File {filename} not found...")

    print(f"Compress file {filename} with ncks")
    command = f"ncks -4 -L4 -O {filename} {filename}"
    print("\t" + command)
    command_list = command.split(" ")
    if ppc is not None:
        if not isinstance(ppc, int):
            raise RuntimeError("Argument ppc should be an integer...")
        elif ppc < 1 or ppc > 6:
            raise RuntimeError("Argument ppc should be between 1 and 6...")
        else:
            ppcText = f"--ppc default={ppc}"
            command_list = [command_list[0]] + ppcText.split(" ") + command_list[1:]

    stdout, stderr = run_command(command_list)
    if len(stderr) > 0 or len(stdout) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from ncks...")


def load_scripts(scripts):
    """Read the contents (i.e. the lines of text) of a set of scripts into a dictionary

    Args:
        scripts: A dictionary of dictionaries, with the inner level containing the key 'path'

    Returns:
        scripts: A dictionary of dictionaries,
            with the inner level containing the keys 'path' and 'lines'
            (giving their file path and lines of text, respectively)
    """
    scripts = copy.copy(scripts)
    ## for each of the scripts, read in the contents
    for k in list(scripts.keys()):
        ## check that the script is found
        if not os.path.exists(scripts[k]["path"]):
            raise RuntimeError(
                "Template run script {} not found at {} ... ".format(k, scripts[k]["path"])
            )
        with open(scripts[k]["path"]) as fh:
            scripts[k]["lines"] = fh.readlines()
    ##
    return scripts


def replace_and_write(lines, outfile, substitutions, strict=True, makeExecutable=False):
    """Make a set of substitutions from a list of strings and write to file

    Args:
        lines: List of strings
        outfile: Place to write the destination
        substitutions: List of substitutions
        strict: Boolean, if True, it will cause an error if substitutions don't mattch exactly once
        makeExecutable: Make the output script an executable

    Returns:
        Nothing
    """
    Lines = copy.copy(lines)
    for subst in substitutions:
        token = subst[0]
        replc = subst[1]
        matches = [iline for iline, line in enumerate(Lines) if line.find(token) != -1]
        nmatches = len(matches)
        if (nmatches == 1) or (nmatches > 0 and (not strict)):
            for iline in matches:
                ## Lines[iline] = re.sub(token, replc, Lines[iline])
                Lines[iline] = Lines[iline].replace(token, replc)
        elif strict:
            raise ValueError("Token '%s' matches %i times..." % (token, nmatches))
    if os.path.exists(outfile):
        os.remove(outfile)
    f = open(outfile, "w")
    for line in Lines:
        f.write(line)
    f.close()
    if makeExecutable:
        os.chmod(outfile, 0o0744)


def run_command(
    command_list: list[str], log_prefix: str | None = None, verbose: bool = False
) -> tuple[str, str]:
    if verbose:
        print("Running command: " + " ".join(command_list))

    p = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    stdout = stdout.decode()
    stderr = stderr.decode()

    if log_prefix:
        with open(f"{log_prefix}.stdout", "w") as f:
            f.write(stdout)
        with open(f"{log_prefix}.stderr", "w") as f:
            f.write(stderr)

    if verbose:
        print(f"Exited with: {p.returncode} ")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")

    return stdout, stderr


def nested_dir(domain: Domain, date: datetime.date, root_dir: pathlib.Path) -> pathlib.Path:
    """
    Get the nested directory for a given domain and date

    Parameters
    ----------
    domain
        Domain of interest
    date
        Date of interest
    root_dir
        Root directory for the nested directory.

        This can contain the date formatting strings used in the `fourdvar` package.

    See Also
    --------
    fourdvar.util.date_handle.replace_date
    Returns
    -------
        Nested path inside root_dir

    """

    # TODO: This whole functions should be replaced with a replace_date
    # and move the nested logic to the configuration
    templated_path = root_dir / "<YYYY-MM-DD>" / domain.id
    return pathlib.Path(date_handle.replace_date(str(templated_path), date))
