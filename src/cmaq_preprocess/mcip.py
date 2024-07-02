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

import netCDF4

from cmaq_preprocess.utils import replace_and_write


def to_wrf_filename(domain: str, time: datetime.datetime) -> str:
    return f'WRFOUT_{domain}_{time.strftime("%Y-%m-%dT%H%M")}Z.nc'


def run_mcip(
    dates,
    domains,
    metDir,
    wrfDir,
    geoDir,
    ProgDir,
    APPL,
    CoordName,
    GridName,
    scripts,
    compressWithNco=True,
    fix_simulation_start_date=True,
    fix_truelat2=False,
    truelat2=None,
    wrfRunName=None,
    doArchiveWrf=False,
    add_qsnow=False,
):
    """Function to run MCIP from python

    Args:
        dates: array of dates to process
        domains: list of which domains should be run?
        metDir: base directory for the MCIP output
        wrfDir: directory containing wrfout_* files
        geoDir: directory containing geo_em.* files
        ProgDir: directory containing the MCIP executable
        APPL: scenario tag (for MCIP). 16-character maximum. list: one per domain
        CoordName: Map projection name (for MCIP). 16-character maximum. list: one per domain
        GridName: Grid name (for MCIP). 16-character maximum. list: one per domain
        scripts: dictionary of scripts, including an entry with the key 'mcipRun'
        compressWithNco: True/False - compress output using ncks?
        fix_simulation_start_date: True/False - adjust the SIMULATION_START_DATE attribute in wrfout files?

    Returns:
        Nothing

    """

    #########

    tmpfl = tempfile.mktemp(suffix=".tar")
    cwd = os.getcwd()

    ndoms = len(domains)
    nMinsPerInterval = [60] * ndoms

    if not os.path.exists(metDir):
        os.mkdir(metDir)
    ##
    for idate, date in enumerate(dates):
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        ##
        parent_mcipdir = f"{metDir}/{yyyymmdd_dashed}"
        ## create output destination
        if not os.path.exists(parent_mcipdir):
            os.mkdir(parent_mcipdir)
        for idomain, domain in enumerate(domains):
            mcipDir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
            ## create output destination
            if not os.path.exists(mcipDir):
                os.mkdir(mcipDir)

    for idate, date in enumerate(dates):
        print("date =", date)
        yyyymmddhh = date.strftime("%Y%m%d%H")
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        for idom, dom in enumerate(domains):
            print("\tdom =", dom)
            ##
            mcipDir = f"{metDir}/{yyyymmdd_dashed}/{dom}"
            ##
            times = [date + datetime.timedelta(hours=h) for h in range(25)]
            WRFfiles = [
                os.path.join(wrfDir, yyyymmddhh, to_wrf_filename(dom, time)) for time in times
            ]
            outPaths = [f"{mcipDir}/{os.path.basename(WRFfile)}" for WRFfile in WRFfiles]
            for src, dst in zip(WRFfiles, outPaths):
                if not os.path.exists(src):
                    raise AssertionError(f"WRF output {src} not found")
                copyfile(src, dst)
                ## print 1. # WRF files =',len([f for f in os.listdir(mcipDir) if f.startswith('wrfout_')])

            if fix_simulation_start_date:
                print("\t\tFix up SIMULATION_START_DATE attribute with ncatted")
                wrfstrttime = date.strftime("%Y-%m-%d_%H:%M:%S")
                for outPath in outPaths:
                    command = f"ncatted -O -a SIMULATION_START_DATE,global,m,c,{wrfstrttime} {outPath} {outPath}"
                    print("\t\t\t" + command)
                    commandList = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from atted...")

            if add_qsnow:
                print("\t\tAdd an artificial variable ('QSNOW') to the WRFOUT files")
                wrfstrttime = date.strftime("%Y-%m-%d_%H:%M:%S")
                for outPath in outPaths:
                    nc = netCDF4.Dataset(outPath, "a")
                    nc.createVariable(
                        "QSNOW",
                        "f4",
                        ("Time", "bottom_top", "south_north", "west_east"),
                        zlib=True,
                    )
                    nc.variables["QSNOW"][:] = 0.0
                    nc.close()

            if fix_truelat2 and (truelat2 is not None):
                print("\t\tFix up TRUELAT2 attribute with ncatted")
                for outPath in outPaths:
                    command = f"ncatted -O -a TRUELAT2,global,m,f,{truelat2} {outPath} {outPath}"
                    print("\t\t\t" + command)
                    commandList = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + stdout)
                        print("stderr = " + stderr)
                        raise RuntimeError("Error from atted...")
                    ## print '3. # WRF files =',len([f for f in os.listdir(mcipDir) if f.startswith('wrfout_')])

            ##
            print("\t\tCreate temporary run.mcip script")
            ## pdb.set_trace()
            # {}/{}'.format(wrfDir,date.strftime('%Y%m%d%H'))---by Sougol
            subs = [
                ["set DataPath   = TEMPLATE", f"set DataPath   = {mcipDir}"],
                ["set InMetDir   = TEMPLATE", f"set InMetDir   = {mcipDir}"],
                ["set OutDir     = TEMPLATE", f"set OutDir     = {mcipDir}"],
                [
                    "set InMetFiles = ( TEMPLATE )",
                    "set InMetFiles = ( {} )".format(" ".join(outPaths)),
                ],
                [
                    "set InTerFile  = TEMPLATE",
                    f"set InTerFile  = {geoDir}/geo_em.{dom}.nc",
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
                    f"set INTVL      = {int(round(nMinsPerInterval[idom]))}",
                ],
                ["set APPL       = TEMPLATE", f"set APPL       = {APPL[idom]}"],
                [
                    "set CoordName  = TEMPLATE",
                    f"set CoordName  = {CoordName[idom]}",
                ],
                [
                    "set GridName   = TEMPLATE",
                    f"set GridName   = {GridName[idom]}",
                ],
                ["set ProgDir    = TEMPLATE", f"set ProgDir    = {ProgDir}"],
            ]
            ##
            tmpRunMcipPath = f"{mcipDir}/run.mcip.{dom}.csh"
            replace_and_write(
                lines=scripts["mcipRun"]["lines"],
                out_file=tmpRunMcipPath,
                substitutions=subs,
                strict=False,
                make_executable=True,
            )
            ##
            ## print '4. # WRF files =',len([f for f in os.listdir(mcipDir) if f.startswith('wrfout_')])
            command = tmpRunMcipPath
            commandList = command.split(" ")
            print("\t\t\t" + command)
            ## delete any existing files
            for metfile in glob.glob(f"{mcipDir}/MET*"):
                print("rm", metfile)
                os.remove(metfile)

            for gridfile in glob.glob(f"{mcipDir}/GRID*"):
                print("rm", gridfile)
                os.remove(gridfile)

            ## print '5. # WRF files =',len([f for f in os.listdir(mcipDir) if f.startswith('wrfout_')])
            ##
            print("\t\tRun temporary run.mcip script")
            p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if stdout.split(b"\n")[-2] != b"NORMAL TERMINATION":
                print("stdout = " + str(stdout.decode()))
                print("stderr = " + str(stderr.decode()))
                raise RuntimeError("Error from run.mcip ...")
            ##

            for outPath in outPaths:
                os.unlink(outPath)
            if compressWithNco:
                for metfile in glob.glob(f"{mcipDir}/MET*_*"):
                    print(f"\t\tCompress {metfile} with ncks")
                    command = f"ncks -4 -L4 -O {metfile} {metfile}"
                    print("\t\t\t" + command)
                    commandList = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from ncks...")

                for gridfile in glob.glob(f"{mcipDir}/GRID*_*"):
                    print(f"\t\tCompress {gridfile} with ncks")
                    command = f"ncks -4 -L4 -O {gridfile} {gridfile}"
                    print("\t\t\t" + command)
                    commandList = command.split(" ")
                    ##
                    p = subprocess.Popen(
                        commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = p.communicate()
                    if len(stderr) > 0:
                        print("stdout = " + str(stdout))
                        print("stderr = " + str(stderr))
                        raise RuntimeError("Error from ncks...")

            if doArchiveWrf and (wrfRunName is not None) and False:
                print(f"\t\tChecking MCIP output in folder {mcipDir}")
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
                    matches = glob.glob(f"{mcipDir}/{filetype}_*")
                    if len(matches) != 1:
                        raise RuntimeError(f"{filetype} file not found in folder {mcipDir} ... ")
                ##
                thisWRFdir = f"{wrfDir}/{yyyymmddhh}"
                os.chdir(thisWRFdir)
                ##
                wrfouts = glob.glob(f"WRFOUT_{dom}_*")
                ##
                command = "tar -cvf {} {}".format(tmpfl, " ".join(wrfouts))
                print("\t\t\t" + command)
                commandList = command.split(" ")
                p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = p.communicate()
                if len(stderr) > 0:
                    print("stdout = " + stdout)
                    print("stderr = " + stderr)
                    raise RuntimeError("Error from tar...")
                ##
                command = f"mdss mkdir ns0890/data/WRF/{wrfRunName}/"
                print("\t\t\t" + command)
                commandList = command.split(" ")
                p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = p.communicate()
                if len(stderr) > 0:
                    print("stdout = " + stdout)
                    print("stderr = " + stderr)
                    raise RuntimeError("Error from mdss...")
                ##
                command = (
                    f"mdss put {tmpfl} ns0890/data/WRF/{wrfRunName}/WRFOUT_{yyyymmddhh}_{dom}.tar"
                )
                print("\t\t\t" + command)
                commandList = command.split(" ")
                p = subprocess.Popen(commandList, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = p.communicate()
                if len(stderr) > 0:
                    print("stdout = " + stdout)
                    print("stderr = " + stderr)
                    raise RuntimeError("Error from mdss...")
                ##
                command = f"rm -f {tmpfl}"
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
                ##
                os.chdir(cwd)
