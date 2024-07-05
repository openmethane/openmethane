"""Functions to check folders, files and attributes from MCIP output"""

import glob
import os
import warnings

import netCDF4
import numpy

from cmaq_preprocess.utils import getDistanceFromLatLonInKm


def checkInputMetAndOutputFolders(ctmDir, metDir, dates, domains):
    """
    Check that MCIP inputs are present, and create directories for CCTM input/output if need be

    Args:
        ctmDir: base directory for the CCTM inputs and outputs
        metDir: base directory for the MCIP output
        dates: list of datetime objects, one per date MCIP and CCTM output should be defined
        domains: list of domain names (e.g. ['d01', 'd02'] )

    Returns:
        True if all the required MCIP files are present, False if not
    """
    allMcipFilesFound = True
    if not os.path.exists(ctmDir):
        os.mkdir(ctmDir)
    ##
    for idate, date in enumerate(dates):
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        ##
        parent_chemdir = f"{ctmDir}/{yyyymmdd_dashed}"
        ## create output destination
        if not os.path.exists(parent_chemdir):
            os.mkdir(parent_chemdir)
        for idomain, domain in enumerate(domains):
            mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
            chemdir = f"{ctmDir}/{yyyymmdd_dashed}/{domain}"
            if not os.path.exists(mcipdir):
                warnings.warn(f"MCIP output directory not found at {mcipdir} ... ")
                allMcipFilesFound = False
                return allMcipFilesFound
            ## create output destination
            if not os.path.exists(chemdir):
                os.mkdir(chemdir)
            ## check that the MCIP GRIDDESC file is present
            griddescFilePath = f"{mcipdir}/GRIDDESC"
            if not os.path.exists(griddescFilePath):
                warnings.warn(f"GRIDDESC file not found at {griddescFilePath} ... ")
                allMcipFilesFound = False
                return allMcipFilesFound
            ## check that the other MCIP output files are present
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
                matches = glob.glob(f"{mcipdir}/{filetype}_*")
                if len(matches) == 0:
                    warnings.warn(f"{filetype} file not found in folder {mcipdir} ... ")
                    allMcipFilesFound = False
                    return allMcipFilesFound
                elif len(matches) > 1:
                    print("warn-inside checkwrfmcip")
    return allMcipFilesFound


def getMcipGridNames(metDir, dates, domains):
    """Get grid names from the MCIP GRIDDESC file

    Args:
        metDir: base directory for the MCIP output
        dates: list of datetime objects for the dates to run
        domains: list of which domains should be run?

    Returns:
        CoordNames: list of MCIP scenario tags (one per domain)
        GridNames: list of MCIP map projection names (one per domain)
        APPL: list of MCIP grid names (one per domain)
    """

    date = dates[0]
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")
    ##
    ndom = len(domains)
    ##
    CoordNames = [[]] * ndom
    GridNames = [[]] * ndom
    APPL = [[]] * ndom
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        griddescFilePath = f"{mcipdir}/GRIDDESC"
        if not os.path.exists(griddescFilePath):
            raise RuntimeError(f"GRIDDESC file not found at {griddescFilePath} ... ")
        f = open(griddescFilePath)
        lines = f.readlines()
        f.close()
        CoordNames[idomain] = lines[1].strip().replace("'", "").replace('"', "")
        GridNames[idomain] = lines[4].strip().replace("'", "").replace('"', "")
        ## find the APPL suffix
        filetype = "GRIDCRO2D"
        matches = glob.glob(f"{mcipdir}/{filetype}_*")
        if len(matches) == 0:
            raise RuntimeError(f"{filetype} file not found in folder {mcipdir} ... ")
        ##
        APPL[idomain] = matches[0].split("/")[-1].replace(f"{filetype}_", "")
    ##
    return CoordNames, GridNames, APPL


def checkWrfMcipDomainSizes(metDir, date, domains, wrfDir=None):
    """Cross check the WRF and MCIP domain sizes

    Args:
        metDir: base directory for the MCIP output
        date: the date in question
        domains: list of domains
        wrfDir:directory containing wrfout_* files

    Returns:
        nx_wrf: length of the x-dimension for the WRF grid
        ny_wrf: length of the y-dimension for the WRF grid
        nx_cmaq: length of the x-dimension for the CMAQ grid
        ny_cmaq: length of the y-dimension for the CMAQ grid
        ix0: the index in the WRF grid of the first CMAQ grid-point in the x-direction
        iy0: the index in the WRF grid of the first CMAQ grid-point in the y-direction
        ncolsin: length of the x-dimension for the CMAQ grid
        nrowsin: length of the y-dimension for the CMAQ grid
    """

    yyyymmdd_dashed = date.strftime("%Y-%m-%d")
    ##
    ndom = len(domains)
    ##
    nx_wrf = numpy.zeros((ndom,), dtype=int)
    ny_wrf = numpy.zeros((ndom,), dtype=int)
    nx_cmaq = numpy.zeros((ndom,), dtype=int)
    ny_cmaq = numpy.zeros((ndom,), dtype=int)
    ix0 = numpy.zeros((ndom,), dtype=int)
    iy0 = numpy.zeros((ndom,), dtype=int)
    ncolsin = numpy.zeros((ndom,), dtype=int)
    nrowsin = numpy.zeros((ndom,), dtype=int)
    for idomain, domain in enumerate(domains):
        mcipdir = f"{metDir}/{yyyymmdd_dashed}/{domain}"
        ## find the APPL suffix
        filetype = "GRIDCRO2D"
        matches = glob.glob(f"{mcipdir}/{filetype}_*")
        if len(matches) == 0:
            raise RuntimeError(f"{filetype} file not found in folder {mcipdir} ... ")
        ##
        APPL = matches[0].split("/")[-1].replace(f"{filetype}_", "")
        ## open the GRIDCRO2D file
        gridcro2dfilepath = f"{mcipdir}/{filetype}_{APPL}"
        nc = netCDF4.Dataset(gridcro2dfilepath)
        ## read in the latitudes and longitudes
        mcipLat = nc.variables["LAT"][0, 0, :, :]
        mcipLon = nc.variables["LON"][0, 0, :, :]
        nc.close()
        ## find a WRF file
        matches = glob.glob(f"{mcipdir}/WRFOUT_{domain}_*")
        if len(matches) == 0:
            if type(wrfDir) == type(None):
                raise RuntimeError(
                    f"No files matched the pattern WRFOUT_{domain}_* in folder {mcipdir}, and no alternative WRF directory was provided..."
                )
            elif len(matches) > 1:
                warnings.warn(
                    f"Multiple files match the pattern WRFOUT_{domain}_* in folder {mcipdir}, using file {matches[0]}"
                )
            else:
                matches = glob.glob(f"{wrfDir}/WRFOUT_{domain}_*")
                if len(matches) == 0:
                    raise RuntimeError(
                        f"No files matched the pattern WRFOUT_{domain}_* the folders {mcipdir} and {wrfDir} ..."
                    )
                elif len(matches) > 1:
                    warnings.warn(
                        f"Multiple files match the pattern WRFOUT_{domain}_* in folder {wrfDir}, using file {matches[0]}"
                    )
        ##
        wrfFile = matches[0]
        nc = netCDF4.Dataset(wrfFile)
        ## read in the latitudes and longitudes
        wrfLat = nc.variables["XLAT"][0, :, :]
        wrfLon = nc.variables["XLONG"][0, :, :]
        nc.close()

        ix = [0, 0, -1, -1]
        iy = [0, -1, 0, -1]
        ncorn = len(ix)
        icorn = [0] * ncorn
        jcorn = [0] * ncorn
        for i in range(ncorn):
            dists = getDistanceFromLatLonInKm(
                mcipLat[ix[i], iy[i]], mcipLon[ix[i], iy[i]], wrfLat, wrfLon
            )
            minidx = numpy.argmin(dists)
            mindist = dists.min()
            if mindist > 0.5:
                warnings.warn(f"Distance between grid-points was {mindist} km for domain {domain}")
            icorn[i], jcorn[i] = numpy.unravel_index(minidx, wrfLat.shape)
        if (
            icorn[0] != icorn[1]
            or icorn[2] != icorn[3]
            or jcorn[0] != jcorn[2]
            or jcorn[1] != jcorn[3]
        ):
            print("icorn =", icorn)
            print("jcorn =", jcorn)
            raise RuntimeError(
                f"Indices of the corner points not completely consistent between the WRF and MCIP grids for domain {domain}"
            )

        nx_wrf[idomain] = wrfLat.shape[0]
        ny_wrf[idomain] = wrfLat.shape[1]
        nx_cmaq[idomain] = mcipLat.shape[0]
        ny_cmaq[idomain] = mcipLat.shape[1]
        ix0[idomain] = icorn[0]
        iy0[idomain] = jcorn[0]
        ncolsin[idomain] = mcipLat.shape[1]
        nrowsin[idomain] = mcipLat.shape[0]

    return nx_wrf, ny_wrf, nx_cmaq, ny_cmaq, ix0, iy0, ncolsin, nrowsin
