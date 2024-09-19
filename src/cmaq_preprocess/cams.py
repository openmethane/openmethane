"""Interpolate the from the global CAMS CTM output to ICs and BCs for CMAQ"""

import datetime
import os
import pathlib
import shutil
import warnings

import netCDF4
import numpy

from cmaq_preprocess.read_config_cmaq import Domain
from cmaq_preprocess.utils import get_distance_from_lat_lon_in_km, nested_dir

moleMass = {"air": 28.96, "ch4_c": 16}


def match_two_sorted_arrays(arr1, arr2):
    """Match up two sorted arrays

    Args:
        arr1: A sorted 1D numpy array
        arr2: A sorted 1D numpy array

    Returns:
        result: numpy integer array with the same dimensions as array arr2, with each element
        containing the index of arr1 that provides the *closest* match to the given entry in arr2
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
    out_interior = numpy.zeros((lens["LAY"], LON.shape[0], LON.shape[1]), dtype=numpy.float32)

    if mzspec in list(ncin.variables.keys()):
        varin = ncin.variables[mzspec][iMZtime, :, :, :]

        convFac = moleMass["air"] / moleMass[mzspec] * 1e6  # converting from kg/kg to VMR in ppmv
        varin = varin * convFac  ## convert from VMR to PPMV

        for irow in range(LON.shape[0]):
            for icol in range(LON.shape[1]):
                ix, iy = near_interior[irow, icol, :]
                out_interior[:, irow, icol] = varin[Iz, ix, iy]
    else:
        warnings.warn(
            f"Species {mzspec} was not found in input CAMS file "
            f"-- contributions from this variable will be zero..."
        )

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
    iCMtime = 0
    iMZtime = iMZtime_for_each_CMtime[iCMtime]
    ntime = 1
    out_boundary = numpy.zeros((ntime, lens["LAY"], LONP.shape[0]), dtype=numpy.float32)
    if mzspec in list(ncin.variables.keys()):
        varin = ncin.variables[mzspec][iMZtime, :, :, :]
        convFac = moleMass["air"] / moleMass[mzspec] * 1e6  # converting from kg/kg to VMR in ppmv
        varin = varin * convFac  ## convert from VMR to PPMV
        for iperim in range(LONP.shape[0]):
            ix, iy = near_boundary[iperim, :]
            ## for iCMtime, iMZtime in enumerate(iMZtime_for_each_CMtime):
            out_boundary[iCMtime, :, iperim] = varin[Iz, ix, iy]
    else:
        warnings.warn(
            f"Species {mzspec} was not found in input CAMS file "
            f"-- contributions from this variable will be zero..."
        )
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


def interpolate_from_cams_to_cmaq_grid(
    dates: list[datetime.date],
    domain: Domain,
    mech: str,
    input_cams_file: pathlib.Path,
    template_icon_file: pathlib.Path,
    template_bcon_file: pathlib.Path,
    met_dir: pathlib.Path,
    ctm_dir: pathlib.Path,
    force_update: bool,
    bias_correct=0.0,
    default_spec="O3",
):
    """Function to interpolate from the global CAMS CTM output to ICs and BCs for CMAQ

    Args:
        dates: list of datetime objects, one per date MCIP and CCTM output should be defined
        domain: Domain to process
        mech: name of chemical mechanism to appear in filenames
        input_cams_file: Output from CAMS to use for boundary and initial conditions
        template_icon_file: list of filenames for template ICON files
        template_bcon_file: list of filenames for template BCON files
        met_dir: base directory for the MCIP output
        ctm_dir: base directory for the CCTM inputs and outputs
        force_update: If True, update the output even if it already exists
        default_spec: A species that is known to exist in the CAMS files (defaults to 'O3'),
            used for checking dimension information

    Returns:
        Nothing

    """
    ##
    ## if we aren't forcing an update, check whether files exist and
    ## return early if possible
    if not force_update:
        all_files_exist = True
        for idate, date in enumerate(dates):
            do_ICs = idate == 0

            chem_dir = nested_dir(domain, date, ctm_dir)
            do_BCs = domain.index == 1

            outBCON = chem_dir / f"{chem_dir}/BCON.{domain.id}.{domain.mcip_suffix}.{mech}.nc"
            outICON = chem_dir / f"{chem_dir}/ICON.{domain.id}.{domain.mcip_suffix}.{mech}.nc"
            ##
            if do_BCs and (not os.path.exists(outBCON)):
                all_files_exist = False
            ##
            if do_ICs and (not os.path.exists(outICON)):
                all_files_exist = False
            ##
        ##
        if all_files_exist:
            return

    ##
    for idate, date in enumerate(dates):
        do_ICs = idate == 0

        mcip_dir = nested_dir(domain, date, met_dir)
        chem_dir = nested_dir(domain, date, ctm_dir)

        ## check that the output directory exists - if not, create it
        os.makedirs(chem_dir, exist_ok=True)

        do_BCs = domain.index == domain.index == 1

        if not (do_ICs or do_BCs):
            continue

        mcip_suffix = domain.mcip_suffix
        croFile = mcip_dir / f"GRIDCRO2D_{mcip_suffix}"
        dotFile = mcip_dir / f"GRIDDOT2D_{mcip_suffix}"
        bdyFile = mcip_dir / f"GRIDBDY2D_{mcip_suffix}"
        metFile = mcip_dir / f"METCRO3D_{mcip_suffix}"
        srfFile = mcip_dir / f"METCRO2D_{mcip_suffix}"
        outBCON = chem_dir / f"BCON.{domain.id}.{domain.mcip_suffix}.{mech}.nc"
        outICON = chem_dir / f"ICON.{domain.id}.{domain.mcip_suffix}.{mech}.nc"

        if do_BCs:
            if os.path.exists(outBCON):
                os.remove(outBCON)
            shutil.copyfile(template_bcon_file, outBCON)
            print(f"copy {template_bcon_file} to {outBCON}")

        if do_ICs:
            if os.path.exists(outICON):
                os.remove(outICON)
            shutil.copyfile(template_icon_file, outICON)
            print(f"copy {template_icon_file} to {outICON}")

        print(dotFile)
        with (
            netCDF4.Dataset(croFile, "r", format="NETCDF4") as nccro,
            netCDF4.Dataset(bdyFile, "r", format="NETCDF4") as ncbdy,
            netCDF4.Dataset(metFile, "r", format="NETCDF4") as ncmet,
            netCDF4.Dataset(srfFile, "r", format="NETCDF4") as ncsrf,
            netCDF4.Dataset(input_cams_file, "r", format="NETCDF4") as ncin,
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
            MZdates = nc.num2date(ncin.variables["valid_time"][:], ncin.variables["valid_time"].getncattr("units"))
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
            itimes = numpy.where([t.date() == date for t in timesmod])[0]
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
                    dists = get_distance_from_lat_lon_in_km(
                        LAT[irow, icol], LON[irow, icol], LATMZ, LONMZ
                    )
                    minidx = numpy.argmin(dists)
                    ix, iy = numpy.unravel_index(minidx, LONMZ.shape)
                    near_interior[irow, icol, 0] = ix
                    near_interior[irow, icol, 1] = iy

            for iperim in range(LONP.shape[0]):
                dists = get_distance_from_lat_lon_in_km(LATP[iperim], LONP[iperim], LATMZ, LONMZ)
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
                            f"Species {spec} was not found in template CMAQ IC file "
                            f"-- creating blank variable..."
                        )
                        isnetcdf4 = ncouti.data_model == "NETCDF4"
                        ncouti.createVariable(
                            varname=spec,
                            datatype="f4",
                            dimensions=ncouti.variables[default_spec].dimensions,
                            zlib=isnetcdf4,
                        )
                        ncouti.long_name = f"{spec:16}"
                        ncouti.units = "{:16}".format("ppmV")
                        ncouti.var_desc = "{:80}".format("Variable " + spec)
                    ncouti.variables[spec][:] = 0.0
                if do_BCs:
                    if spec not in list(ncoutb.variables.keys()):
                        warnings.warn(
                            f"Species {spec} was not found in template CMAQ BC file "
                            f"-- creating blank variable..."
                        )
                        isnetcdf4 = ncoutb.data_model == "NETCDF4"
                        ncoutb.createVariable(
                            varname=spec,
                            datatype="f4",
                            dimensions=ncoutb.variables[default_spec].dimensions,
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
