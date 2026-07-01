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

import os 
import numpy as np

import openmethane.fourdvar.datadef as d
import openmethane.fourdvar.user_driver as user
import openmethane.fourdvar.util.archive_handle as archive
import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar._transform import transform
from openmethane.fourdvar.params import archive_defn, cmaq_config, template_defn

def make_cost_template( model_output, weight, layers=None,time=13):
    print(f"make_cost_template, layers = {layers}, time={time}")
    one_d_vector = model_output.get_vector()
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    target_shape = ncf.get_variable(template_defn.conc, tmp_spc)[:].shape
    result = np.zeros(target_shape)
    if result.size != one_d_vector.size:
        raise ValueError(f"inconsistent sizes: vector={one_d_vector.size},\
        template={result.size}")
    if layers is None:
        result[...] = 1.
    else:
        result[time,layers,4,4] = 1 #weight[layers]
    return result.flatten()


def make_pert_template( model_input, layers=None, time=12):
    print(f"make_pert_template, layers = {layers}, time={time}")

    one_d_vector = model_input.get_vector()
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    input_file = dt.replace_date(template_defn.emis, dt.get_datelist()[0])
    print(input_file)
    target_shape = ncf.get_variable(input_file, tmp_spc)[:].shape
    result = np.zeros(target_shape)
    print(result.shape)
    if result.size != one_d_vector.size:
        raise ValueError(f"inconsistent sizes: vector={one_d_vector.size},\
        template={result.size}")
    if layers is None:
        result[...] = 1.
    else:
        result[time,layers,:,:] = 1.
    return result.flatten()

    


def test_fourdvar_grad_cmaq(target_environment):
    target_environment("docker-test")

    _run_grad_cmaq()


def _run_grad_cmaq():
    # measure_layer = np.s_[:]
    measure_layer = 0
    pert_layer = 0              # 
    measure_time=int(os.environ.get("TEST_GRAD_MEASURE_TIME",default="13"))
    pert_time=int(os.environ.get("TEST_GRAD_PERT_TIME",default="12"))
    cost_mult=1.e3
    archive_defn.experiment = "tmp_grad_cmaq"
    archive_defn.desc_name = ""

    archive_path = archive.get_archive_path()
    print(f"saving results in:\n{archive_path}")
    lay_sigma = list(ncf.get_attr(template_defn.sense_emis, "VGLVLS"))
    # layer thickness measured in scaled pressure units
    lay_thick = [lay_sigma[i] - lay_sigma[i + 1] for i in range(len(lay_sigma) - 1)]
    lay_thick = np.array(lay_thick).reshape((1, len(lay_thick), 1, 1))
    thick = lay_thick.squeeze()

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

    for date in dt.get_datelist():
        met_file = dt.replace_date(cmaq_config.met_cro_3d, date)
        # slice off any extra layers above area of interest
        rhoj = ncf.get_variable(met_file, "DENSA_J")[ ...]
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
    conversion_vector.dump('/opt/project/data/conversion.pic')

    print("get prior in PhysicalData format")
    physical = user.get_background()
    physical.emis['CH4'][...] = 0.
    modelInput = transform(physical, d.ModelInputData)
    model_input_vector = modelInput.get_vector()
    modelOutput = transform(modelInput, d.ModelOutputData) # 
    cost_template = make_cost_template(modelOutput, thick, layers=measure_layer,
                                       time=measure_time)
    model_output_vector = modelOutput.get_vector()
    model_output_vector.dump('/opt/project/data//unperturbed.pic')
    cost_template.dump('/opt/project/data/template.pic')
    
    sampled_output_vector = cost_template * model_output_vector # region targeted for cost function
    sampled_output_vector.dump('/opt/project/data/forcing.pic')
    init_cost = cost_mult*(sampled_output_vector.sum())
    forcing_vector = cost_mult*cost_template   # adjoint of squared sum
    # now we want to divide forcing_vector by layer thickness which needs some reshaping
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    target_shape = ncf.get_variable(template_defn.sense_emis, tmp_spc)[:].shape
    forcing_reshape = forcing_vector.reshape(target_shape)
    # forcing_reshape /= lay_thick*rhoj[measure_time,0,4,4] 
    forcing_vector = forcing_reshape.flatten()
    adjointForcing = d.AdjointForcingData.load_from_vector_template(forcing_vector)
    sensitivity = transform(adjointForcing, d.SensitivityData)
    # units are now in cf/ppm/s, we need to convert to cf/mole/s which means dealing with air density
    sensitivity_vector = sensitivity.get_vector()
    sensitivity_vector.dump('/opt/project/data/sensitivity_raw.pic')
    sensitivity_vector_mole = sensitivity_vector * 8
    sensitivity_vector_mole.dump('/opt/project/data/sensitivity.pic')
    epsilon = 1.
    pert_template = make_pert_template(modelInput, layers=pert_layer,
                                       time=pert_time)
    dx = epsilon * pert_template
    pert_input_vector = model_input_vector + dx
    pert_model_input = d.ModelInputData.load_from_vector_template(pert_input_vector)
    pert_model_output = transform(pert_model_input, d.ModelOutputData)
    pert_output_vector = pert_model_output.get_vector()
    pert_output_vector.dump('/opt/project/data/perturbed.pic')
    sampled_pert_output_vector = cost_template * pert_output_vector
    pert_cost = cost_mult*(sampled_pert_output_vector.sum()) 
    finite_diff = pert_cost - init_cost
    grad_diff = (dx @ sensitivity_vector_mole)
    percentage_error = 100.*(grad_diff -finite_diff)/((grad_diff+finite_diff)/2.)
    print(F"pert_time = {pert_time}, measure_time={measure_time}") # 
    print(f"pert_time {pert_time} measure_time {measure_time} init_cost {init_cost} pert_cost {pert_cost} finite_diff {finite_diff} grad_diff {grad_diff} percentage_error {percentage_error:6.2f}")
    print(f"percentage error {100.*(grad_diff -finite_diff)/((grad_diff+finite_diff)/2.):6.2f}")


if __name__ == "__main__":
    _run_grad_cmaq()
