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
import subprocess
import tempfile
from shutil import copyfile

from cmaq_preprocess.utils import replace_and_write


def to_wrf_filename(domain: str, time: datetime.datetime) -> str:
    return f'WRFOUT_{domain}_{time.strftime("%Y-%m-%dT%H%M")}Z.nc'


def run_mcip(
    dates: list[datetime.date],
    domains: list[str],
    met_dir,
    wrf_dir,
    geo_dir,
    mcip_executable_dir,
    scenario_tag: list[str],
    map_projection_name: list[str],
    grid_name: list[str],
    scripts,
    compress_with_nco=True,
    fix_simulation_start_date=True,
    wrf_run_name=None,
    do_archive_wrf=False,
):
    """Function to run MCIP from python

    Args:
        dates: array of dates to process
        domains: list of which domains should be run?
        met_dir: base directory for the MCIP output
        wrf_dir: directory containing wrfout_* files
        geo_dir: directory containing geo_em.* files
        mcip_executable_dir: directory containing the MCIP executable
        scenario_tag: scenario tag (for MCIP). 16-character maximum. list: one per domain
        map_projection_name: Map projection name (for MCIP). 16-character maximum. list: one per domain
        grid_name: Grid name (for MCIP). 16-character maximum. list: one per domain
        scripts: dictionary of scripts, including an entry with the key 'mcipRun'
        compress_with_nco: True/False - compress output using ncks?
        fix_simulation_start_date: True/False - adjust the SIMULATION_START_DATE attribute in wrfout files?

    Returns:
        Nothing

    """
    cwd = os.getcwd()

    ndoms = len(domains)
    n_mins_per_interval = [60] * ndoms

    for idate, date in enumerate(dates):
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        for idomain, domain in enumerate(domains):
            mcip_dir = os.path.join(met_dir, yyyymmdd_dashed, domain)
            os.makedirs(mcip_dir, exist_ok=True)

    for idate, date in enumerate(dates):
        print("date =", date)
        yyyymmddhh = date.strftime("%Y%m%d%H")
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        times = [date + datetime.timedelta(hours=h) for h in range(25)]

        for idom, dom in enumerate(domains):
            print("\tdom =", dom)
            mcip_dir = f"{met_dir}/{yyyymmdd_dashed}/{dom}"
            wrf_files = [
                os.path.join(wrf_dir, yyyymmddhh, to_wrf_filename(dom, time)) for time in times
            ]
            out_paths = [
                os.path.join(mcip_dir, os.path.basename(wrf_file)) for wrf_file in wrf_files
            ]
            for src, dst in zip(wrf_files, out_paths):
                if not os.path.exists(src):
                    raise AssertionError(f"WRF output {src} not found")
                copyfile(src, dst)

            if fix_simulation_start_date:
                print("\t\tFix up SIMULATION_START_DATE attribute with ncatted")
                wrfstrttime = date.strftime("%Y-%m-%d_%H:%M:%S")
                for outPath in out_paths:
                    command = f"ncatted -O -a SIMULATION_START_DATE,global,m,c,{wrfstrttime} {outPath} {outPath}"
                    print("\t\t\t" + command)
                    command_list = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from atted...")
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
                    f"set InTerFile  = {geo_dir}/geo_em.{dom}.nc",
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
                    f"set INTVL      = {int(round(n_mins_per_interval[idom]))}",
                ],
                ["set APPL       = TEMPLATE", f"set APPL       = {scenario_tag[idom]}"],
                [
                    "set CoordName  = TEMPLATE",
                    f"set CoordName  = {map_projection_name[idom]}",
                ],
                [
                    "set GridName   = TEMPLATE",
                    f"set GridName   = {grid_name[idom]}",
                ],
                ["set ProgDir    = TEMPLATE", f"set ProgDir    = {mcip_executable_dir}"],
            ]
            ##
            tmp_run_mcip_path = f"{mcip_dir}/run.mcip.{dom}.csh"
            replace_and_write(
                lines=scripts["mcipRun"]["lines"],
                out_file=tmp_run_mcip_path,
                substitutions=subs,
                strict=False,
                make_executable=True,
            )
            ##
            command = tmp_run_mcip_path
            command_list = command.split(" ")
            print("\t\t\t" + command)
            ## delete any existing files
            for metfile in glob.glob(f"{mcip_dir}/MET*"):
                print("rm", metfile)
                os.remove(metfile)
            for gridfile in glob.glob(f"{mcip_dir}/GRID*"):
                print("rm", gridfile)
                os.remove(gridfile)
            ##
            print("\t\tRun temporary run.mcip script")
            p = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if stdout.split(b"\n")[-2] != b"NORMAL TERMINATION":
                print("stdout = " + str(stdout.decode()))
                print("stderr = " + str(stderr.decode()))
                raise RuntimeError("Error from run.mcip ...")
            ##
            for outPath in out_paths:
                os.unlink(outPath)
            if compress_with_nco:
                for metfile in glob.glob(f"{mcip_dir}/MET*_*"):
                    print(f"\t\tCompress {metfile} with ncks")
                    command = f"ncks -4 -L4 -O {metfile} {metfile}"
                    print("\t\t\t" + command)
                    command_list = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from ncks...")

                for gridfile in glob.glob(f"{mcip_dir}/GRID*_*"):
                    print(f"\t\tCompress {gridfile} with ncks")
                    command = f"ncks -4 -L4 -O {gridfile} {gridfile}"
                    print("\t\t\t" + command)
                    command_list = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from ncks...")
            if do_archive_wrf and (wrf_run_name is not None) and False:
                os.chdir(f"{wrf_dir}/{yyyymmddhh}")

                archive_wrf(dom, mcip_dir, wrf_run_name, yyyymmddhh)

                os.chdir(cwd)


def archive_wrf(dom: str, mcip_dir: str, wrf_run_name: str, yyyymmddhh: str):
    """
    Archive WRF output files to MDSS

    TODO: This is unused and untested

    Parameters
    ----------
    dom
        Name of the domain that is being processed
    mcip_dir
        MCIP directory.

        Used to verify if the MCIP run succeeded
    wrf_run_name
        Name of the WRF run
    yyyymmddhh
        Current timestring
    """
    temp_file = tempfile.mkstemp(suffix=".tar")

    print(f"\t\tChecking MCIP output in folder {mcip_dir}")

    ## double check that all the files MCIP files are present before archiving the WRF files
    filetypes = [
        "GRIDBDY2D",
        "GRIDCRO2D",
        "GRIDDOT2D",
        "METBDY3D",
        "METCRO2D",
        "METCRO3D",
        "METDOT3D",
    ]
    for filetype in filetypes:
        matches = glob.glob(f"{mcip_dir}/{filetype}_*")
        if len(matches) != 1:
            raise RuntimeError(f"{filetype} file not found in folder {mcip_dir} ... ")
    ##

    ##
    wrfouts = glob.glob(f"WRFOUT_{dom}_*")
    ##
    command = "tar -cvf {} {}".format(temp_file, " ".join(wrfouts))
    print("\t\t\t" + command)
    commandList = command.split(" ")
    p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from tar...")
    ##
    command = f"mdss mkdir ns0890/data/WRF/{wrf_run_name}/"
    print("\t\t\t" + command)
    commandList = command.split(" ")
    p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from mdss...")
    ##
    command = f"mdss put {temp_file} ns0890/data/WRF/{wrf_run_name}/WRFOUT_{yyyymmddhh}_{dom}.tar"
    print("\t\t\t" + command)
    commandList = command.split(" ")
    p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from mdss...")
    ##
    command = f"rm -f {temp_file}"
    print("\t\t\t" + command)
    commandList = command.split(" ")
    p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from rm...")
    ##
    command = "rm {}".format(" ".join(wrfouts))
    print("\t\t\t" + command)
    commandList = command.split(" ")
    p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0:
        print("stdout = " + stdout)
        print("stderr = " + stderr)
        raise RuntimeError("Error from rm...")
