"""Interpolate the from the global CAMS CTM output to ICs and BCs for CMAQ"""

import datetime
import itertools
import os
import pathlib
import shutil
import warnings

import netCDF4
import numpy
from scipy.spatial import cKDTree

from openmethane.cmaq_preprocess.cams_readers import open_cams
from openmethane.cmaq_preprocess.read_config_cmaq import Domain
from openmethane.cmaq_preprocess.utils import nested_dir


def _unit_vectors(lat, lon):
    lat = numpy.deg2rad(numpy.asarray(lat, dtype=float).ravel())
    lon = numpy.deg2rad(numpy.asarray(lon, dtype=float).ravel())
    return numpy.column_stack(
        (numpy.cos(lat) * numpy.cos(lon), numpy.cos(lat) * numpy.sin(lon), numpy.sin(lat))
    )


def nearest_points(grid_lat, grid_lon, lat, lon):
    """Index of the nearest grid point to each point, by great-circle distance

    The straight-line distance between points on a sphere increases with the
    great-circle distance, so a KD-tree over unit vectors finds the same neighbours
    as comparing great-circle distances to every grid point, in a fraction of the time.

    Raises an error if any point is further from its nearest grid point than 1.5 grid
    cell diagonals, which suggests the CAMS file was cut to a different domain.

    Args:
        grid_lat, grid_lon: latitude and longitude of the grid points, 2D
        lat, lon: latitude and longitude of the points to look up, any matching shape

    Returns:
        Indices into the flattened grid, with the shape of `lat`
    """
    grid = _unit_vectors(grid_lat, grid_lon)
    distance, index = cKDTree(grid).query(_unit_vectors(lat, lon))
    corners = grid.reshape(*numpy.shape(grid_lat), 3)
    max_diagonal = numpy.linalg.norm(corners[1:, 1:] - corners[:-1, :-1], axis=-1).max()
    if distance.max() > 1.5 * max_diagonal:
        raise ValueError(
            "Some points are more than one and a half cell diagonals from the grid, so the "
            "grid does not cover them. A CAMS file cut for another domain does this."
        )
    return index.reshape(numpy.shape(lat))


def cmaq_layer_pressures(psurf, sigma, mtop):
    """Mid-layer pressures of CMAQ columns

    Args:
        psurf: surface pressure (Pa) of each column, any shape
        sigma: sigma values of the layer interfaces, length LAY + 1
        mtop: model top pressure (Pa)

    Returns:
        Pressures (Pa) with shape (LAY, *psurf.shape)
    """
    psurf = numpy.asarray(psurf, dtype=float)
    sigma = numpy.asarray(sigma, dtype=float).reshape((-1,) + (1,) * psurf.ndim)
    interfaces = (psurf - mtop) * sigma + mtop
    return (interfaces[1:] + interfaces[:-1]) / 2.0


def interpolate_columns(profile, ix, iy, cmaq_pressure):
    """Interpolate CAMS columns onto the layers of CMAQ columns

    Each CMAQ column takes the CAMS column of its nearest cell, with the CAMS levels
    placed at that cell's own pressures, and is interpolated linearly in log-pressure to
    the column's own CMAQ layer pressures. Values beyond the CAMS levels take the
    nearest level.

    Args:
        profile: CamsProfile of the CAMS grid at one time
        ix, iy: CAMS lat and lon indices of the nearest cell to each CMAQ column, shape (N,)
        cmaq_pressure: CMAQ mid-layer pressures (Pa), shape (LAY, N)

    Returns:
        CH4 in ppmV, shape (LAY, N)
    """
    columns = numpy.asarray(profile.ch4_ppmv[:, ix, iy], dtype=float)
    log_cams = numpy.log(profile.pressure_pa[:, ix, iy])
    log_cmaq = numpy.log(cmaq_pressure)
    # np.interp wants increasing x, and the levels run in either direction
    if log_cams[0, 0] > log_cams[-1, 0]:
        columns, log_cams = columns[::-1], log_cams[::-1]
    out = numpy.empty(cmaq_pressure.shape, dtype=numpy.float32)
    for column in range(cmaq_pressure.shape[1]):
        out[:, column] = numpy.interp(log_cmaq[:, column], log_cams[:, column], columns[:, column])
    return out


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


def ioapi_datetime(yyyyddd: int, hhmmss: int) -> datetime.datetime:
    """The time of an I/O API TFLAG pair"""
    return datetime.datetime.strptime(f"{int(yyyyddd):07d}", "%Y%j") + datetime.timedelta(
        hours=int(hhmmss) // 10000, minutes=int(hhmmss) // 100 % 100, seconds=int(hhmmss) % 100
    )


def as_datetimes(times) -> list[datetime.datetime]:
    """CAMS times, which netCDF4 returns as cftime, as plain datetimes"""
    return [datetime.datetime(t.year, t.month, t.day, t.hour, t.minute, t.second) for t in times]


def index_at_or_before(times: list[datetime.datetime], time: datetime.datetime) -> int:
    """Index of the latest of `times` at or before `time`

    If every one of `times` is later, the nearest is used with a warning.
    """
    earlier = [i for i, t in enumerate(times) if t <= time]
    if earlier:
        return earlier[-1]
    warnings.warn(
        f"All CAMS times are after {time:%Y-%m-%d %H:%M:%S}, using the nearest: "
        f"{times[0]:%Y-%m-%d %H:%M:%S}"
    )
    return 0


def bcon_record_times(
    date: datetime.date, cams_times: list[datetime.datetime]
) -> list[datetime.datetime]:
    """Times of the BCON records for one day, at the CAMS time step from 00:00 to 24:00

    The step is the shortest interval between CAMS times, so the records fall on the
    CAMS times themselves: 3-hourly for EAC4, 6-hourly for the inversion and the
    forecasts. A file with a single time gives records at 00:00 and 24:00 only. The
    24:00 record lets CMAQ interpolate up to the end of the day, as it requires.
    """
    times = sorted(set(cams_times))
    gaps = numpy.array([(b - a).total_seconds() for a, b in itertools.pairwise(times)])
    step = int(gaps.min()) if gaps.size else 86400
    if 86400 % step:
        raise ValueError(
            f"The CAMS time step of {step / 3600:g} hours does not divide a day, so the "
            "BCON records cannot start and end at midnight"
        )
    start = datetime.datetime.combine(date, datetime.time())
    return [start + datetime.timedelta(seconds=s) for s in range(0, 86400 + step, step)]


def write_bcon(
    template_bcon_file: pathlib.Path,
    output_file: pathlib.Path,
    times: list[datetime.datetime],
    species: dict[str, numpy.ndarray],
    attrs: dict | None = None,
):
    """Write a time-stepped BCON file with the layout and attributes of the template

    The template from CMAQ's BCON tool in profile mode is time-independent
    (TSTEP = 0) with a single record. The output has one record per time, with
    SDATE, STIME, TSTEP and TFLAG set to match. Species not given keep the
    template's record at every time.

    Args:
        template_bcon_file: BCON file made by CMAQ's BCON tool
        output_file: path of the BCON file to write
        times: time of each record, evenly spaced
        species: values of each species to write, shape (time, LAY, PERIM)
        attrs: global attributes to add
    """
    step = int((times[1] - times[0]).total_seconds()) if len(times) > 1 else 0
    if any((b - a).total_seconds() != step for a, b in itertools.pairwise(times)):
        raise ValueError("BCON records must be evenly spaced")

    def hhmmss(seconds):
        return seconds // 3600 * 10000 + seconds // 60 % 60 * 100 + seconds % 60

    with (
        netCDF4.Dataset(template_bcon_file, "r") as template,
        netCDF4.Dataset(output_file, "w", format=template.data_model) as output,
    ):
        missing = set(species) - set(template.variables)
        if missing:
            raise ValueError(
                f"{template_bcon_file} has no {', '.join(sorted(missing))}; "
                "make the template with a mechanism that includes it"
            )
        for name, dimension in template.dimensions.items():
            output.createDimension(name, None if name == "TSTEP" else len(dimension))
        output.setncatts({name: template.getncattr(name) for name in template.ncattrs()})
        output.setncatts(
            {
                "SDATE": numpy.int32(int(times[0].strftime("%Y%j"))),
                "STIME": numpy.int32(int(times[0].strftime("%H%M%S"))),
                "TSTEP": numpy.int32(hhmmss(step)),
                **(attrs or {}),
            }
        )
        for name, variable in template.variables.items():
            out = output.createVariable(
                name, variable.dtype, variable.dimensions, zlib=template.data_model == "NETCDF4"
            )
            out.setncatts({attr: variable.getncattr(attr) for attr in variable.ncattrs()})
            if name == "TFLAG":
                flags = [[int(t.strftime("%Y%j")), int(t.strftime("%H%M%S"))] for t in times]
                out[:] = numpy.repeat(
                    numpy.array(flags, dtype=numpy.int32)[:, numpy.newaxis, :],
                    len(template.dimensions["VAR"]),
                    axis=1,
                )
            elif name in species:
                out[:] = species[name]
            else:
                out[:] = numpy.repeat(variable[:1], len(times), axis=0)


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
    cams_product="eac4",
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
        cams_product: "eac4" if input_cams_file is the CAMS reanalysis, "inversion" if it
            is the CAMS inversion cut by `download_cams_input.py`, or "forecasts" if it is
            the CAMS greenhouse gas forecasts cut by `download_cams_input.py`

    Returns:
        Nothing

    """
    with open_cams(input_cams_file, cams_product) as cams:
        cams.require_dates(dates)

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
            open_cams(input_cams_file, cams_product) as cams,
        ):
            if do_ICs:
                print("write ICs to file: ", outICON)
                ncouti = netCDF4.Dataset(outICON, "r+", format="NETCDF4")

            nlay = len(ncmet.dimensions["LAY"])
            LAT = nccro.variables["LAT"][:].squeeze()
            LON = nccro.variables["LON"][:].squeeze()
            LATP = ncbdy.variables["LAT"][:].squeeze()
            LONP = ncbdy.variables["LON"][:].squeeze()
            sigma = ncmet.getncattr("VGLVLS")
            mtop = ncmet.getncattr("VGTOP")
            cams_times = as_datetimes(cams.times)
            latmz = cams.lat
            lonmz = cams.lon
            PSURF = ncsrf.variables["PRSFC"][:].squeeze()
            # the index of each MCIP time, which runs hourly from 00:00 to 24:00
            mcip_index = {
                ioapi_datetime(*flag): i for i, flag in enumerate(ncsrf.variables["TFLAG"][:, 0, :])
            }
            day_start = datetime.datetime.combine(date, datetime.time())
            if day_start not in mcip_index:
                raise ValueError(f"{srfFile} has no record at {day_start}")

            cams_attrs = {"CAMS_PRODUCT": cams.product}
            if cams.release:
                cams_attrs["CAMS_RELEASE"] = cams.release

            LATMZ, LONMZ = numpy.meshgrid(latmz, lonmz, indexing="ij")
            Factor = 1.0e3  ## convert from ppm to ppb
            ##
            if do_ICs:
                spec = "CH4"
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

                near_interior = numpy.stack(
                    numpy.unravel_index(nearest_points(LATMZ, LONMZ, LAT, LON), LATMZ.shape),
                    axis=-1,
                )
                layer_pressure = cmaq_layer_pressures(
                    PSURF[mcip_index[day_start]].ravel(), sigma, mtop
                )
                out_interior = interpolate_columns(
                    cams.profile(index_at_or_before(cams_times, day_start)),
                    near_interior[..., 0].ravel(),
                    near_interior[..., 1].ravel(),
                    layer_pressure,
                ).reshape((nlay, *LON.shape))
                out_interior += bias_correct
                print_interior_variable("CH4", out_interior, Factor)
                populate_interior_variable(ncouti, "CH4", out_interior, 1.0)
                ncouti.setncatts(cams_attrs)
                ncouti.close()
            ##
            if do_BCs:
                print("write BCs to file: ", outBCON)
                near_boundary = numpy.stack(
                    numpy.unravel_index(nearest_points(LATMZ, LONMZ, LATP, LONP), LATMZ.shape),
                    axis=-1,
                )
                # a perimeter point takes the surface pressure of its nearest CMAQ cell
                perimeter_cell = nearest_points(LAT, LON, LATP, LONP)
                record_times = bcon_record_times(date, cams_times)
                out_boundary = numpy.empty((len(record_times), nlay, len(LATP)), numpy.float32)
                for irec, time in enumerate(record_times):
                    if time not in mcip_index:
                        raise ValueError(f"{srfFile} has no record at {time}")
                    perimeter_psurf = PSURF[mcip_index[time]].ravel()[perimeter_cell]
                    # the latest CAMS time at or before the record, which holds the last
                    # CAMS time over the end of a file that stops before 24:00
                    out_boundary[irec] = interpolate_columns(
                        cams.profile(index_at_or_before(cams_times, time)),
                        near_boundary[:, 0],
                        near_boundary[:, 1],
                        cmaq_layer_pressures(perimeter_psurf, sigma, mtop),
                    )
                out_boundary += bias_correct
                print_boundary_variable("CH4", out_boundary, Factor)
                if os.path.exists(outBCON):
                    os.remove(outBCON)
                write_bcon(
                    template_bcon_file,
                    outBCON,
                    record_times,
                    {"CH4": numpy.fmax(out_boundary, 1.0e-30)},
                    attrs=cams_attrs,
                )
