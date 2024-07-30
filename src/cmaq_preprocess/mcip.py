"""Run MCIP from python

TODO: Update verify and update docstring
The set-up provided assumes that the WRF model output will be in one
file per simulation (rather than one file per hour, or per six hours),
which reflects the sample WRF model output provided in preparation for
this project. If the user decides to split the WRF model output in
other ways, then this section of the code will need to be modified.

The procedure underlying the Python function that runs MCIP is
described in pseudo-code as follows:

for date in dates:
  for domain in domains:
      Extract the subset of data for this day using ncks
      Modify global attributes as necessary
      Write MCIP run script based on the template
      Run MCIP
      Check whether MCIP finished correctly
      if MCIP failed:
          Abort
      endif
      Compress to netCDF4 using ncks
  endfor
endfor
"""

import datetime
import glob
import os
import pathlib
from shutil import copyfile

from cmaq_preprocess.read_config_cmaq import Domain
from cmaq_preprocess.utils import compress_nc_file, nested_dir, replace_and_write, run_command


def to_wrf_filename(domain: str, time: datetime.datetime) -> str:
    return f'WRFOUT_{domain}_{time.strftime("%Y-%m-%dT%H%M")}Z.nc'


def run_mcip(
    dates,
    domain: Domain,
    met_dir: pathlib.Path,
    wrf_dir: pathlib.Path,
    geo_dir: pathlib.Path,
    mcip_executable_dir: pathlib.Path,
    scripts,
    compress_output=True,
    fix_simulation_start_date=True,
    fix_truelat2=False,
    truelat2=None,
    boundary_trim: int = 5,
):
    """Function to run MCIP from python

    Args:
        dates: array of dates to process
        domains: list of which domains should be run?
        met_dir: base directory for the MCIP output
        wrf_dir: directory containing wrfout_* files
        geo_dir: directory containing geo_em.* files
        mcip_executable_dir: directory containing the MCIP executable
        APPL: scenario tag (for MCIP). 16-character maximum. list: one per domain
        CoordName: Map projection name (for MCIP). 16-character maximum. list: one per domain
        GridName: Grid name (for MCIP). 16-character maximum. list: one per domain
        scripts: dictionary of scripts, including an entry with the key 'mcipRun'
        compress_output: True/False - compress output using ncks?
        fix_simulation_start_date: True/False - adjust the SIMULATION_START_DATE attribute in wrfout files?
        boundary_trim
            Number of meteorology "boundary" points to remove on each of four horizontal sides
            of the MCIP domain.

            See `templates/run.mcip` for a description of the `BTRIM` variable.

    Returns:
        Nothing

    """

    #########

    for idate, date in enumerate(dates):
        print("date =", date)
        yyyymmddhh = date.strftime("%Y%m%d%H")

        ##
        mcip_dir = nested_dir(domain, date, met_dir)
        os.makedirs(mcip_dir, exist_ok=True)
        ##
        times = [date + datetime.timedelta(hours=h) for h in range(25)]
        wrf_files = [
            os.path.join(wrf_dir, yyyymmddhh, to_wrf_filename(domain.id, time)) for time in times
        ]
        out_paths = [mcip_dir / os.path.basename(WRFfile) for WRFfile in wrf_files]
        for src, dst in zip(wrf_files, out_paths):
            if not os.path.exists(src):
                raise AssertionError(f"WRF output {src} not found")
            copyfile(src, dst)

        if fix_simulation_start_date:
            fix_wrf_start_dates(out_paths, date)

        if fix_truelat2 and (truelat2 is not None):
            fix_true_lat(out_paths, truelat2)

        ##
        print("\t\tCreate temporary run.mcip script")
        subs = [
            ["set DataPath   = TEMPLATE", f"set DataPath   = {mcip_dir}"],
            ["set InMetDir   = TEMPLATE", f"set InMetDir   = {mcip_dir}"],
            ["set OutDir     = TEMPLATE", f"set OutDir     = {mcip_dir}"],
            [
                "set InMetFiles = ( TEMPLATE )",
                "set InMetFiles = ( {} )".format(" ".join(out_paths)),
            ],
            [
                "set InTerFile  = TEMPLATE",
                f"set InTerFile  = {geo_dir}/geo_em.{domain.id}.nc",
            ],
            [
                "set MCIP_START = TEMPLATE",
                "set MCIP_START = {}:00:00.0000".format(date.strftime("%Y-%m-%d-%H")),
            ],
            [
                "set MCIP_END   = TEMPLATE",
                "set MCIP_END   = {}:00:00.0000".format(times[-1].strftime("%Y-%m-%d-%H")),
            ],
            [
                "set INTVL      = TEMPLATE",
                f"set INTVL      = {60}",
            ],
            ["set APPL       = TEMPLATE", f"set APPL       = {domain.scenario_tag}"],
            [
                "set CoordName  = TEMPLATE",
                f"set CoordName  = {domain.map_projection}",
            ],
            [
                "set GridName   = TEMPLATE",
                f"set GridName   = {domain.name}",
            ],
            ["set ProgDir    = TEMPLATE", f"set ProgDir    = {mcip_executable_dir}"],
            ["set BTRIM = TEMPLATE", f"set BTRIM = {boundary_trim}"],
        ]
        ##
        tmpRunMcipPath = f"{mcip_dir}/run.mcip.{domain.id}.csh"
        replace_and_write(
            lines=scripts["mcipRun"]["lines"],
            outfile=tmpRunMcipPath,
            substitutions=subs,
            strict=False,
            makeExecutable=True,
        )

        command = tmpRunMcipPath
        command_list = command.split(" ")
        print("\t\t\t" + command)
        ## delete any existing files
        for metfile in glob.glob(f"{mcip_dir}/MET*"):
            print("rm", metfile)
            os.remove(metfile)

        for gridfile in glob.glob(f"{mcip_dir}/GRID*"):
            print("rm", gridfile)
            os.remove(gridfile)

        print("\t\tRun temporary run.mcip script")
        stdout, stderr = run_command(command_list, verbose=True)
        if stdout.split("\n")[-2] != "NORMAL TERMINATION":
            raise RuntimeError("Error from run.mcip ...")
        ##

        for outPath in out_paths:
            os.unlink(outPath)
        if compress_output:
            files_to_compress = glob.glob(os.path.join(mcip_dir, "MET*_*")) + glob.glob(
                os.path.join(mcip_dir, "GRID*_*")
            )

            for fname in files_to_compress:
                compress_nc_file(fname)


def fix_true_lat(out_paths, truelat2):
    print("\t\tFix up TRUELAT2 attribute with ncatted")
    for outPath in out_paths:
        command = f"ncatted -O -a TRUELAT2,global,m,f,{truelat2} {outPath} {outPath}"
        print("\t\t\t" + command)
        command_list = command.split(" ")
        ##
        stdout, stderr = run_command(command_list, verbose=False)
        if len(stderr) > 0:
            print("stdout = " + stdout)
            print("stderr = " + stderr)
            raise RuntimeError("Error from ncatted...")


def fix_wrf_start_dates(out_paths, date):
    print("\t\tFix up SIMULATION_START_DATE attribute with ncatted")
    wrf_start_time = date.strftime("%Y-%m-%d_%H:%M:%S")
    for outPath in out_paths:
        command = (
            f"ncatted -O -a SIMULATION_START_DATE,global,m,c,"
            f"{wrf_start_time} {outPath} {outPath}"
        )
        print("\t\t\t" + command)
        command_list = command.split(" ")

        stdout, stderr = run_command(command_list, verbose=False)
        if len(stderr) > 0:
            print("stdout = " + stdout)
            print("stderr = " + stderr)
            raise RuntimeError("Error from ncatted...")
