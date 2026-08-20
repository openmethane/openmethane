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
import contextlib
import datetime
import gzip
import multiprocessing
import os
import pathlib
import pickle

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

from openmethane.util.cf import get_grid_mappings
from openmethane.util.logger import get_logger
from openmethane.util.system import get_timestamped_command, get_version

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
    records = iterPickle(path)
    # throw away domain spec as first element
    next(records)
    if pop_keys is None:
        return list(records)
    # drop the unwanted keys as each record arrives rather than afterwards, so
    # the discarded values are never all resident at once. weight_grid alone is
    # about two thirds of an observation record.
    result = []
    for record in records:
        for k in pop_keys:
            record.pop(k)
        result.append(record)
    return result


def get_obs_sim(
    dir: pathlib.Path | str,
    obs_file_template: str,
    sim_file_template: str,
):
    """
    reads obs and simulations from dir/obs_template_file and dir/sim_template_file,
    checks for consistency of coordinates

    Returns a row per observation of (latitude, longitude, observed value,
    simulated value), along with the period the observations cover. Only these
    fields are needed downstream, so the full records are not retained.
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

    obs_sim = np.empty((len(obs_list), 4))
    for n, (obs, sim) in enumerate(zip(obs_list, sim_list)):
        if (period_start is None) or (period_start > obs["time"]):
            period_start = obs["time"]
        if (period_end is None) or (period_end < obs["time"]):
            period_end = obs["time"]
        if obs["lite_coord"] != sim["lite_coord"]:
            raise ValueError("inconsistent lite coord")
        obs_sim[n] = (
            obs["latitude_center"],
            obs["longitude_center"],
            obs["value"],
            sim["value"],
        )
    return obs_sim, period_start, period_end


def calculate_baseline_statistics(
    near_fields_array: np.ndarray,
    far_fields_array: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """calculates baseline statistics of mean and standard deviation of
    local enhancement along with number of valid samples for each spatial point.
    """
    logger.info("calculating baseline statistics")
    # enforce types, without copying arrays that are already the right type
    near_fields_array = np.asarray(near_fields_array)
    far_fields_array = np.asarray(far_fields_array)
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


def _day_enhancement(task):
    """
    Near and far fields for a single day, as a worker for create_alerts_baseline.
    Takes its arguments as one tuple so it can be used with multiprocessing.
    """
    (
        dir,
        obs_file_template,
        sim_file_template,
        lats,
        lons,
        land_mask,
        near_threshold,
        far_threshold,
    ) = task
    obs_sim, period_start, period_end = get_obs_sim(dir, obs_file_template, sim_file_template)
    near, far = map_enhance(lats, lons, land_mask, obs_sim, near_threshold, far_threshold)
    return near, far, period_start, period_end


def create_alerts_baseline( # noqa: PLR0913
    domain_file: pathlib.Path,
    dir_list: list[str],
    obs_file_template: str = "input/test_obs.pic.gz",
    sim_file_template: str = "simulobs.pic.gz",
    near_threshold: float = 0.2,
    far_threshold: float = 1.0,
    output_file: str = "alerts-baseline.nc",
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

        lats = domain_ds["lat"].to_numpy().squeeze()
        lons = domain_ds["lon"].to_numpy().squeeze()
        land_mask = domain_ds["land_mask"].to_numpy().squeeze()
    near_fields = []
    far_fields = []

    logger.info(f"Creating alerts baseline from {len(dir_list)} days of observations")

    obs_period_start: datetime.datetime | None = None
    obs_period_end: datetime.datetime | None = None

    tasks = [
        (dir, obs_file_template, sim_file_template, lats, lons, land_mask, near_threshold,
         far_threshold)
        for dir in dir_list
    ]

    # Each day is independent and reading its observations dominates its cost,
    # so the days are what is worth spreading over NCPUS. Only the two field
    # arrays come back from each worker, which keeps the data sent between
    # processes proportional to the number of days rather than to the work done.
    # Don't use more CPUs than there are days to process.
    n_cpus = max(1, min(int(os.environ.get("NCPUS", "1")), len(dir_list)))
    logger.debug(f"Calculating daily enhancements using {n_cpus} process(es)")

    # Use ExitStack to enter multiple contexts, and make sure they all get
    # cleaned up properly, even in the event of exceptions or signals.
    with contextlib.ExitStack() as stack:
        if n_cpus > 1:
            pool = stack.enter_context(multiprocessing.Pool(n_cpus))
            # imap keeps the results in dir_list order, so the baseline is
            # reproducible regardless of the order the days finish in
            results = pool.imap(_day_enhancement, tasks)
        else:
            results = map(_day_enhancement, tasks)

        for near, far, period_start, period_end in results:
            near_fields.append(near)
            far_fields.append(far)

            # record the dates of the first and last observation being examined
            if (obs_period_start is None) or (obs_period_start > period_start):
                obs_period_start = period_start
            if (obs_period_end is None) or (obs_period_end < period_end):
                obs_period_end = period_end

    logger.info("Constructing near_fields_array")
    near_fields_array = np.stack(near_fields)
    near_fields.clear()

    logger.info("Constructing far_fields_array")
    far_fields_array = np.stack(far_fields)
    far_fields.clear()

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

    # the domain typically has only one grid mapping, which applies to vars
    # with y, x coords
    projection_var_name = get_grid_mappings(domain_ds)[0]

    logger.info("Creating dataset")
    # copy dimensions and attributes from the domain, as the alerts should be
    # provided in the same grid / format
    alerts_baseline_ds = xr.Dataset(
        coords={
            "x": domain_ds.coords["x"],
            "y": domain_ds.coords["y"],
            "time": (("time"), [baseline_period_start], {
                "standard_name": "time",
                "bounds": "time_bounds",
            }),
        },
        data_vars={
            # bounds
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#cell-boundaries
            "x_bounds": domain_ds.variables["x_bounds"],
            "y_bounds": domain_ds.variables["y_bounds"],
            "time_bounds": (("time", "bounds_t"), [[baseline_period_start, baseline_period_end]]),

            # georeferencing
            "lat": domain_ds.variables["lat"],
            "lon": domain_ds.variables["lon"],
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#_lambert_conformal
            projection_var_name: domain_ds.variables[projection_var_name],

            # copied data
            "land_mask": domain_ds.variables["land_mask"],

            # baseline data
            "obs_baseline_mean_diff": (
                ("time", "y", "x"),
                [obs_baseline_mean_diff],
                {
                    "long_name": "Average observed difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                    "grid_mapping": projection_var_name,
                },
            ),
            "obs_baseline_std_diff": (
                ("time", "y", "x"),
                [obs_baseline_std_diff],
                {
                    "long_name": "Standard deviation of observed difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                    "grid_mapping": projection_var_name,
                },
            ),
            "sim_baseline_mean_diff": (
                ("time", "y", "x"),
                [sim_baseline_mean_diff],
                {
                    "long_name": "Average simulated difference between near and far field concentrations'", # noqa: E501
                    "units": "1e-9",
                    "grid_mapping": projection_var_name,
                },
            ),
            "sim_baseline_std_diff": (
                ("time", "y", "x"),
                [sim_baseline_std_diff],
                {
                    "long_name": "Standard deviation of simulated difference between near and far field concentrations", # noqa: E501
                    "units": "1e-9",
                    "grid_mapping": projection_var_name,
                },
            ),
            "baseline_count": (
                ("time", "y", "x"),
                [baseline_count],
                {
                    "long_name": "number of observations in baseline",
                    "units": "1",
                    "grid_mapping": projection_var_name,
                },
            ),
        },
        attrs={
            "DX": domain_ds.DX,
            "DY": domain_ds.DY,
            "XCELL": domain_ds.XCELL,
            "YCELL": domain_ds.YCELL,
            "alerts_near_threshold": near_threshold,
            "alerts_far_threshold": far_threshold,

            # domain
            "domain_name": domain_ds.domain_name,
            "domain_version": domain_ds.domain_version,
            "domain_slug": domain_ds.domain_slug,

            # common
            "title": "Open Methane methane alerts baseline",
            "history": get_timestamped_command(),
            "openmethane_version": get_version(),

            "Conventions": "CF-1.12",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {baseline_period_start.strftime('%Y-%m-%d')}"
    alerts_baseline_ds.time.encoding["units"] = time_encoding
    alerts_baseline_ds.time_bounds.encoding["units"] = time_encoding

    # disable _FillValue for variables that shouldn't have empty values
    alerts_baseline_ds.time_bounds.encoding["_FillValue"] = None
    alerts_baseline_ds.x.encoding["_FillValue"] = None
    alerts_baseline_ds.y.encoding["_FillValue"] = None
    alerts_baseline_ds.x_bounds.encoding["_FillValue"] = None
    alerts_baseline_ds.y_bounds.encoding["_FillValue"] = None

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
        land_mask = alerts_baseline_ds["land_mask"].to_numpy().squeeze()
        baseline_mean = alerts_baseline_ds["sim_baseline_mean_diff"].to_numpy().squeeze()
        baseline_std = alerts_baseline_ds["obs_baseline_std_diff"].to_numpy().squeeze()
        baseline_count = alerts_baseline_ds["baseline_count"].to_numpy().squeeze()

        near_threshold = alerts_baseline_ds.attrs["alerts_near_threshold"]
        far_threshold = alerts_baseline_ds.attrs["alerts_far_threshold"]
        ds.close()

    obs_sim, obs_period_start, obs_period_end = get_obs_sim(
        daily_dir, obs_file_template, sim_file_template
    )

    near, far = map_enhance(lats, lons, land_mask, obs_sim, near_threshold, far_threshold)
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

    # the domain typically has only one grid mapping, which applies to vars
    # with y, x coords
    projection_var_name = get_grid_mappings(alerts_baseline_ds)[0]

    # copy dimensions and attributes from the alerts baseline, as the alerts
    # should be provided in the same grid / format
    alerts_ds = xr.Dataset(
        coords={
            "x": alerts_baseline_ds.coords["x"],
            "y": alerts_baseline_ds.coords["y"],
            "time": (("time"), [period_start], {
                "standard_name": "time",
                "bounds": "time_bounds",
            }),
        },
        data_vars={
            # bounds
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#cell-boundaries
            "x_bounds": alerts_baseline_ds.variables["x_bounds"],
            "y_bounds": alerts_baseline_ds.variables["y_bounds"],
            "time_bounds": (("time", "bounds_t"), [[period_start, period_end]]),

            # georeferencing
            "lat": alerts_baseline_ds.variables["lat"],
            "lon": alerts_baseline_ds.variables["lon"],
            # https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#_lambert_conformal
            projection_var_name: alerts_baseline_ds.variables[projection_var_name],

            # copied data
            "land_mask": alerts_baseline_ds.variables["land_mask"],
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
                    "grid_mapping": projection_var_name,
                },
            ),
            "obs_enhancement": (
                ("time", "y", "x"),
                [obs_enhancement],
                {
                    "long_name": "Difference between near and far field concentrations",
                    "units": "1e-9",
                    "grid_mapping": projection_var_name,
                },
            ),
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

            # domain
            "domain_name": alerts_baseline_ds.domain_name,
            "domain_version": alerts_baseline_ds.domain_version,
            "domain_slug": alerts_baseline_ds.domain_slug,

            # common
            "title": "Open Methane daily methane alerts",
            "history": get_timestamped_command(),
            "openmethane_version": get_version(),

            "Conventions": "CF-1.12",
        },
    )

    # ensure time and time_bounds use the same time encoding
    time_encoding = f"days since {period_start.strftime('%Y-%m-%d')}"
    alerts_ds.time.encoding["units"] = time_encoding
    alerts_ds.time_bounds.encoding["units"] = time_encoding

    # disable _FillValue for variables that shouldn't have empty values
    alerts_baseline_ds.time_bounds.encoding["_FillValue"] = None
    alerts_baseline_ds.x.encoding["_FillValue"] = None
    alerts_baseline_ds.y.encoding["_FillValue"] = None
    alerts_baseline_ds.x_bounds.encoding["_FillValue"] = None
    alerts_baseline_ds.y_bounds.encoding["_FillValue"] = None

    alerts_ds.to_netcdf(output_file)


def map_enhance( # noqa: PLR0913
    lat,
    lon,
    land_mask,
    concs,
    nearThreshold,
    farThreshold,
    chunk_size=4096,
):
    """
    Average each concentration record over the observations surrounding every
    land cell in the domain, for a near field (distance < nearThreshold) and a
    far field (nearThreshold < distance < farThreshold).

    Distances are Euclidean in degrees of latitude/longitude, matching the units
    of the thresholds. Cells with no near-field or no far-field observations are
    left as nan.

    The observations are indexed in a k-d tree so that each land cell only ever
    looks at the observations near it. Scanning every observation once per land
    cell instead makes this quadratic in the size of the domain, which dominates
    the runtime of the whole baseline for a continental grid.
    """
    logger.debug("Calculating enhancements in map_enhance")
    nConcs = concs.shape[1] - 2  # number of concentration records, the -2 removes lat,lon
    n_rows = land_mask.shape[0]
    n_cols = land_mask.shape[1]
    resultShape = (nConcs, n_rows, n_cols)
    near_field = np.full(resultShape, np.nan)
    far_field = np.full(resultShape, np.nan)

    land = land_mask > 0.5
    if concs.shape[0] == 0 or not land.any():
        return near_field, far_field

    obs_coords = np.ascontiguousarray(concs[:, 0:2], dtype=np.float64)
    obs_values = np.ascontiguousarray(concs[:, 2:], dtype=np.float64)

    rows, cols = np.nonzero(land)
    land_coords = np.stack([lat[rows, cols], lon[rows, cols]], axis=1).astype(np.float64)
    n_land = land_coords.shape[0]
    logger.debug(f"Averaging {concs.shape[0]} observations over {n_land} land cells")

    # Use an efficient structure to store observation coordinates, making it
    # easy to quickly locate observations in neighbouring cells when calculating
    # near and far fields.
    obs_tree = cKDTree(obs_coords)

    near_sum = np.zeros((n_land, nConcs))
    far_sum = np.zeros((n_land, nConcs))
    near_count = np.zeros(n_land, dtype=np.int64)
    far_count = np.zeros(n_land, dtype=np.int64)

    # work through the land cells in chunks so the neighbour list stays bounded
    # regardless of how many observations the day contains
    for start in range(0, n_land, chunk_size):
        stop = min(start + chunk_size, n_land)
        chunk_tree = cKDTree(land_coords[start:stop])
        pairs = chunk_tree.sparse_distance_matrix(obs_tree, farThreshold, output_type="ndarray")
        if pairs.size == 0:
            continue
        cell_index = pairs["i"] + start
        obs_index = pairs["j"]
        dist = pairs["v"]

        for selected, sums, counts in (
            (dist < nearThreshold, near_sum, near_count),
            ((dist > nearThreshold) & (dist < farThreshold), far_sum, far_count),
        ):
            cells = cell_index[selected]
            if cells.size == 0:
                continue
            counts[:] += np.bincount(cells, minlength=n_land)
            observations = obs_index[selected]
            for k in range(nConcs):
                sums[:, k] += np.bincount(
                    cells, weights=obs_values[observations, k], minlength=n_land
                )

    # an enhancement is only defined where both fields saw observations
    valid = (near_count > 0) & (far_count > 0)
    valid_rows = rows[valid]
    valid_cols = cols[valid]
    for k in range(nConcs):
        near_field[k, valid_rows, valid_cols] = near_sum[valid, k] / near_count[valid]
        far_field[k, valid_rows, valid_cols] = far_sum[valid, k] / far_count[valid]

    return near_field, far_field
