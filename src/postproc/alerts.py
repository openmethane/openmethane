#
# Copyright 2025 The Superpower Institute Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import datetime
import gzip
import itertools
import multiprocessing
import os
import pathlib
import pickle

import numpy as np
import xarray as xr

from util.logger import get_logger
from util.netcdf import extract_bounds

ALERTS_MINIMUM_DATA = 1  # minimum data required to define alerts baseline

logger = get_logger(__name__)


def iterPickle(filename, compressed=True):
    with gzip.open(filename) if compressed else open(filename, "rb") as f:
        while True:
            try:
                yield pickle.load(f) # noqa: S301
            except EOFError:
                break


def read_obs_file(
    path: pathlib.Path,
    pop_keys: list | None = None,
) -> list:
    """read obs from file
    remove keys specified by pop_keys if present."""
    result = [_ for _ in iterPickle(path)]
    # throw away domain spec as first element
    result.pop(0)
    if pop_keys is not None:
        for b in result:
            for k in pop_keys:
                b.pop(k)
    return result


def get_obs_sim(
    dir: pathlib.Path | str,
    obs_file_template: str,
    sim_file_template: str,
):
    """
    reads obs and simulations from dir/obs_template_file and dir/sim_template_file,
    checks for consistency of coordinates
    """
    logger.debug(f"Loading observation data from {dir}")

    obs_path = pathlib.Path.joinpath(pathlib.Path(dir), obs_file_template)
    obs_list = read_obs_file(obs_path, pop_keys=["weight_grid"])
    sim_path = pathlib.Path.joinpath(pathlib.Path(dir), sim_file_template)
    sim_list = read_obs_file(sim_path, pop_keys=["weight_grid"])
    if len(sim_list) != len(obs_list):
        raise ValueError("inconsistent lenghts for obs and sim")

    period_start: datetime.datetime | None = None
    period_end: datetime.datetime | None = None

    for obs, sim in zip(obs_list, sim_list):
        if (period_start is None) or (period_start > obs["time"]):
            period_start = obs["time"]
        if (period_end is None) or (period_end < obs["time"]):
            period_end = obs["time"]
        if obs["lite_coord"] != sim["lite_coord"]:
            raise ValueError("inconsistent lite coord")
    return obs_list, sim_list, period_start, period_end


def calculate_baseline_statistics(
    near_fields_array: np.ndarray,
    far_fields_array: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """calculates baseline statistics of mean and standard deviation of
    local enhancement along with number of valid samples for each spatial point.
    """
    logger.info("calculating baseline statistics")
    # enforce types
    near_fields_array = np.array(near_fields_array)
    far_fields_array = np.array(far_fields_array)
    # check consistent masking
    if (np.isnan(near_fields_array) != np.isnan(far_fields_array)).any():
        raise ValueError("inconsistent masking of near and far fields")
    baseline_count = (~np.isnan(far_fields_array[:, 0, ...])).sum(axis=0)
    enhancement = near_fields_array - far_fields_array
    obs_baseline_mean_diff = np.nanmean(enhancement[:, 0, ...], axis=0)
    obs_baseline_std_diff = np.nanstd(enhancement[:, 0, ...], axis=0)
    sim_baseline_mean_diff = np.nanmean(enhancement[:, 1, ...], axis=0)
    sim_baseline_std_diff = np.nanstd(enhancement[:, 1, ...], axis=0)
    return (
        obs_baseline_mean_diff,
        obs_baseline_std_diff,
        sim_baseline_mean_diff,
        sim_baseline_std_diff,
        baseline_count,
    )


def create_alerts_baseline( # noqa: PLR0913
    domain_file: pathlib.Path,
    dir_list: list[str],
    obs_file_template: str = "input/test_obs.pic.gz",
    sim_file_template: str = "simulobs.pic.gz",
    near_threshold: float = 0.2,
    far_threshold: float = 1.0,
    output_file: str = "alerts_baseline.nc",
):
    """
    Constructs a baseline for alerts. The baseline consists of a mean and
    standard deviation for the differences between obs and simulation at each
    point in the domain. Output is stored as a netcdf file.

    :param domain_file: netcdf file describing the domain, will be used to
        template the output.
    :param dir_list: list of directories containing obs and simulation outputs
        as ObservationData.
    :param obs_file_template: string to be appended to each dir in dir_list to
        point to observations
    :param sim_file_template: string to be appended to each dir in dir_list to
        point to simulations
    :param near_threshold: distance from the target cell to be included in the
        near field
    :param far_threshold: distance from the target cell to be included in the
        far field
    :param output_file: name of output_file, will be overwritten if exists
    :return:
    """
    with xr.open_dataset(domain_file) as ds:
        logger.debug(f"Domain found at {domain_file}")

        domain_ds = ds.load()

        domain_size_x = domain_ds.sizes["COL"]
        domain_size_y = domain_ds.sizes["ROW"]

        lats = domain_ds["LAT"].to_numpy().squeeze()
        lons = domain_ds["LON"].to_numpy().squeeze()
        land_mask = domain_ds["LANDMASK"].to_numpy().squeeze()
    near_fields = []
    far_fields = []

    logger.info(f"Creating alerts baseline from {len(dir_list)} observations")

    obs_period_start: datetime.datetime | None = None
    obs_period_end: datetime.datetime | None = None

    for dir in dir_list:
        obs_list, sim_list, period_start, period_end = get_obs_sim(
            dir, obs_file_template, sim_file_template
        )
        obs_sim = [
            (
                o["latitude_center"],
                o["longitude_center"],
                o["value"],
                s["value"],
            )
            for o, s in zip(obs_list, sim_list)
        ]
        obs_sim_array = np.array(obs_sim)
        near, far = map_enhance(lats, lons, land_mask, obs_sim_array, near_threshold, far_threshold)
        near_fields.append(near)
        far_fields.append(far)

        # record the dates of the first and last observation being examined
        if (obs_period_start is None) or (obs_period_start > period_start):
            obs_period_start = period_start
        if (obs_period_end is None) or (obs_period_end < period_end):
            obs_period_end = period_end

    logger.info("Constructing near_fields_array")
    near_fields_array = np.array(near_fields)

    logger.info("Constructing far_fields_array")
    far_fields_array = np.array(far_fields)

    (
        obs_baseline_mean_diff,
        obs_baseline_std_diff,
        sim_baseline_mean_diff,
        sim_baseline_std_diff,
        baseline_count,
    ) = calculate_baseline_statistics(near_fields_array, far_fields_array)

    # observations have specific times, but represent all the observations
    # that were available for the entire day, so make the period the full day
    baseline_period_start = obs_period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    # end of day
    baseline_period_end = obs_period_end.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=1)

    # create a variable with projection coordinates
    projection_x = (
        domain_ds.XORIG + (0.5 * domain_ds.XCELL) + np.arange(domain_size_x) * domain_ds.XCELL
    )
    projection_y = (
        domain_ds.YORIG + (0.5 * domain_ds.YCELL) + np.arange(domain_size_y) * domain_ds.YCELL
    )

    logger.info("Creating dataset")
    # copy dimensions and attributes from the domain, as the alerts should be
    # provided in the same grid / format
    alerts_baseline_ds = xr.Dataset(
        data_vars={
            # meta data
            "lat": (
                ("y", "x"),
                domain_ds.variables["LAT"][0],
                {
                    "long_name": "latitude",
                    "units": "degrees_north",
                    "standard_name": "latitude",
                    "bounds": "lat_bounds",
                },
            ),
            "lon": (
                ("y", "x"),
                domain_ds.variables["LON"][0],
                {
                    "long_name": "longitude",
                    "units": "degrees_east",
                    "standard_name": "longitude",
                    "bounds": "lon_bounds",
                },
            ),
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#cell-boundaries
            "lat_bounds": (
                ("y", "x", "cell_corners"),
                extract_bounds(domain_ds.variables["LATD"][0][0]),
            ),
            "lon_bounds": (
                ("y", "x", "cell_corners"),
                extract_bounds(domain_ds.variables["LOND"][0][0]),
            ),
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#_lambert_conformal
            "grid_projection": (
                (),
                False,
                {
                    "grid_mapping_name": "lambert_conformal_conic",
                    "standard_parallel": (domain_ds.TRUELAT1, domain_ds.TRUELAT2),
                    "longitude_of_central_meridian": domain_ds.STAND_LON,
                    "latitude_of_projection_origin": domain_ds.MOAD_CEN_LAT,
                },
            ),
            "projection_x": (
                ("x"),
                projection_x,
                {
                    "long_name": "x coordinate of projection",
                    "units": "m",
                    "standard_name": "projection_x_coordinate",
                },
            ),
            "projection_y": (
                ("y"),
                projection_y,
                {
                    "long_name": "y coordinate of projection",
                    "units": "m",
                    "standard_name": "projection_y_coordinate",
                },
            ),
            "time_bounds": (("time", "bounds_t"), [[baseline_period_start, baseline_period_end]]),
            # copied data
            "landmask": (
                ("y", "x"),
                domain_ds.variables["LANDMASK"][0],
                {
                    "long_name": domain_ds.variables["LANDMASK"].attrs["var_desc"],
                    "standard_name": "land_binary_mask",
                },
            ),
            # baseline data
            "obs_baseline_mean_diff": (
                ("time", "y", "x"),
                [obs_baseline_mean_diff],
                {
                    "long_name": "Average observed difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                },
            ),
            "obs_baseline_std_diff": (
                ("time", "y", "x"),
                [obs_baseline_std_diff],
                {
                    "long_name": "Standard deviation of observed difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                },
            ),
            "sim_baseline_mean_diff": (
                ("time", "y", "x"),
                [sim_baseline_mean_diff],
                {
                    "long_name": "Average simulated difference between near and far field concentrations'", # noqa: E501
                    "units": "1e-9",
                },
            ),
            "sim_baseline_std_diff": (
                ("time", "y", "x"),
                [sim_baseline_std_diff],
                {
                    "long_name": "Standard deviation of simulated difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                },
            ),
            "baseline_count": (
                ("time", "y", "x"),
                [baseline_count],
                {
                    "long_name": "number of observations in baseline",
                    "units": "1",
                },
            ),
        },
        coords={
            "x": np.arange(domain_size_x),
            "y": np.arange(domain_size_y),
            "time": (("time"), [baseline_period_start], {"bounds": "time_bounds"}),
        },
        attrs={
            "DX": domain_ds.DX,
            "DY": domain_ds.DY,
            "XCELL": domain_ds.XCELL,
            "YCELL": domain_ds.YCELL,
            "alerts_near_threshold": near_threshold,
            "alerts_far_threshold": far_threshold,
            # common
            "title": "Open Methane methane alerts baseline",
            "openmethane_version": os.getenv("OPENMETHANE_VERSION", "development"),
            "history": "",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {baseline_period_start.strftime('%Y-%m-%d')}"
    alerts_baseline_ds.time.encoding["units"] = time_encoding
    alerts_baseline_ds.time_bounds.encoding["units"] = time_encoding

    logger.info(f"Writing alerts baseline to {output_file}")
    alerts_baseline_ds.to_netcdf(output_file)


def create_alerts( # noqa: PLR0913
    baseline_file: pathlib.Path,
    daily_dir: pathlib.Path,
    obs_file_template: str = "input/test_obs.pic.gz",
    sim_file_template: str = "simulobs.pic.gz",
    output_file: str = "alerts.nc",
    alerts_threshold: float = 0.0,
    significance_threshold: float = 1.0,
    count_threshold: int = 30,
):
    """
    Construct alerts.
    The baseline consists of a mean and standard deviation for local enhancement
    where the mean is based on simulations and the standard deviation on
    observations. For the alert we consider whether the observed local
    enhancement lies outside the confidence interval defined by the mean and
    standard deviation and outside the confidence interval defined by the mean
    and threshold at each point in the domain.

    Output is stored as a netcdf file, which will contain nans wherever an
    alert cannot be defined (usually no obs), 0 for no alert and 1 for an alert.

    :param baseline_file: netcdf file describing the baseline (see function
        create_alerts_baseline). will be used to template the output.
    :param daily_dir: directory containing obs and simulation outputs as
        ObservationData.
    :param obs_file_template: string to be appended to daily_dir to point to
        observations
    :param sim_file_template: string to be appended to daily_dir to point to
        simulations
    :param output_file: name of output_file, will be overwritten if exists
    :param alerts_threshold: the minimum delta between the baseline and the
        observed concentration for an alert to be generated for a cell.
    :param significance_threshold: controls how much standard deviation is
        considered when generating alerts.
    :param count_threshold: the minimum observation count in the baseline for
        alerts to be generated for a cell
    """
    with xr.open_dataset(baseline_file) as ds:
        logger.debug(f"Alerts baseline found at {baseline_file}")

        alerts_baseline_ds = ds.load()
        n_cols = alerts_baseline_ds.sizes["x"]
        n_rows = alerts_baseline_ds.sizes["y"]
        resultShape = (n_rows, n_cols)
        lats = alerts_baseline_ds["lat"].to_numpy().squeeze()
        lons = alerts_baseline_ds["lon"].to_numpy().squeeze()
        land_mask = alerts_baseline_ds["landmask"].to_numpy().squeeze()
        baseline_mean = alerts_baseline_ds["sim_baseline_mean_diff"].to_numpy().squeeze()
        baseline_std = alerts_baseline_ds["obs_baseline_std_diff"].to_numpy().squeeze()
        baseline_count = alerts_baseline_ds["baseline_count"].to_numpy().squeeze()

        near_threshold = alerts_baseline_ds.attrs["alerts_near_threshold"]
        far_threshold = alerts_baseline_ds.attrs["alerts_far_threshold"]
        ds.close()

    obs_list, sim_list, obs_period_start, obs_period_end = get_obs_sim(
        daily_dir, obs_file_template, sim_file_template
    )
    obs_sim = [
        (
            o["latitude_center"],
            o["longitude_center"],
            o["value"],
            s["value"],
        )
        for o, s in zip(obs_list, sim_list)
    ]
    obs_sim_array = np.array(obs_sim)

    near, far = map_enhance(lats, lons, land_mask, obs_sim_array, near_threshold, far_threshold)
    enhancement = near - far
    obs_enhancement = enhancement[0, ...]
    alerts = np.zeros(resultShape)
    alerts[...] = np.nan
    # first construct mask for points we cannot calcolate alert, either no baseline or no obs
    undefined_mask = (
        np.isnan(obs_enhancement)
        | np.isnan(baseline_mean)
        | np.isnan(baseline_std)
        | (baseline_count < count_threshold)
    )
    defined_mask = ~undefined_mask
    # now calculate alerts only where defined
    alerts[defined_mask] = (
        (
            np.abs(obs_enhancement - baseline_mean)[defined_mask]
            > significance_threshold * baseline_std[defined_mask]
        )
        & (np.abs(obs_enhancement - baseline_mean)[defined_mask] > alerts_threshold)
    ).astype("float")

    logger.info(f"Writing alerts to {output_file}")

    # observations have specific times, but represent all the observations
    # that were available for the entire day, so make the period the full day
    period_start = obs_period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    # end of day
    period_end = obs_period_end.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=1)

    # copy dimensions and attributes from the alerts baseline, as the alerts
    # should be provided in the same grid / format
    alerts_ds = xr.Dataset(
        data_vars={
            # meta data
            "lat": alerts_baseline_ds.variables["lat"],
            "lon": alerts_baseline_ds.variables["lon"],
            "lat_bounds": alerts_baseline_ds.variables["lat_bounds"],
            "lon_bounds": alerts_baseline_ds.variables["lon_bounds"],
            "grid_projection": alerts_baseline_ds.variables["grid_projection"],
            "projection_x": alerts_baseline_ds.variables["projection_x"],
            "projection_y": alerts_baseline_ds.variables["projection_y"],
            # record the time bounds of this alert period
            "time_bounds": (("time", "bounds_t"), [[period_start, period_end]]),
            # copied data
            "landmask": alerts_baseline_ds.variables["landmask"],
            "obs_baseline_mean_diff": alerts_baseline_ds.variables["obs_baseline_mean_diff"],
            "obs_baseline_std_diff": alerts_baseline_ds.variables["obs_baseline_std_diff"],
            "sim_baseline_mean_diff": alerts_baseline_ds.variables["sim_baseline_mean_diff"],
            "sim_baseline_std_diff": alerts_baseline_ds.variables["sim_baseline_std_diff"],
            "baseline_count": alerts_baseline_ds.variables["baseline_count"],
            # results data
            "alerts": (
                ("time", "y", "x"),
                [alerts],
                {
                    "long_name": "Boolean flag for anomalous concentration",
                    "missing_value": np.nan,
                },
            ),
            "obs_enhancement": (
                ("time", "y", "x"),
                [obs_enhancement],
                {
                    "long_name": "Difference between near and far field concentrations",
                    "units": "1e-9",
                },
            ),
        },
        coords={
            "x": alerts_baseline_ds.coords["x"],
            "y": alerts_baseline_ds.coords["y"],
            "time": (("time"), [period_start], {"bounds": "time_bounds"}),
        },
        attrs={
            "DX": alerts_baseline_ds.DX,
            "DY": alerts_baseline_ds.DY,
            "XCELL": alerts_baseline_ds.XCELL,
            "YCELL": alerts_baseline_ds.YCELL,
            "alerts_near_threshold": alerts_baseline_ds.alerts_near_threshold,
            "alerts_far_threshold": alerts_baseline_ds.alerts_far_threshold,
            "alerts_threshold": alerts_threshold,
            "alerts_significance_threshold": significance_threshold,
            "alerts_count_threshold": count_threshold,
            # common
            "title": "Open Methane daily methane alerts",
            "openmethane_version": os.getenv("OPENMETHANE_VERSION", "development"),
            "history": "",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {period_start.strftime('%Y-%m-%d')}"
    alerts_ds.time.encoding["units"] = time_encoding
    alerts_ds.time_bounds.encoding["units"] = time_encoding

    alerts_ds.to_netcdf(output_file)


def map_enhance(lat, lon, land_mask, concs, nearThreshold, farThreshold): # noqa: PLR0913
    logger.debug("Calculating enhancements in map_enhance")
    nConcs = concs.shape[1] - 2  # number of concentration records, the -2 removes lat,lon
    n_rows = land_mask.shape[0]
    n_cols = land_mask.shape[1]
    resultShape = (nConcs, n_rows, n_cols)
    near_field = np.zeros(resultShape)
    near_field[...] = np.nan
    far_field = np.zeros(resultShape)
    far_field[...] = np.nan

    # now build the input queue for multiprocessing points
    logger.debug(f"Building input_proc_list for shape {resultShape}")
    input_proc_list = []
    for i, j in itertools.product(range(0, n_rows, 1), range(0, n_cols, 1)):
        if land_mask[i, j] > 0.5:  # land point
            input_proc_list.append((i, j, lat, lon, land_mask, concs, nearThreshold, farThreshold))

    nCPUs = int(os.environ.get("NCPUS", "1"))
    logger.debug(f"Spawning {nCPUs} processes")
    with multiprocessing.Pool(nCPUs) as pool:
        processOutput = pool.imap_unordered(point_enhance, input_proc_list)
        for obs in processOutput:
            i, j = obs[0:2]
            near_field[:, i, j], far_field[:, i, j] = obs[2:]
    return near_field, far_field


def point_enhance(val):
    i, j, lat, lon, land_mask, concs, nearThreshold, farThreshold = val

    if land_mask[i, j] < 0.5:  # ocean point
        return i, j, np.nan, np.nan
    else:
        dist = calc_dist(concs, (lat[i, j], lon[i, j]))
        near = dist < nearThreshold
        far = (dist > nearThreshold) & (dist < farThreshold)
        nearCount = near.sum()
        farCount = far.sum()
        if (nearCount == 0) or (farCount == 0):
            return i, j, np.nan, np.nan
        else:
            near_field = concs[near, 2:].mean(axis=0)
            far_field = concs[far, 2:].mean(axis=0)
            return i, j, near_field, far_field


def calc_dist(concs, loc):
    diff = concs[:, 0:2] - np.array(loc)
    dist = (diff[:, 0] ** 2 + diff[:, 1] ** 2) ** 0.5
    return dist
