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
import traceback

import func_timeout
import numpy as np
from netCDF4 import Dataset

import fourdvar.util.file_handle as fh
from fourdvar import logging
from fourdvar.params import input_defn
from fourdvar.util.date_handle import end_date, start_date
from obs_preprocess.model_space import ModelSpace
from obs_preprocess.obsESA_defn import ObsSRON

logging.setup_logging()
logger = logging.get_logger(__name__)

# -CONFIG-SETTINGS---------------------------------------------------------

#'filelist': source = list of OCO2-Lite files
#'directory': source = directory, use all files in source
#'pattern': source = file_pattern_string, use all files that match pattern
source_type = "pattern"

# source = [ os.path.join( store_path, 'obs_src', 's5p_l2_co_0007_04270.nc' ) ]
source = "/home/563/pjr563/scratch/tmp/202207/S5P_RPRO_L2__CH4____20220721T063513_20220721T081643_24713_03_020400_20230201T030600.SUB.nc4"  # noqa
source = "/scratch/q90/pjr563/tmp/202207/S5P_OFFL_L2__CH4____20220730T070626_20220730T084755_24841_03_020400_20220801T012853.SUB.nc4"  # noqa
source = "/home/563/pjr563/scratch/tmp/202207/S5P_RPRO_L2__CH4____202207*.nc4"
output_file = input_defn.obs_file

# minimum qa_value before observation is discarded
qa_cutoff = 0.5
# --------------------------------------------------------------------------

# set up multiprocessing wrappers and pools
nCPUs = os.environ.get("NCPUS")
if nCPUs is None:
    nCPUs = 1
else:
    nCPUs = int(nCPUs)  # it's read as a string
maxProcessTime = 5.0  # maximum time for processing an observation in seconds


def timeWrapper(val):
    wait, modelGrid, varDict = val
    args = (modelGrid, varDict)
    try:
        return func_timeout.func_timeout(wait, processObs, (args,))
    except func_timeout.FunctionTimedOut:
        return None


def processObs(vals):
    var_dict = vals[0]
    model_grid = vals[1]
    obs = ObsSRON.create(**var_dict)
    obs.interp_time = False
    obs.model_process(model_grid)
    return obs


model_grid = ModelSpace.create_from_fourdvar()

if source_type.lower() == "filelist":
    filelist = [os.path.realpath(f) for f in source]
elif source_type.lower() == "pattern":
    filelist = [os.path.realpath(f) for f in sorted(glob.glob(source))]
elif source_type.lower() == "directory":
    dirname = os.path.realpath(source)
    filelist = [
        os.path.join(dirname, f)
        for f in os.listdir(dirname)
        if os.path.isfile(os.path.join(dirname, f))
    ]
else:
    raise TypeError(f"source_type '{source_type}' not supported")

obslist = []
nObs = [0, 0]
nThin = 1  # included for testing
nTest = 0  # included for testing
iTest = 0

for fname in filelist:
    print(f"processing {fname}")
    varDictList = []
    nTimedOut = 0

    with Dataset(fname, "r") as f:
        try:  # checking if there's an error code by getting the error attribute, we hope this fails
            errorString = f.getncattr("errors")
            print("error ", fname, errorString)
            continue  # no further processing on this file, context manager should close f
        except Exception:
            pass  # all ok, just continue
        if f.processing_status != "Nominal":
            print(f"file {fname} processing_status = {f.processing_status}, skipping")
        instrument = f.groups["PRODUCT"]
        meteo = f["/PRODUCT/SUPPORT_DATA/INPUT_DATA"]
        product = f["/PRODUCT"]
        diag = f["/PRODUCT"]
        geo = f["/PRODUCT/SUPPORT_DATA/GEOLOCATIONS"]
        n_layers = product.dimensions["layer"].size
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
        surface_pressure = meteo.variables["surface_pressure"][:, :]
        ch4 = product.variables["methane_mixing_ratio_bias_corrected"][...]
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
            latitude_center >= model_grid.lat_bounds[0], latitude_center <= model_grid.lat_bounds[1]
        )
        lon_filter = np.logical_and(
            longitude_center >= model_grid.lon_bounds[0],
            longitude_center <= model_grid.lon_bounds[1],
        )
        mask_filter = np.logical_not(mask_arr)
        qa_filter = qa_value > qa_cutoff
        include_filter = np.logical_and.reduce((lat_filter, lon_filter, mask_filter, qa_filter))

        epoch = dt.datetime.utcfromtimestamp(0)
        sdate = dt.datetime(start_date.year, start_date.month, start_date.day)
        edate = dt.datetime(end_date.year, end_date.month, end_date.day)
        size = include_filter.sum()
        nObs[0] += size
        nObs[1] += include_filter.size
        for i, iflag in enumerate(include_filter):
            if iflag:
                # scanning time is slow, do it after other filters.
                # tsec = (dt.datetime(*time[i,:])-epoch).total_seconds()
                dt_time = dt.datetime.strptime(time[i][0:19], "%Y-%m-%dT%H:%M:%S")
                tsec = (dt_time - epoch).total_seconds()
                time0 = (sdate - epoch).total_seconds()
                time1 = (edate - epoch).total_seconds() + 24 * 60 * 60
                if tsec < time0 or tsec > time1:
                    continue
                iTest += 1
                if nTest > 0 and iTest > nTest:
                    break
                if iTest % nThin != 0:
                    continue
                var_dict = {}
                # var_dict['time'] = dt.datetime( *time[0,i] )
                var_dict["time"] = dt.datetime.strptime(time[i][0:19], "%Y-%m-%dT%H:%M:%S")
                var_dict["latitude_center"] = latitude_center[i]
                var_dict["longitude_center"] = longitude_center[i]
                var_dict["latitude_corners"] = latitude_corners[i, :]
                var_dict["longitude_corners"] = longitude_corners[i, :]
                var_dict["solar_zenith_angle"] = solar_zenith_angle[i]
                var_dict["viewing_zenith_angle"] = viewing_zenith_angle[i]
                var_dict["solar_azimuth_angle"] = solar_azimuth_angle[i]
                var_dict["viewing_azimuth_angle"] = viewing_azimuth_angle[i]
                press_levels = (
                    np.arange(n_levels) * pressure_interval[i]
                )  ##we need to put pressure=0 at the first leveli
                var_dict["pressure_levels"] = press_levels
                var_dict["ch4_column"] = ch4_column[i]
                var_dict["ch4_column_precision"] = ch4_column_precision[i]
                var_dict["obs_kernel"] = averaging_kernel[i, :]
                var_dict["qa_value"] = qa_value[i]
                var_dict["ch4_profile_apriori"] = ch4_profile_apriori[i, :]
                varDictList.append((maxProcessTime, var_dict, model_grid))
                # obs = ObsSRON.create( **var_dict )
                # obs.interp_time = False
                # obs.model_process( model_grid )
                # if obs.valid is True:
                #     obslist.append( obs.get_obsdict() )
        with multiprocessing.Pool(nCPUs) as pool:
            try:
                processOutput = pool.imap_unordered(timeWrapper, varDictList)
                nProcessed = 0
                baseTime = timing.time()
                for obs in processOutput:
                    if obs is None:
                        nTimedOut += 1
                    elif obs.valid:
                        obslist.append(obs)
                    if nProcessed % 1000 == 0:
                        print(
                            f"{nProcessed} obs processed in {timing.time() -baseTime:8.1f} seconds"
                        )
                    nProcessed += 1
            except Exception as ex:
                message = (
                    f"an exception of type {type(ex).__name__} has occurred\nskipping file {fname}"
                )
                print(message)
                print(traceback.format_exc())
                logger.warn(message)

print(len(varDictList), "possible observations")
print(f"found {nObs[0]:d} valid soundings from {nObs[1]:d} possible")
print(f"{nTimedOut} observations timed out after {maxProcessTime} seconds")
if len(obslist) > 0:
    domain = model_grid.get_domain()
    domain["is_lite"] = False
    datalist = [domain] + [o.out_dict for o in obslist]
    fh.save_list(datalist, output_file)
    print(f"recorded observations to {output_file}")
else:
    print("No valid observations found, no output file generated.")
