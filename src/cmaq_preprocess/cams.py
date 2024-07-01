"""Interpolate the from the global CAMS CTM output to ICs and BCs for CMAQ"""

import datetime
import os
import shutil
import warnings

import netCDF4
import numpy

from cmaq_preprocess.utils import getDistanceFromLatLonInKm

moleMass = {"air": 28.96, "ch4_c": 16}


def match_two_sorted_arrays(arr1, arr2):
    """Match up two sorted arrays

    Args:
        arr1: A sorted 1D numpy array
        arr2: A sorted 1D numpy array

    Returns:
        result: numpy integer array with the same dimensions as array arr2, with each element containing the index of arr1 that provides the *closest* match to the given entry in arr2
    """
    result = numpy.zeros(arr2.shape, dtype=int)
    for i, v in enumerate(arr2):
        result[i] = numpy.argmin(numpy.abs(arr1 - v))
    return result


def extract_and_interpolate_interior(mzspec, ncin, lens, LON, Iz, iMZtime, P, near_interior):
    """Interpolate from the CAMS grid to the CMAQ interior points (i.e. the full 3D array)

    Args:
        mzspec: the CAMS species name
        ncin: the connection to the netCDF input file (i.e. the CAMS file)
        lens: dictionary of dimension lengths
        LON: array of longitudes with the same size as the output array
        Iz: array of indices of CAMS levels that correspond to the CMAQ levels
        iMZtime: index of the CAMS time to use
        isAerosol: Boolean (True/False) whether this is an aerosol species or not
        mz_mw_aerosol: molecular weight of the CAMS species
        T: array of temperatures (units = K) from the CAMS output
        P: array of pressures (units = Pa) from the CAMS output
        near_interior: array of indices matching up the CAMS grid-points with CMAQ grid-points

    Returns:
        out_interior: Gridded CAMS concentrations interpolated to the CMAQ grid
    """
    #
    out_interior = numpy.zeros((lens["LAY"], LON.shape[0], LON.shape[1]), dtype=numpy.float32)
    #
    if mzspec in list(ncin.variables.keys()):
        varin = ncin.variables[mzspec][iMZtime, :, :, :]
        #
        convFac = moleMass["air"] / moleMass[mzspec] * 1e6  # converting from kg/kg to VMR in ppmv
        varin = varin * convFac  ## convert from VMR to PPMV
        #
        for irow in range(LON.shape[0]):
            for icol in range(LON.shape[1]):
                ix, iy = near_interior[irow, icol, :]
                out_interior[:, irow, icol] = varin[Iz, ix, iy]
    else:
        warnings.warn(
            f"Species {mzspec} was not found in input CAMS file -- contributions from this variable will be zero..."
        )
    #
    return out_interior


def extract_and_interpolate_boundary(
    mzspec, ncin, lens, LONP, Iz, iMZtime_for_each_CMtime, P, near_boundary
):
    """Interpolate from the CAMS grid to the CMAQ boundary points

    Args:
        mzspec: the CAMS species name
        ncin: the connection to the netCDF input file (i.e. the CAMS file)
        lens: dictionary of dimension lengths
        LONP: array of longitudes of CMAQ boundary points with the same size as the output array
        Iz: array of indices of CAMS levels that correspond to the CMAQ levels
        iMZtime_for_each_CMtime: index of the CAMS time to use, one entry for each CMAQ time
        P: array of pressures (units = Pa) from the CAMS output
        near_boundary: array of indices matching up the CAMS grid-points with CMAQ boundary grid-points

    Returns:
        out_boundary: Gridded CAMS concentrations interpolated to the CMAQ boundary grid points
    """
    #
    iCMtime = 0
    iMZtime = iMZtime_for_each_CMtime[iCMtime]
    #
    ntime = 1
    out_boundary = numpy.zeros((ntime, lens["LAY"], LONP.shape[0]), dtype=numpy.float32)
    #
    if mzspec in list(ncin.variables.keys()):
        varin = ncin.variables[mzspec][iMZtime, :, :, :]
        #
        convFac = moleMass["air"] / moleMass[mzspec] * 1e6  # converting from kg/kg to VMR in ppmv
        varin = varin * convFac  ## convert from VMR to PPMV
        #
        for iperim in range(LONP.shape[0]):
            ix, iy = near_boundary[iperim, :]
            ## for iCMtime, iMZtime in enumerate(iMZtime_for_each_CMtime):
            out_boundary[iCMtime, :, iperim] = varin[Iz, ix, iy]
    else:
        warnings.warn(
            f"Species {mzspec} was not found in input CAMS file -- contributions from this variable will be zero..."
        )
    #
    return out_boundary


def populate_interior_variable(ncouti, cmspec, out_interior, coef):
    """Populate an interior variable (i.e. for the IC file)

    Args:
        ncouti: connection to the output file for the initial conditions
        cmspec: the name of the CMAQ species
        out_interior: numpy array of concentrations at interior points
        coef: Coefficient to multiply the values by

    Returns:
        Nothing
    """
    ncouti.variables[cmspec][:] = ncouti.variables[cmspec][:] + numpy.fmax(
        out_interior[:] * coef, 1.0e-30
    )


def populate_boundary_variable(ncoutb, cmspec, out_boundary, coef):
    """Populate an boundary variable (i.e. for the BC file)

    Args:
        ncoutb: connection to the output file for the boundary conditions
        cmspec: the name of the CMAQ species
        out_boundary: numpy array of concentrations at boundary points
        coef: Coefficient to multiply the values by

    Returns:
        Nothing
    """
    ncoutb.variables[cmspec][:] = ncoutb.variables[cmspec][:] + numpy.fmax(
        out_boundary[:] * coef, 1.0e-30
    )


def print_interior_variable(cmspec, out_interior, factor):
    """Print the mean value of a interior variable

    Args:
        cmspec: Name of the CMAQ species
        out_interior: numpy array of concentrations at interior points
        factor: Coefficient to multiply the values by

    Returns:
        Nothing

    """
    print(f"{cmspec:20} {out_interior[0, :, :].mean() * factor:.3e}")


def print_boundary_variable(cmspec, out_boundary, factor):
    """Print the mean value of a boundary variable

    Args:
        cmspec: Name of the CMAQ species
        out_boundary: numpy array of concentrations at boundary points
        factor: Coefficient to multiply the values by

    Returns:
        Nothing

    """
    print(f"{cmspec:20} {out_boundary[:, 0, :].mean() * factor:.3e}")


def interpolateFromCAMSToCmaqGrid(
    dates,
    doms,
    mech,
    inputCAMSFile,
    templateIconFiles,
    templateBconFiles,
    metDir,
    ctmDir,
    GridNames,
    mcipsuffix,
    forceUpdate,
    bias_correct=0.0,
    defaultSpec="O3",
):
    """Function to interpolate the from the global CAMS CTM output to ICs and BCs for CMAQ

    Args:
        dates: list of datetime objects, one per date MCIP and CCTM output should be defined
        doms: list of domain names (e.g. ['d01', 'd02'] )
        mech: name of chemical mechanism to appear in filenames
        inputCAMSFile: Output from CAMS to use for boundary and initial conditions
        templateIconFiles: list of filenames for template ICON files
        templateBconFiles: list of filenames for template BCON files
        metDir: base directory for the MCIP output
        ctmDir: base directory for the CCTM inputs and outputs
        GridNames: list of MCIP map projection names (one per domain)
        mcipsuffix: Suffix for the MCIP output files
        forceUpdate: Boolean (True/False) for whether we should update the output if it already exists
        defaultSpec: A species that is known to exist in the CAMS files (defaults to 'O3'), used for checking dimension information

    Returns:
        Nothing

    """
    ##
    ## if we aren't forcing an update, check whether files exist and
    ## return early if possible
    if not forceUpdate:
        allFilesExist = True
        for idate, date in enumerate(dates):
            yyyymmdd_dashed = date.strftime("%Y-%m-%d")
            do_ICs = idate == 0
            for idom, dom in enumerate(doms):
                grid = GridNames[idom]
                chemdir = f"{ctmDir}/{yyyymmdd_dashed}/{dom}"
                do_BCs = dom == doms[0]
                ##
                outBCON = f"{chemdir}/BCON.{dom}.{grid}.{mech}.nc"
                outICON = f"{chemdir}/ICON.{dom}.{grid}.{mech}.nc"
                ##
                if do_BCs and (not os.path.exists(outBCON)):
                    allFilesExist = False
                ##
                if do_ICs and (not os.path.exists(outICON)):
                    allFilesExist = False
                ##
        ##
        if allFilesExist:
            return

    ##
    for idate, date in enumerate(dates):
        yyyymmdd_dashed = date.strftime("%Y-%m-%d")
        do_ICs = idate == 0
        for idom, dom in enumerate(doms):
            grid = GridNames[idom]
            mcipdir = f"{metDir}/{yyyymmdd_dashed}/{dom}"
            chemdir = f"{ctmDir}/{yyyymmdd_dashed}/{dom}"

            ## check that the output directory exists - if not, create it
            os.makedirs(chemdir, exist_ok=True)

            do_BCs = dom == doms[0]

            if not (do_ICs or do_BCs):
                continue

            croFile = f"{mcipdir}/GRIDCRO2D_{mcipsuffix[idom]}"
            dotFile = f"{mcipdir}/GRIDDOT2D_{mcipsuffix[idom]}"
            bdyFile = f"{mcipdir}/GRIDBDY2D_{mcipsuffix[idom]}"
            metFile = f"{mcipdir}/METCRO3D_{mcipsuffix[idom]}"
            srfFile = f"{mcipdir}/METCRO2D_{mcipsuffix[idom]}"
            outBCON = f"{chemdir}/BCON.{dom}.{grid}.{mech}.nc"
            outICON = f"{chemdir}/ICON.{dom}.{grid}.{mech}.nc"
            templateIconFile = templateIconFiles[idom]
            templateBconFile = templateBconFiles[idom]

            if do_BCs:
                if os.path.exists(outBCON):
                    os.remove(outBCON)
                shutil.copyfile(templateBconFile, outBCON)
                print(f"copy {templateBconFile} to {outBCON}")

            if do_ICs:
                if os.path.exists(outICON):
                    os.remove(outICON)
                shutil.copyfile(templateIconFile, outICON)
                print(f"copy {templateIconFile} to {outICON}")

            print(dotFile)
            with (
                netCDF4.Dataset(croFile, "r", format="NETCDF4") as nccro,
                netCDF4.Dataset(bdyFile, "r", format="NETCDF4") as ncbdy,
                netCDF4.Dataset(metFile, "r", format="NETCDF4") as ncmet,
                netCDF4.Dataset(srfFile, "r", format="NETCDF4") as ncsrf,
                netCDF4.Dataset(inputCAMSFile, "r", format="NETCDF4") as ncin,
            ):
                if do_BCs:
                    print("write BCs to file: ", outBCON)
                    ncoutb = netCDF4.Dataset(outBCON, "r+", format="NETCDF4")
                    all_vars = list(ncoutb.variables.keys())[1:]
                    nvars = len(all_vars)

                if do_ICs:
                    print("write ICs to file: ", outICON)
                    ncouti = netCDF4.Dataset(outICON, "r+", format="NETCDF4")
                    all_vars = list(ncoutb.variables.keys())[1:]
                    nvars = len(all_vars)

                lens = dict()
                for k in list(nccro.dimensions.keys()):
                    lens[k] = len(nccro.dimensions[k])

                lens["PERIM"] = len(ncbdy.dimensions["PERIM"])
                lens["LAY"] = len(ncmet.dimensions["LAY"])
                lens["VAR"] = nvars
                lens["TSTEP"] = 1

                LAT = nccro.variables["LAT"][:].squeeze()
                LON = nccro.variables["LON"][:].squeeze()
                LATP = ncbdy.variables["LAT"][:].squeeze()
                LONP = ncbdy.variables["LON"][:].squeeze()
                sigma = ncmet.getncattr("VGLVLS")
                mtop = ncmet.getncattr("VGTOP")
                #
                base_MZ_time = datetime.datetime(1900, 1, 1, 0, 0, 0)  # epoch
                MZdates = [base_MZ_time + datetime.timedelta(hours=int(t)) for t in ncin["time"][:]]
                #
                latmz = ncin.variables["latitude"][:].squeeze()
                lonmz = ncin.variables["longitude"][:].squeeze()
                PSURF = ncsrf.variables["PRSFC"][:].squeeze()
                TFLAG = ncsrf.variables["TFLAG"][:, 0, :].squeeze()
                yyyy = TFLAG[:, 0] // 1000
                jjj = TFLAG[:, 0] % 1000
                hh = TFLAG[:, 1] // 10000
                mm = (TFLAG[:, 1] - hh * 10000) / 100
                ss = TFLAG[:, 1] % 100
                ntimemod = len(yyyy)
                timesmod = [
                    datetime.datetime(int(yyyy[i]), 1, 1, 0, 0, 0)
                    + datetime.timedelta(
                        days=float(jjj[i] - 1)
                        + float(hh[i]) / 24.0
                        + float(mm[i]) / (24.0 * 60.0)
                        + float(ss[i]) / (24.0 * 60.0 * 60.0)
                    )
                    for i in range(ntimemod)
                ]
                itimes = numpy.where([t.date() == date.date() for t in timesmod])[0]
                itime0 = itimes[0]
                itime1 = itimes[-1] + 2
                timesmod = timesmod[itime0:itime1]
                TFLAG = TFLAG[itime0:itime1]

                ## populate the pressure array
                P = numpy.zeros(ncin["ch4_c"].shape)
                P += ncin["level"][...][
                    :, numpy.newaxis, numpy.newaxis
                ]  # broadcasting but into axis 0 not axis -1
                LATMZ = numpy.zeros((len(latmz), len(lonmz)))
                LONMZ = numpy.zeros((len(latmz), len(lonmz)))
                for irow in range(len(latmz)):
                    LONMZ[irow, :] = lonmz

                for icol in range(len(lonmz)):
                    LATMZ[:, icol] = latmz

                near_interior = numpy.zeros((LON.shape[0], LON.shape[1], 2), dtype=int)
                near_boundary = numpy.zeros((LONP.shape[0], 2), dtype=int)

                for irow in range(LON.shape[0]):
                    for icol in range(LON.shape[1]):
                        dists = getDistanceFromLatLonInKm(
                            LAT[irow, icol], LON[irow, icol], LATMZ, LONMZ
                        )
                        minidx = numpy.argmin(dists)
                        ix, iy = numpy.unravel_index(minidx, LONMZ.shape)
                        near_interior[irow, icol, 0] = ix
                        near_interior[irow, icol, 1] = iy

                for iperim in range(LONP.shape[0]):
                    dists = getDistanceFromLatLonInKm(LATP[iperim], LONP[iperim], LATMZ, LONMZ)
                    minidx = numpy.argmin(dists)
                    ix, iy = numpy.unravel_index(minidx, LONMZ.shape)
                    near_boundary[iperim, 0] = ix
                    near_boundary[iperim, 1] = iy

                iMZtime_for_each_CMtime = numpy.zeros((len(timesmod)), dtype=int)
                for itime, time in enumerate(timesmod):
                    dtime = numpy.array(
                        [((time - t).total_seconds()) / (24.0 * 60.0 * 60.0) for t in MZdates]
                    )
                    if all(dtime < 0.0):
                        imin = numpy.argmin(numpy.abs(dtime))
                        iMZtime_for_each_CMtime[itime] = imin
                        warnings.warn(
                            "All dates were negative for date {}, using nearest match: {}".format(
                                date.strftime("%Y-%m-%d %H:%M:%S"),
                                MZdates[imin].strftime("%Y-%m-%d %H:%M:%S"),
                            )
                        )
                    else:
                        iMZtime_for_each_CMtime[itime] = numpy.where(dtime >= 0)[0][-1]

                iMZtime = iMZtime_for_each_CMtime[0]

                ## interpolation from CAMS to CMAQ levels
                if not ("Iz" in vars() or "Iz" in globals()):
                    irow = LON.shape[0] - 1
                    icol = LON.shape[1] - 1
                    itime = 0
                    PRES_CM = (PSURF[itime, irow, icol] - mtop) * sigma + mtop
                    PRES_CM[0] = PSURF[itime, irow, icol]
                    PRES_CM = (PRES_CM[1:] + PRES_CM[:-1]) / 2.0
                    # PRES_MZ = Ap +  Bp * PSURF[itime,irow,icol]
                    PRES_MZm = ncin["level"][:].astype("float")
                    mb2pa = 100.0  # converting from  millibar to pascal
                    Iz = match_two_sorted_arrays(PRES_MZm * mb2pa, PRES_CM)
                ## set the values to zero for species that we *WILL* interpolate to
                ALL_CM_SPEC = ["CH4"]
                species_map = []
                species_map.append(
                    {
                        "MZspec": "ch4_c",
                        "CMspec": "CH4",
                        "coef": 1.0,
                        "isAerosol": False,
                    }
                )
                for spec in ALL_CM_SPEC:
                    if do_ICs:
                        if spec not in list(ncouti.variables.keys()):
                            warnings.warn(
                                f"Species {spec} was not found in template CMAQ IC file -- creating blank variable..."
                            )
                            isnetcdf4 = ncouti.data_model == "NETCDF4"
                            ncouti.createVariable(
                                varname=spec,
                                datatype="f4",
                                dimensions=ncouti.variables[defaultSpec].dimensions,
                                zlib=isnetcdf4,
                            )
                            ncouti.long_name = f"{spec:16}"
                            ncouti.units = "{:16}".format("ppmV")
                            ncouti.var_desc = "{:80}".format("Variable " + spec)
                        ncouti.variables[spec][:] = 0.0
                    if do_BCs:
                        if spec not in list(ncoutb.variables.keys()):
                            warnings.warn(
                                f"Species {spec} was not found in template CMAQ BC file -- creating blank variable..."
                            )
                            isnetcdf4 = ncoutb.data_model == "NETCDF4"
                            ncoutb.createVariable(
                                varname=spec,
                                datatype="f4",
                                dimensions=ncoutb.variables[defaultSpec].dimensions,
                                zlib=isnetcdf4,
                            )
                            ncoutb.long_name = f"{spec:16}"
                            ncoutb.units = "{:16}".format("ppmV")
                            ncoutb.var_desc = "{:80}".format("Variable " + spec)
                        ncoutb.variables[spec][:] = 0.0

                nspec = len(species_map)
                for ispec in range(nspec):
                    MZspec = species_map[ispec]["MZspec"]
                    CMspec = species_map[ispec]["CMspec"]
                    coefs = species_map[ispec]["coef"]
                    Factor = 1.0e3  ## convert from ppm to ppb
                    ##
                    if do_ICs:
                        out_interior = extract_and_interpolate_interior(
                            MZspec, ncin, lens, LON, Iz, iMZtime, P, near_interior
                        )
                        out_interior += bias_correct
                        print_interior_variable(MZspec, out_interior, Factor)
                    ##
                    if do_BCs:
                        out_boundary = extract_and_interpolate_boundary(
                            MZspec,
                            ncin,
                            lens,
                            LONP,
                            Iz,
                            iMZtime_for_each_CMtime,
                            P,
                            near_boundary,
                        )
                        out_boundary += bias_correct
                        print_boundary_variable(MZspec, out_boundary, Factor)
                    ##
                    if do_ICs:
                        populate_interior_variable(ncouti, CMspec, out_interior, coefs)
                    ##
                    if do_BCs:
                        populate_boundary_variable(ncoutb, CMspec, out_boundary, coefs)

                if do_ICs:
                    ncouti.close()
                if do_BCs:
                    ncoutb.close()
