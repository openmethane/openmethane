#
# Copyright 2023 The SuperPower Institute Ltd
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

import numpy as np

import fourdvar.datadef as d
import fourdvar.user_driver as user
import fourdvar.util.archive_handle as archive
import fourdvar.util.date_handle as dt
import fourdvar.util.netcdf_handle as ncf
from fourdvar._transform import transform
from fourdvar.params import archive_defn, cmaq_config, template_defn


def test_fourdvar_grad_cmaq(target_environment):
    target_environment("docker-test")

    _run_grad_cmaq()


def _run_grad_cmaq():
    archive_defn.experiment = "tmp_grad_cmaq"
    archive_defn.desc_name = ""

    archive_path = archive.get_archive_path()
    print(f"saving results in:\n{archive_path}")

    print("get prior in PhysicalData format")
    physical = user.get_background()
    modelInput = transform(physical, d.ModelInputData)
    model_input_vector = modelInput.get_vector()
    modelOutput = transform(modelInput, d.ModelOutputData)
    init_cost = modelOutput.sum_squares()
    forcing_vector = modelOutput.get_vector()  # adjoint of sum_squares
    adjointForcing = d.AdjointForcingData.load_from_vector_template(forcing_vector)
    sensitivity = transform(adjointForcing, d.SensitivityData)
    # units are now in cf/ppm/s, we need to convert to cf/mole/s which means dealing with air density
    # physical constants:
    # molar weight of dry air (precision matches cmaq)
    mwair = 28.9628
    # convert proportion to ppm
    ppm_scale = 1e6
    # convert g to kg
    kg_scale = 1e-3

    conversion_list = []
    # all spcs have same shape, get from 1st
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    target_shape = ncf.get_variable(template_defn.sense_emis, tmp_spc)[:].shape
    # layer thickness constant between files
    lay_sigma = list(ncf.get_attr(template_defn.sense_emis, "VGLVLS"))
    # layer thickness measured in scaled pressure units
    lay_thick = [lay_sigma[i] - lay_sigma[i + 1] for i in range(len(lay_sigma) - 1)]
    lay_thick = np.array(lay_thick).reshape((1, len(lay_thick), 1, 1))

    for date in dt.get_datelist():
        met_file = dt.replace_date(cmaq_config.met_cro_3d, date)
        # slice off any extra layers above area of interest
        rhoj = ncf.get_variable(met_file, "DENSA_J")[:, : lay_thick.size, ...]
        xcell = ncf.get_attr(met_file, "XCELL")
        ycell = ncf.get_attr(met_file, "YCELL")
        cell_area = float(xcell * ycell)

        # assert timesteps are compatible
        assert (target_shape[0] - 1) >= (rhoj.shape[0] - 1), "incompatible timesteps"
        assert (target_shape[0] - 1) % (rhoj.shape[0] - 1) == 0, "incompatible timesteps"
        reps = (target_shape[0] - 1) // (rhoj.shape[0] - 1)

        rhoj_interp = np.zeros(target_shape)
        for r in range(reps):
            frac = float(2 * r + 1) / float(2 * reps)
            rhoj_interp[r:-1:reps, ...] = (1 - frac) * rhoj[:-1, ...] + frac * rhoj[1:, ...]
        rhoj_interp[-1, ...] = rhoj[-1, ...]
        unit_array = (ppm_scale * kg_scale * mwair) / (rhoj_interp * lay_thick) / cell_area

        conversion_list.append(unit_array)
    conversion_vector = np.array(conversion_list).flatten()
    sensitivity_vector = sensitivity.get_vector()
    sensitivity_vector_mole = sensitivity_vector * conversion_vector

    epsilon = 1e-2
    dx_template = np.zeros_like(model_input_vector)
    dx_template[:] = 1.0
    dx = epsilon * dx_template
    pert_input_vector = model_input_vector + dx
    pert_model_input = d.ModelInputData.load_from_vector_template(pert_input_vector)
    pert_model_output = transform(pert_model_input, d.ModelOutputData)
    pert_cost = pert_model_output.sum_squares()
    print("pert cost", pert_cost)
    print("finite diff ", pert_cost - init_cost)
    print("grad calc ", dx @ sensitivity_vector_mole)


if __name__ == "__main__":
    _run_grad_cmaq()
