#
# Copyright 2016 University of Melbourne.
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
#
import datetime as dt
import glob
import multiprocessing
import os
import time as timing
from typing import Any

import click
import func_timeout
import numpy as np
from netCDF4 import Dataset

import fourdvar.util.file_handle as fh
from fourdvar import logging
from fourdvar.params import date_defn, input_defn
from obs_preprocess.model_space import ModelSpace
from obs_preprocess.obsESA_defn import ObsSRON

logging.setup_logging()
logger = logging.get_logger(__name__)


N_CPUS = int(os.environ.get("NCPUS", 1))
DEFAULT_WS1 = int(os.environ.get("DEFAULT_WS1", 7))  # default recommended by SRON
DEFAULT_WS2 = int(os.environ.get("DEFAULT_WS2", 100))  # default recommended by SRON


def destripe_smoothing(
    data: np.ndarray,
    ws1: int = DEFAULT_WS1,
    ws2: int = DEFAULT_WS2,
) -> np.ndarray:
    """Remove low-frequency stripes in the data using smoothing.

    Parameters
    ----------
    data
        2D data array
    ws1
        The window size along the second axis
    ws2
        The window size along the first axis
    """

    # get the number of rows
    n = data.shape[0]
    # get the number of columns
    m = data.shape[1]

    back = np.zeros((n, m)) * np.nan
    for i in range(m):
        # define half window size
        ws = ws1

        if i < ws:
            st = 0
            sp = i + ws

        elif m - i < ws:
            st = i - ws
            sp = m - 1
        else:
            st = i - ws
            sp = i + ws

        back[:, i] = np.nanmedian(data[:, st:sp], axis=1)

    this = data - back

    stripes = np.zeros((n, m)) * np.nan
    for j in range(n):
        ws = ws2

        if j < ws:
            st = 0
            sp = j + ws

        elif n - j < ws:
            st = j - ws
            sp = n - 1
        else:
            st = j - ws
            sp = j + ws

        stripes[j, :] = np.nanmedian(this[st:sp, :], axis=0)

    return data - stripes


def time_wrapper(
    val,
    # timeout: float, obs_variables: dict[str, float], model_grid: ModelSpace
) -> ObsSRON | None:
    timeout, obs_variables, model_grid = val
    try:
        return func_timeout.func_timeout(timeout, process_obs, (obs_variables, model_grid))
    except func_timeout.FunctionTimedOut:
        return None


def process_obs(obs: dict[str, float], model_grid: ModelSpace) -> ObsSRON:
    obs = ObsSRON.create(**obs)
    obs.interp_time = False
    obs.model_process(model_grid)

    return obs


def process_file(
    model_grid: ModelSpace, ds: Dataset, qa_cutoff: float, max_process_time: float
) -> tuple[list[ObsSRON], int, int]:
    """
    Process an individual file

    Parameters
    ----------
    model_grid
        Model defining the grid
    ds
        The open TropOMI file to process
    qa_cutoff

    max_process_time
        Maximum time to spend on each process

    Returns
    -------

    """
    instrument = ds.groups["PRODUCT"]
    meteo = ds["/PRODUCT/SUPPORT_DATA/INPUT_DATA"]
    product = ds["/PRODUCT"]
    diag = ds["/PRODUCT"]
    geo = ds["/PRODUCT/SUPPORT_DATA/GEOLOCATIONS"]
    n_levels = product.dimensions["level"].size
    latitude = instrument.variables["latitude"][:]
    latitude_center = latitude.reshape((latitude.size,))
    longitude = instrument.variables["longitude"][:]
    longitude_center = longitude.reshape((longitude.size,))
    timeUTC = instrument.variables["time_utc"][:]
    timeUTC = np.stack([timeUTC] * latitude.shape[2], axis=2)
    time = timeUTC.reshape((timeUTC.size,))
    latitude_bounds = geo.variables["latitude_bounds"][:]
    latitude_corners = latitude_bounds.reshape((latitude.size, 4))
    longitude_bounds = geo.variables["longitude_bounds"][:]
    longitude_corners = longitude_bounds.reshape((longitude.size, 4))
    solar_zenith_deg = geo.variables["solar_zenith_angle"][:]
    solar_zenith_angle = solar_zenith_deg.reshape((solar_zenith_deg.size,))
    viewing_zenith_deg = geo.variables["viewing_zenith_angle"][:]
    viewing_zenith_angle = viewing_zenith_deg.reshape((viewing_zenith_deg.size,))
    solar_azimuth_deg = geo.variables["solar_azimuth_angle"][:]
    solar_azimuth_angle = solar_azimuth_deg.reshape((solar_azimuth_deg.size,))
    viewing_azimuth_deg = geo.variables["viewing_azimuth_angle"][:]
    viewing_azimuth_angle = viewing_azimuth_deg.reshape((viewing_azimuth_deg.size,))
    pressure_interval = meteo.variables["pressure_interval"][:, :]
    pressure_interval = pressure_interval.reshape(pressure_interval.size)
    ch4 = product.variables["methane_mixing_ratio_bias_corrected"][...]
    ch4 = destripe_smoothing(ch4.squeeze())
    ch4_column = ch4.reshape((ch4.size,))
    ch4_precision = product.variables["methane_mixing_ratio_precision"][:]
    ch4_column_precision = ch4_precision.reshape((ch4_precision.size,))
    ch4_averaging_kernel = product["SUPPORT_DATA/DETAILED_RESULTS/column_averaging_kernel"][...]
    averaging_kernel = np.reshape(ch4_averaging_kernel, (-1, ch4_averaging_kernel.shape[-1]))
    #        ch4_column_apriori = product.variables['ch4_column_apriori'][:]
    temp = meteo.variables["methane_profile_apriori"][...]
    ch4_profile_apriori = temp.reshape(temp.size, -1)
    qa = diag.variables["qa_value"][:]
    qa_value = qa.reshape((qa.size,))

    mask_arr = np.ma.getmaskarray(ch4_column)

    # quick filter out: mask, lat, lon and quality
    lat_filter = np.logical_and(
        latitude_center >= model_grid.lat_bounds[0],
        latitude_center <= model_grid.lat_bounds[1],
    )
    lon_filter = np.logical_and(
        longitude_center >= model_grid.lon_bounds[0],
        longitude_center <= model_grid.lon_bounds[1],
    )
    mask_filter = np.logical_not(mask_arr)
    qa_filter = qa_value > qa_cutoff
    include_filter = np.logical_and.reduce((lat_filter, lon_filter, mask_filter, qa_filter))

    epoch = dt.datetime.utcfromtimestamp(0)

    start_date = date_defn.start_date
    end_date = date_defn.end_date
    sdate = dt.datetime(start_date.year, start_date.month, start_date.day)
    edate = dt.datetime(end_date.year, end_date.month, end_date.day)
    size = include_filter.sum()

    if size:
        print(f"{size} observations in domain")

    file_total_obs = include_filter.size

    obs_collection = []
    for i, iflag in enumerate(include_filter):
        if not iflag:
            continue
        # scanning time is slow, do it after other filters.
        # tsec = (dt.datetime(*time[i,:])-epoch).total_seconds()
        dt_time = dt.datetime.strptime(time[i][0:19], "%Y-%m-%dT%H:%M:%S")
        tsec = (dt_time - epoch).total_seconds()
        time0 = (sdate - epoch).total_seconds()
        time1 = (edate - epoch).total_seconds() + 24 * 60 * 60
        if tsec < time0 or tsec > time1:
            continue

        press_levels = (
            np.arange(n_levels) * pressure_interval[i]
        )  ## we need to put pressure=0 at the first leveli

        obs_variables = {
            "time": dt.datetime.strptime(time[i][0:19], "%Y-%m-%dT%H:%M:%S"),
            "latitude_center": latitude_center[i],
            "longitude_center": longitude_center[i],
            "latitude_corners": latitude_corners[i, :],
            "longitude_corners": longitude_corners[i, :],
            "solar_zenith_angle": solar_zenith_angle[i],
            "viewing_zenith_angle": viewing_zenith_angle[i],
            "solar_azimuth_angle": solar_azimuth_angle[i],
            "viewing_azimuth_angle": viewing_azimuth_angle[i],
            "pressure_levels": press_levels,
            "ch4_column": ch4_column[i],
            "ch4_column_precision": ch4_column_precision[i],
            "obs_kernel": averaging_kernel[i, :],
            "qa_value": qa_value[i],
            "ch4_profile_apriori": ch4_profile_apriori[i, :],
        }

        obs_collection.append((obs_variables, model_grid))
    if len(obs_collection):
        obs_list = process_observations(obs_collection, max_process_time=max_process_time)
    else:
        print("no valid observations remain")
        obs_list = []
    return obs_list, file_total_obs, len(obs_collection)


def process_observations(
    obs_collection: list[tuple[Any, ModelSpace]], max_process_time: float
) -> list[ObsSRON]:
    """
    Process the observations for a single file

    This function is a wrapper around the multiprocessing pool to handle timeouts and other issues.

    Parameters
    ----------
    obs_collection
        The collection of observations to process.

        Each item is a tuple of (obs_variables, model_grid)
    n_cpus
        Number of CPUs used to process the observations
    max_process_time
        Maximum time to process each observation in seconds

    Returns
    -------
        The result from processing the observations

        TODO: Figure out what is returned
    """
    n_timed_out = 0
    n_processed = 0

    obs_list = []

    with multiprocessing.Pool(N_CPUS) as pool:
        process_output = pool.imap_unordered(
            time_wrapper, [(max_process_time, *item) for item in obs_collection]
        )
        base_time = timing.time()

        for obs in process_output:
            if obs is None:
                n_timed_out += 1
            elif obs.valid:
                obs_list.append(obs)
            if n_processed % 1000 == 0:
                print(f"{n_processed} obs processed in {timing.time() - base_time:8.1f} seconds")
            n_processed += 1

    print(
        f"{n_timed_out}/{len(obs_collection)} "
        f"observations timed out after {max_process_time} seconds"
    )

    return obs_list


@click.command()
@click.option(
    "--source", "-s", help="Glob used to define the input tropOMI files to process", required=True
)
@click.option(
    "--output-file",
    "-o",
    help="Filename to put the processed observations. This is nominally a GZipped pickle file",
    default=input_defn.obs_file,
)
@click.option(
    "--qa-cutoff",
    help="Minimum qa_value before observation is discarded.",
    default=0.5,
)
@click.option(
    "--max-process-time",
    help="Maximum time to process each observation in seconds. Default is 5 seconds",
    default=5,
)
def run_tropomi_preprocess(source, output_file, qa_cutoff, max_process_time):
    """
    Process TROPOMI data to create a set of observations for use in the fourdvar system.
    """
    model_grid = ModelSpace.create_from_fourdvar()

    file_list = sorted([os.path.realpath(f) for f in glob.glob(source)])

    obs_list = []
    n_total_obs = 0
    n_valid_obs = 0

    for fname in file_list:
        print(f"Processing {fname}")
        try:
            with Dataset(fname, "r") as ds:
                # Check if the file has any error messages
                if hasattr(ds, "errors"):
                    print(f"error in file = {ds.errors}, skipping")
                    continue
                # elif ds.processing_status != "Nominal":
                #     print(f"processing_status = {ds.processing_status}, skipping")
                #     continue

                new_obs, file_total_obs, file_valid_obs = process_file(
                    model_grid,
                    ds,
                    qa_cutoff=qa_cutoff,
                    max_process_time=max_process_time,
                )

            obs_list.extend(new_obs)
            n_total_obs += file_total_obs
            n_valid_obs += file_valid_obs
        except Exception:
            # Ignore all observations in that file
            logger.exception(f"Failed to process file: {fname}. Skipping")

    print(f"found {n_valid_obs} valid soundings from {n_total_obs} possible")
    if len(obs_list) > 0:
        domain = model_grid.get_domain()
        domain["is_lite"] = False
        datalist = [domain] + [o.out_dict for o in obs_list]
        fh.save_list(datalist, output_file)
        print(f"recorded observations to {output_file}")
    else:
        print("No valid observations found, no output file generated.")


if __name__ == "__main__":
    run_tropomi_preprocess()
