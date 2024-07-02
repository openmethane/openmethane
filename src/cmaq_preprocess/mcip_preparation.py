"""Functions to check folders, files and attributes from MCIP output"""

import datetime
import glob
import os
import warnings

import netCDF4
import numpy

from cmaq_preprocess.utils import get_distance_from_lat_lon_in_km


def check_input_met_and_output_folders(
    ctm_dir, met_dir, dates: list[datetime.date], domains: list[str]
):
    """
    Check that MCIP inputs are present, and create directories for CCTM input/output if need be

    Args:
        ctm_dir: base directory for the CCTM inputs and outputs
        met_dir: base directory for the MCIP output
        dates: list of datetime objects, one per date MCIP and CCTM output should be defined
        domains: list of domain names (e.g. ['d01', 'd02'] )

    Returns:
        True if all the required MCIP files are present, False if not
    """
    all_mcip_files_found = True
    if not os.path.exists(ctm_dir):
        os.mkdir(ctm_dir)
    ##
    for idate, date in enumerate(dates):
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        ##
        parent_chemdir = f"{ctm_dir}/{yyyymmdd_dashed}"
        ## create output destination
        if not os.path.exists(parent_chemdir):
            os.mkdir(parent_chemdir)
        for idomain, domain in enumerate(domains):
            mcip_dir = f"{met_dir}/{yyyymmdd_dashed}/{domain}"
            chemdir = f"{ctm_dir}/{yyyymmdd_dashed}/{domain}"
            if not os.path.exists(mcip_dir):
                warnings.warn(f"MCIP output directory not found at {mcip_dir} ... ")
                all_mcip_files_found = False
                return all_mcip_files_found
            ## create output destination
            if not os.path.exists(chemdir):
                os.mkdir(chemdir)
            ## check that the MCIP GRIDDESC file is present
            griddesc_file_path = f"{mcip_dir}/GRIDDESC"
            if not os.path.exists(griddesc_file_path):
                warnings.warn(f"GRIDDESC file not found at {griddesc_file_path} ... ")
                all_mcip_files_found = False
                return all_mcip_files_found
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
                matches = glob.glob(f"{mcip_dir}/{filetype}_*")
                if len(matches) == 0:
                    warnings.warn(f"{filetype} file not found in folder {mcip_dir} ... ")
                    all_mcip_files_found = False
                    return all_mcip_files_found
                elif len(matches) > 1:
                    print("warn-inside checkwrfmcip")
    return all_mcip_files_found


def get_mcip_grid_names(met_dir: str, dates: list[datetime.date], domains: list[str]):
    """Get grid names from the MCIP GRIDDESC file

    Args:
        met_dir: base directory for the MCIP output
        dates: list of datetime objects for the dates to run
        domains: list of which domains should be run?

    Returns:
        coord_names: list of MCIP scenario tags (one per domain)
        grid_names: list of MCIP map projection names (one per domain)
        simulation_names: list of MCIP grid names (one per domain)
    """

    date = dates[0]
    yyyymmdd_dashed = date.strftime("%Y-%m-%d")

    coord_names: list[str] = []
    grid_names: list[str] = []
    simulation_names: list[str] = []
    for i_domain, domain in enumerate(domains):
        mcip_dir = f"{met_dir}/{yyyymmdd_dashed}/{domain}"
        griddesc_file_path = f"{mcip_dir}/GRIDDESC"
        if not os.path.exists(griddesc_file_path):
            raise RuntimeError(f"GRIDDESC file not found at {griddesc_file_path} ... ")
        f = open(griddesc_file_path)
        lines = f.readlines()
        f.close()
        coord_names.append(lines[1].strip().replace("'", "").replace('"', ""))
        grid_names.append(lines[4].strip().replace("'", "").replace('"', ""))

        ## find the simulation_names suffix
        filetype = "GRIDCRO2D"
        matches = glob.glob(f"{mcip_dir}/{filetype}_*")
        if len(matches) == 0:
            raise RuntimeError(f"{filetype} file not found in folder {mcip_dir} ... ")

        simulation_names.append(matches[0].split("/")[-1].replace(f"{filetype}_", ""))
    return coord_names, grid_names, simulation_names


def check_wrf_mcip_domain_sizes(
    met_dir: str, date: datetime.date, domains: list[str], wrf_dir: str | None = None
):
    """Cross check the WRF and MCIP domain sizes

    Args:
        met_dir: base directory for the MCIP output
        date: the date in question
        domains: list of domains
        wrf_dir: directory containing wrfout_* files

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
        mcip_dir = f"{met_dir}/{yyyymmdd_dashed}/{domain}"
        ## find the APPL suffix
        filetype = "GRIDCRO2D"
        matches = glob.glob(f"{mcip_dir}/{filetype}_*")
        if len(matches) == 0:
            raise RuntimeError(f"{filetype} file not found in folder {mcip_dir} ... ")
        ##
        APPL = matches[0].split("/")[-1].replace(f"{filetype}_", "")
        ## open the GRIDCRO2D file
        gridcro2dfilepath = f"{mcip_dir}/{filetype}_{APPL}"
        nc = netCDF4.Dataset(gridcro2dfilepath)
        ## read in the latitudes and longitudes
        mcip_lat = nc.variables["LAT"][0, 0, :, :]
        mcip_lon = nc.variables["LON"][0, 0, :, :]
        nc.close()
        ## find a WRF file
        matches = glob.glob(f"{mcip_dir}/WRFOUT_{domain}_*")
        if len(matches) == 0:
            if wrf_dir is None:
                raise RuntimeError(
                    f"No files matched the pattern WRFOUT_{domain}_* in folder {mcip_dir}"
                    f", and no alternative WRF directory was provided..."
                )
            elif len(matches) > 1:
                warnings.warn(
                    f"Multiple files match the pattern WRFOUT_{domain}_* in folder {mcip_dir},"
                    f" using file {matches[0]}"
                )
            else:
                matches = glob.glob(f"{wrf_dir}/WRFOUT_{domain}_*")
                if len(matches) == 0:
                    raise RuntimeError(
                        f"No files matched the pattern WRFOUT_{domain}_* "
                        f"the folders {mcip_dir} and {wrf_dir} ..."
                    )
                elif len(matches) > 1:
                    warnings.warn(
                        f"Multiple files match the pattern WRFOUT_{domain}_* in folder {wrf_dir}, "
                        f"using file {matches[0]}"
                    )
        ##
        wrf_file = matches[0]
        with netCDF4.Dataset(wrf_file) as nc:
            ## read in the latitudes and longitudes
            wrf_lat = nc.variables["XLAT"][0, :, :]
            wrf_lon = nc.variables["XLONG"][0, :, :]

        ix = [0, 0, -1, -1]
        iy = [0, -1, 0, -1]
        ncorn = len(ix)
        icorn = [0] * ncorn
        jcorn = [0] * ncorn
        for i in range(ncorn):
            dists = get_distance_from_lat_lon_in_km(
                mcip_lat[ix[i], iy[i]], mcip_lon[ix[i], iy[i]], wrf_lat, wrf_lon
            )
            min_idx = numpy.argmin(dists)
            min_dist = dists.min()
            if min_dist > 0.5:
                warnings.warn(f"Distance between grid-points was {min_dist} km for domain {domain}")
            icorn[i], jcorn[i] = numpy.unravel_index(min_idx, wrf_lat.shape)
        if (
            icorn[0] != icorn[1]
            or icorn[2] != icorn[3]
            or jcorn[0] != jcorn[2]
            or jcorn[1] != jcorn[3]
        ):
            print("icorn =", icorn)
            print("jcorn =", jcorn)
            raise RuntimeError(
                f"Indices of the corner points not completely consistent between the "
                f"WRF and MCIP grids for domain {domain}"
            )

        nx_wrf[idomain] = wrf_lat.shape[0]
        ny_wrf[idomain] = wrf_lat.shape[1]
        nx_cmaq[idomain] = mcip_lat.shape[0]
        ny_cmaq[idomain] = mcip_lat.shape[1]
        ix0[idomain] = icorn[0]
        iy0[idomain] = jcorn[0]
        ncolsin[idomain] = mcip_lat.shape[1]
        nrowsin[idomain] = mcip_lat.shape[0]

    return nx_wrf, ny_wrf, nx_cmaq, ny_cmaq, ix0, iy0, ncolsin, nrowsin
