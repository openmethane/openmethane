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
import pathlib
import pytest
import xarray as xr

import fourdvar.datadef as d
from postproc.posterior_emissions_postprocess import posterior_emissions_postprocess, normalise_posterior


def test_posterior_emissions_postprocess(target_environment, test_data_dir):
    target_environment('docker-test')

    posterior_multipliers = d.PhysicalData.from_file(
        pathlib.Path(test_data_dir, "fourdvar", "posterior_multipliers.nc")
    )

    # validate that test input hasn't changed before we attempt to transform it
    assert posterior_multipliers.emis_units == "mol/(s*m^2)", "incorrect unit emissions"
    assert posterior_multipliers.ncols == 5, "incorrect dimensions (cols) in test data"
    assert posterior_multipliers.nrows == 5, "incorrect dimensions (rows) in test data"
    assert posterior_multipliers.emis['CH4'].max() == pytest.approx(1.000529), "input values (max) do not match expected"
    assert posterior_multipliers.emis['CH4'].sum() == pytest.approx(25.001793), "input values (sum) do not match expected"

    prior_emis = xr.open_dataset(pathlib.Path(test_data_dir, "templates", "record", "emis_record_2022-07-22.nc"))
    prior_emis_mean_3d = prior_emis['CH4'].to_numpy().mean(axis=0)
    prior_emis_mean_surf = prior_emis_mean_3d[0, ...]
    assert prior_emis_mean_surf.max() == pytest.approx(0.73562735), "prior emissions values (max) do not match expected"
    assert prior_emis_mean_surf.mean() == pytest.approx(0.5934696197509766), "prior emissions values (mean) do not match expected"
    assert prior_emis_mean_surf[0][0] == pytest.approx(0.73562735), "prior emissions values (first) do not match expected"

    # calculate the estimated emissions, multiplying the posterior multipliers from
    # the minimiser (test-data/fourdvar/posterior_multipliers.nc) by the expected
    # emissions values (test-data/templates/record/emis_record_2022-07-22.nc)
    posterior_emissions = posterior_emissions_postprocess(
        posterior_multipliers=posterior_multipliers.emis['CH4'],
        template_dir=pathlib.Path(test_data_dir, "templates"),
        emis_template="emis_record_2022-07-22.nc"
    )

    # check the transformations on the data, multiplying the posterior multipliers from
    # the minimiser (test-data/fourdvar/posterior_multipliers.nc) by the expected
    # emissions values (test-data/templates/record/emis_record_2022-07-22.nc)
    assert posterior_emissions.attrs['XCELL'] == 10000, "post-processed cell size has changed"
    assert posterior_emissions.attrs['YCELL'] == 10000, "post-processed cell size has changed"
    assert posterior_emissions['CH4'].sum() == pytest.approx(2.3740436e-09), "post-processed emissions (max) don't match expected"

    expected_moles = normalise_posterior(posterior_multipliers.emis['CH4']) * prior_emis_mean_surf
    # convert from moles to m**2/kg
    expected = expected_moles * (16 * 1e-3) / (posterior_emissions.attrs['XCELL'] * posterior_emissions.attrs['YCELL'])

    # spot check several cells
    assert posterior_emissions['CH4'][0][0] == expected[0][0], "emissions are do not equal multiplier times prior"
    assert posterior_emissions['CH4'][2][4] == expected[2][4], "emissions are do not equal multiplier times prior"
    assert posterior_emissions['CH4'][4][4] == expected[4][4], "emissions are do not equal multiplier times prior"