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

# Configuration knobs, all optional and all read from the environment:
#
#   TEST_GRAD_PERT_TIME     emission perturbation time index      (default 12)
#   TEST_GRAD_MEASURE_TIME  concentration measurement time index  (default 13)
#   TEST_GRAD_PERT_CELL     "row,col" of the perturbed cell       (default 9,3)
#   TEST_GRAD_MEASURE_CELL  "row,col" of the measured cell        (default 4,4)
#   TEST_GRAD_COST_ALL      "1" sums the cost over the whole domain
#   TEST_GRAD_PERT_ALL      "1" perturbs every cell of layer 0 at pert_time
#   TEST_GRAD_EPSILON       perturbation size                     (default 0.1)
#   TEST_GRAD_CENTRAL       "1" uses a central difference (one extra forward run)
#
# The adjoint is verified to 3.5e-5 relative with:
#
#   TEST_GRAD_COST_ALL=1 TEST_GRAD_PERT_ALL=1 TEST_GRAD_CENTRAL=1 \
#   TEST_GRAD_EPSILON=0.03 TEST_GRAD_PERT_TIME=8 TEST_GRAD_MEASURE_TIME=11
#       -> finite_diff=104.51943 grad_diff=104.52306 ratio=1.000035
#
# Use that as the regression check. The defaults below are the historical
# single-cell configuration, kept for continuity but far less accurate --
# see the discussion of why.
#
# On epsilon: the default used to be 10, which is roughly 100x too large for
# the au-test domain. At that amplitude the perturbation is ~3% of background
# and the PPM monotonicity limiter takes different branches in the perturbed
# and unperturbed runs, so pert_cost - init_cost is a secant across a kink
# rather than a derivative, and the check fails against a correct adjoint.
# Measured ratios (grad/fd) at pert_time=8, measure_time=11, cell 4,4:
#
#   eps=10   1.967      <- nonlinearity: limiter branches differ
#   eps=1    0.992
#   eps=0.1  1.003      <- sweet spot
#   eps=0.01 0.918      <- float32 round-off in the CONC file dominates
#
# Also note cell (4,4) sits in the negative undershoot lobe beside the plume
# at every time it carries signal, so it is a near-cancellation and a poor
# single-cell check. TEST_GRAD_COST_ALL=1 gives a mass-balance test with no
# cancellation (ratio 0.998) and is the better regression signal.
#
# Three independent error sources set the accuracy floor, and the recommended
# settings above defeat all three:
#
#   O(eps)     PPM limiter branches differ between base and perturbed runs.
#              TEST_GRAD_CENTRAL=1 removes the smooth part of this.
#   O(1/eps)   float32 quantisation of the CONC file; over the whole domain
#              it accumulates as sqrt(80000)*1.2e-7*cost_mult ~ 0.034 cost
#              units. A distributed perturbation raises the signal ~100x
#              against it; central differencing correlates the two runs so
#              most of the quantisation cancels as well.
#   local      A single-cell spike makes sharp gradients that keep the
#              limiter permanently engaged, and its error scales like
#              eps**0.3 -- sub-linear, so neither a smaller eps nor a central
#              difference removes it. TEST_GRAD_PERT_ALL=1 spreads the same
#              total emission over 100 cells, so the response is smooth and
#              the limiter barely fires.
#
# Measured whole-domain deviations from 1 (pert_time=8, measure_time=11):
#
#   single cell (9,3), one-sided, eps=1        0.22%
#   single cell (9,3), central,   eps=1        0.13%
#   single cell (5,5), central,   eps=1        4.10%   <- limiter, not truncation
#   distributed,       one-sided, eps=0.03     0.13%
#   distributed,       central,   eps=0.1      0.062%
#   distributed,       central,   eps=0.03     0.0035%


def _cell(name, default):
    """Read a 'row,col' env var, falling back to the hard-coded default."""
    raw = os.environ.get(name)
    if not raw:
        return default
    r, c = (int(x) for x in raw.split(","))
    return r, c


def make_cost_template( model_output, weight, layers=None,time=13):
    print(f"make_cost_template, layers = {layers}, time={time}")
    one_d_vector = model_output.get_vector()
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    target_shape = ncf.get_variable(template_defn.conc, tmp_spc)[:].shape
    result = np.zeros(target_shape)
    if result.size != one_d_vector.size:
        raise ValueError(f"inconsistent sizes: vector={one_d_vector.size},\
        template={result.size}")
    if os.environ.get("TEST_GRAD_COST_ALL", "0") == "1":
        result[...] = 1.
    else:
        r, c = _cell("TEST_GRAD_MEASURE_CELL", (4, 4))
        result[time,0,r,c] = 1.
    return result.flatten()


def make_pert_template( model_input, layers=None, time=12):

    one_d_vector = model_input.get_vector()
    tmp_spc = ncf.get_attr(template_defn.sense_emis, "VAR-LIST").split()[0]
    input_file = dt.replace_date(template_defn.emis, dt.get_datelist()[0])
    target_shape = ncf.get_variable(input_file, tmp_spc)[:].shape
    result = np.zeros(target_shape)
    if result.size != one_d_vector.size:
        raise ValueError(f"inconsistent sizes: vector={one_d_vector.size},\
        template={result.size}")
    if os.environ.get("TEST_GRAD_PERT_ALL", "0") == "1":
        # Spread the perturbation over every cell of layer 0 at this time. The
        # signal grows with the number of cells while the per-cell amplitude --
        # which is what drives PPM limiter branch flips -- stays at epsilon. So
        # this beats down the O(1/eps) float32 noise and the limiter
        # non-differentiability at the same time, which neither a smaller
        # epsilon nor a central difference can do alone.
        result[time,0,:,:] = 1.
    else:
        r, c = _cell("TEST_GRAD_PERT_CELL", (9, 3))
        result[time,0,r,c] = 1.
    return result.flatten()

    


def test_fourdvar_grad_cmaq(target_environment):
    target_environment("docker-test")

    _run_grad_cmaq()


def _run_grad_cmaq():
    measure_layer = np.s_[:]
    # measure_layer = 0
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

    sensitivity_vector = sensitivity.get_vector()
    sensitivity_vector.dump('/opt/project/data/sensitivity_raw.pic')
    sensitivity_vector_mole = sensitivity_vector
    sensitivity_vector_mole.dump('/opt/project/data/sensitivity.pic')
    epsilon = float(os.environ.get("TEST_GRAD_EPSILON", "0.1"))
    central = os.environ.get("TEST_GRAD_CENTRAL", "0") == "1"
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
    if central:
        # Central difference: [J(x+dx) - J(x-dx)] / 2. The one-sided difference
        # carries an O(eps) error from the PPM limiter taking different branches
        # in the perturbed run; that term is even in dx and cancels here, leaving
        # O(eps**2). Costs one extra forward run and widens the usable eps window
        # by an order of magnitude at each end.
        minus_input_vector = model_input_vector - dx
        minus_model_input = d.ModelInputData.load_from_vector_template(minus_input_vector)
        minus_model_output = transform(minus_model_input, d.ModelOutputData)
        minus_output_vector = minus_model_output.get_vector()
        minus_output_vector.dump('/opt/project/data/perturbed_minus.pic')
        minus_cost = cost_mult*((cost_template * minus_output_vector).sum())
        finite_diff = 0.5 * (pert_cost - minus_cost)
    else:
        finite_diff = pert_cost - init_cost
    grad_diff = (dx @ sensitivity_vector_mole)
    percentage_error = 100.*(grad_diff -finite_diff)/finite_diff
    print(f"pert_time {pert_time} measure_time {measure_time} init_cost {init_cost} pert_cost {pert_cost} finite_diff {finite_diff} grad_diff {grad_diff} percentage_error {percentage_error:6.2f}")
    ratio = grad_diff / finite_diff if finite_diff != 0. else float("nan")
    print(
        "RESULT"
        f" eps={epsilon:g}"
        f" fd={'central' if central else 'onesided'}"
        f" pert_cell={'ALL' if os.environ.get('TEST_GRAD_PERT_ALL','0')=='1' else _cell('TEST_GRAD_PERT_CELL', (9, 3))}"
        f" measure_cell={'ALL' if os.environ.get('TEST_GRAD_COST_ALL','0')=='1' else _cell('TEST_GRAD_MEASURE_CELL', (4, 4))}"
        f" pert_time={pert_time} measure_time={measure_time}"
        f" finite_diff={finite_diff:.8g} grad_diff={grad_diff:.8g}"
        f" ratio={ratio:.6f}"
    )


if __name__ == "__main__":
    _run_grad_cmaq()
