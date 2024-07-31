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
    dates: list[datetime.date],
    domain: Domain,
    met_dir: pathlib.Path,
    wrf_dir: pathlib.Path,
    geo_dir: pathlib.Path,
    mcip_source_dir: pathlib.Path,
    scripts,
    compress_output: bool = True,
    fix_simulation_start_date: bool = True,
    truelat2: float | None = None,
    boundary_trim: int = 5,
):
    """
    Run MCIP from python

    MCIP extracts the meteorology data from WRF
    and processes it into a format that can be read by CMAQ.

    Args:
        dates: array of dates to process
        domain: Domain of interest
        met_dir: base directory for the MCIP output
        wrf_dir: directory containing wrfout_* files
        geo_dir: directory containing geo_em.* files
        mcip_source_dir: directory containing the MCIP executable
        scripts: dictionary of scripts, including an entry with the key 'mcipRun'
        compress_output: Compress output using ncks?
        fix_simulation_start_date:  Adjust the SIMULATION_START_DATE attribute in wrfout files?
        truelat2: If not None, modify the value of truelat2 in the WRF output
            TODO: JL: Check if this is needed anymore
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
        times: list[datetime.datetime] = [
            datetime.datetime(date.year, date.month, date.day) + datetime.timedelta(hours=h)
            for h in range(25)
        ]
        wrf_files = [
            os.path.join(wrf_dir, yyyymmddhh, to_wrf_filename(domain.id, time)) for time in times
        ]

        # This has to be of type list[str] because of how it is used in the substitution
        out_paths = [str(mcip_dir / os.path.basename(WRFfile)) for WRFfile in wrf_files]

        if len(out_paths) == 0:
            raise FileNotFoundError(f"No WRF output found in {wrf_dir / yyyymmddhh}")

        for src, dst in zip(wrf_files, out_paths):
            if not os.path.exists(src):
                raise AssertionError(f"WRF output {src} not found")
            copyfile(src, dst)

        if fix_simulation_start_date:
            fix_wrf_start_dates(out_paths, date)

        if truelat2 is not None:
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
            ["set APPL       = TEMPLATE", f"set APPL       = {domain.mcip_suffix}"],
            [
                "set CoordName  = TEMPLATE",
                f"set CoordName  = {domain.map_projection}",
            ],
            [
                "set GridName   = TEMPLATE",
                f"set GridName   = {domain.mcip_suffix}",
            ],
            ["set ProgDir    = TEMPLATE", f"set ProgDir    = {mcip_source_dir}"],
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
        try:
            stdout, stderr = run_command(command_list, verbose=True)
            if stdout.split("\n")[-2] != "NORMAL TERMINATION":
                raise RuntimeError("Error from run.mcip ...")
        except Exception:
            with open(tmpRunMcipPath) as fh:
                print(fh.read())
            raise
        ##

        for outPath in out_paths:
            os.unlink(outPath)
        if compress_output:
            files_to_compress = glob.glob(os.path.join(mcip_dir, "MET*_*")) + glob.glob(
                os.path.join(mcip_dir, "GRID*_*")
            )

            for fname in files_to_compress:
                compress_nc_file(fname)


def fix_true_lat(out_paths: list[str], truelat2: float):
    print("\t\tFix up TRUELAT2 attribute with ncatted")
    for outPath in out_paths:
        command = f"ncatted -O -a TRUELAT2,global,m,f,{truelat2} {outPath} {outPath}"
        command_list = command.split(" ")
        ##
        stdout, stderr = run_command(command_list, verbose=True)
        if len(stderr) > 0:
            raise RuntimeError("Error from ncatted...")


def fix_wrf_start_dates(out_paths: list[str], date: datetime.date):
    print("\t\tFix up SIMULATION_START_DATE attribute with ncatted")
    wrf_start_time = date.strftime("%Y-%m-%d_%H:%M:%S")
    for outPath in out_paths:
        command = (
            f"ncatted -O -a SIMULATION_START_DATE,global,m,c,"
            f"{wrf_start_time} {outPath} {outPath}"
        )
        command_list = command.split(" ")

        stdout, stderr = run_command(command_list, verbose=True)
        if len(stderr) > 0:
            raise RuntimeError("Error from ncatted...")
