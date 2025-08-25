#
# Copyright 2024 The SuperPower Institute Ltd
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
import glob
import pathlib

import numpy as np
import pandas as pd
import pytest
import xarray as xr

import fourdvar.datadef as d
from postproc.posterior_emissions_postprocess import (
    normalise_posterior,
    posterior_emissions_postprocess,
)


def test_posterior_emissions_postprocess(target_environment, test_data_dir):
    target_environment("docker-test")

    posterior_multipliers = d.PhysicalData.from_file(
        pathlib.Path(test_data_dir, "fourdvar", "posterior-multipliers.nc")
    )
    prior_emissions = xr.open_dataset(pathlib.Path(test_data_dir, "prior", "prior-emissions.nc"))

    # validate that test input hasn't changed before we attempt to transform it
    assert posterior_multipliers.emis_units == "mol/(s*m^2)", "incorrect unit emissions"
    assert posterior_multipliers.ncols == 10, "incorrect dimensions (cols) in test data"
    assert posterior_multipliers.nrows == 10, "incorrect dimensions (rows) in test data"
    assert posterior_multipliers.emis["CH4"].max() == pytest.approx(
        1.1112205
    ), "input values (max) do not match expected"
    assert posterior_multipliers.emis["CH4"].sum() == pytest.approx(
        99.69608
    ), "input values (sum) do not match expected"

    prior_emis = xr.open_dataset(
        pathlib.Path(test_data_dir, "templates", "record", "emis_record_2022-12-07.nc")
    )
    prior_emis_mean_3d = prior_emis["CH4"].to_numpy().mean(axis=0)
    prior_emis_mean_surf = prior_emis_mean_3d[0, ...]
    assert prior_emis_mean_surf.max() == pytest.approx(
        95.388885
    ), "prior emissions values (max) do not match expected"
    assert prior_emis_mean_surf.mean() == pytest.approx(
        4.111149
    ), "prior emissions values (mean) do not match expected"
    assert prior_emis_mean_surf[0][0] == pytest.approx(
        1.8064358234405518
    ), "prior emissions values (first) do not match expected"

    # calculate the estimated emissions, multiplying the posterior multipliers from
    # the minimiser (test-data/fourdvar/posterior-multipliers.nc) by the expected
    # emissions values (test-data/templates/record/emis_record_2022-12-07.nc)
    posterior_emissions = posterior_emissions_postprocess(
        posterior_multipliers=posterior_multipliers.emis["CH4"],
        prior_emissions_ds=prior_emissions,
        template_dir=pathlib.Path(test_data_dir, "templates"),
        emis_template="emis_record_2022-12-07.nc",
    )

    # check the transformations on the data, multiplying the posterior multipliers from
    # the minimiser (test-data/fourdvar/posterior-multipliers.nc) by the expected
    # emissions values (test-data/templates/record/emis_record_2022-12-07.nc)
    assert posterior_emissions.attrs["XCELL"] == 10000, "post-processed cell size has changed"
    assert posterior_emissions.attrs["YCELL"] == 10000, "post-processed cell size has changed"
    assert posterior_emissions["ch4"].sum() == pytest.approx(
        6.25249e-08
    ), "post-processed emissions (max) don't match expected"

    expected_moles = normalise_posterior(posterior_multipliers.emis["CH4"]) * prior_emis_mean_surf
    # convert from moles to m**2/kg
    expected = (
        expected_moles
        * (16 * 1e-3)
        / (posterior_emissions.attrs["XCELL"] * posterior_emissions.attrs["YCELL"])
    )

    # spot check several cells
    assert (
        posterior_emissions["ch4"][0][0][0][0] == expected[0][0]
    ), "emissions do not equal multiplier times prior"
    assert (
        posterior_emissions["ch4"][0][0][2][4] == expected[2][4]
    ), "emissions do not equal multiplier times prior"
    assert (
        posterior_emissions["ch4"][0][0][4][4] == expected[4][4]
    ), "emissions do not equal multiplier times prior"

    assert posterior_emissions["time"][0] == np.datetime64("2022-12-07"),\
        "time coordinates do not match expected"
    assert posterior_emissions["time"].attrs["bounds"] == "time_bounds"

    assert posterior_emissions["time_bounds"][0][0] == np.datetime64("2022-12-07"),\
        "time_bounds do not match expected"
    assert posterior_emissions["time_bounds"][0][1] == np.datetime64("2022-12-08"),\
        "time_bounds do not match expected"

    assert posterior_emissions["x"].attrs["bounds"] == "x_bounds"

    assert posterior_emissions["y"].attrs["bounds"] == "y_bounds"

    assert posterior_emissions["lat"][0, 0].item() == pytest.approx(
        -23.729095458984375
    ), "lat coordinates do not match expected"
    assert posterior_emissions["lat"][2, 2].item() == pytest.approx(
        -23.524276733398438
    ), "lat coordinates do not match expected"
    assert posterior_emissions["lat"][4, 4].item() == pytest.approx(
        -23.31928062438965
    ), "lat coordinates do not match expected"

    assert posterior_emissions["lon"][0, 0].item() == pytest.approx(
        148.247802734375
    ), "lon coordinates do not match expected"
    assert posterior_emissions["lon"][2, 2].item() == pytest.approx(
        148.4224853515625
    ), "lon coordinates do not match expected"
    assert posterior_emissions["lon"][4, 4].item() == pytest.approx(
        148.5965576171875
    ), "lon coordinates do not match expected"

    # check that prior emissions in the posterior output are the mean of all
    # prior timesteps from the input
    prior_sector_vars = [var_name for var_name in prior_emissions.variables if var_name.startswith("ch4_sector")]
    for sector_var in prior_sector_vars:
        sector_mean = prior_emissions[sector_var].mean(axis=0)
        # spot check a single coord at 1,1
        assert float(sector_mean[0, 1, 1]) == float(posterior_emissions[f"prior_{sector_var}"][0, 0, 1, 1])


def test_posterior_emissions_postprocess_multi_day(target_environment, test_data_dir):
    target_environment("docker-test")

    posterior_multipliers = d.PhysicalData.from_file(
        pathlib.Path(test_data_dir, "fourdvar", "posterior-multipliers.nc")
    )
    prior_emissions = xr.open_dataset(pathlib.Path(test_data_dir, "prior", "prior-emissions.nc"))

    prior_emis = glob.glob(str(pathlib.Path(test_data_dir, "templates", "record", "emis_*.nc")))
    assert len(prior_emis) == 2, "did not find exactly 2 days of test data"

    # calculate the estimated emissions, multiplying the posterior multipliers from
    # the minimiser (test-data/fourdvar/posterior-multipliers.nc) by the expected
    # emissions values (test-data/templates/record/emis_record_2022-12-07.nc)
    posterior_emissions = posterior_emissions_postprocess(
        posterior_multipliers=posterior_multipliers.emis["CH4"],
        prior_emissions_ds=prior_emissions,
        template_dir=pathlib.Path(test_data_dir, "templates"),
        emis_template="emis_*.nc",
    )

    # spot check several cells
    assert posterior_emissions["ch4"][0, 0, 0, 0].item() == pytest.approx(
        2.8897012560591406e-10
    ), "emissions do not match expected"
    assert posterior_emissions["ch4"][0, 0, 4, 4].item() == pytest.approx(
        8.876147039593718e-11
    ), "emissions do not match expected"
    print("type(posterior_emissions['time'][0].item())")
    print(type(posterior_emissions["time"][0].item()))
    assert posterior_emissions["time"][0] == np.datetime64("2022-12-07"),\
        "time coordinates do not match expected"
    assert posterior_emissions["time_bounds"][0, 0] == np.datetime64("2022-12-07"),\
        "time_bounds do not match expected"
    assert posterior_emissions["time_bounds"][0, 1] == np.datetime64("2022-12-09"),\
        "time_bounds do not match expected"

    # TODO: check that sectoral ch4 variables equal the mean of all time steps
    # in the prior file, when we have a multi-day prior for tests
