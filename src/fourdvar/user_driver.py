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

import logging
import os
import pathlib
import pickle

from scipy.optimize import fmin_l_bfgs_b as minimize

import fourdvar.datadef as d
import fourdvar.util.archive_handle as archive
import fourdvar.util.cmaq_handle as cmaq
from fourdvar._transform import transform
from fourdvar.params import archive_defn, data_access, input_defn
from postproc.calculate_average_emissions import calculate_average_emissions

logger = logging.getLogger(__name__)

observed = None
background = None
iter_num = 0

allow_neg_values = True


def setup():
    """application: setup any requirements for minimizer to run (eg: check resources, etc.)
    input: None
    output: None.
    """
    archive.setup()
    if input_defn.inc_icon is False:
        logger.warning("input_defn.inc_icon is turned off.")
    bg = get_background()
    obs = get_observed()
    bg.archive("prior.ncf")
    obs.archive("observed.pickle")


def cleanup():
    """application: cleanup any unwanted output from minimizer (eg: delete checkpoints, etc.)
    input: None
    output: None.
    """
    cmaq.wipeout_fwd()


def get_background():
    """application: get the background / prior estimate for the minimizer
    input: None
    output: PhysicalData (prior estimate).
    """
    global background

    if background is None:
        background = d.PhysicalData.from_file(input_defn.prior_file)
    return background


def get_observed():
    """application: get the observed observations for the minimizer
    input: None
    output: ObservationData.
    """
    global observed

    if observed is None:
        observed = d.ObservationData.from_file(input_defn.obs_file)
        observed.assert_params()
    return observed


def callback_func(current_vector):
    """Called once for every iteration of minimizer.
    input: np.array
    output: None.
    """
    global iter_num
    iter_num += 1
    current_unknown = d.UnknownData(current_vector)
    current_physical = transform(current_unknown, d.PhysicalData)
    current_physical.archive(f"iter{iter_num:04}.ncf")
    if archive_defn.iter_model_output is True:
        current_model_output = d.ModelOutputData()
        current_model_output.archive(f"conc_iter{iter_num:04}.ncf")
    if archive_defn.iter_obs_lite is True:
        current_model_output = d.ModelOutputData()
        current_obs = transform(current_model_output, d.ObservationData)
        current_obs.archive(f"obs_lite_iter{iter_num:04}.pic.gz", force_lite=True)

    logger.info(f"iter_num = {iter_num}")


def minim(cost_func, grad_func, init_guess):
    """application: the minimizer function
    input: cost function, gradient function, prior estimate / background
    output: list (1st element is numpy.ndarray of solution, the rest are user-defined).
    """
    # turn on skipping of unneeded fwd calls
    data_access.allow_fwd_skip = True

    start_cost = cost_func(init_guess)
    start_grad = grad_func(init_guess)
    start_dict = {"start_cost": start_cost, "start_grad": start_grad}

    if allow_neg_values is True:
        bounds = None
    else:
        bounds = len(init_guess) * [(0, None)]

    answer = minimize(
        cost_func, init_guess, bounds=bounds, fprime=grad_func, callback=callback_func, maxiter=20
    )
    # check answer warnflag, etc for success
    answer = [*list(answer), start_dict]
    return answer


def post_process(out_physical, metadata):
    """application: how to handle/save results of minimizer
    input: PhysicalData (solution), list (user-defined output of minim)
    output: None.
    """
    out_physical.archive("final_solution.ncf")
    posterior_emissions_path = os.path.join(archive.get_archive_path(), "posterior_emissions.nc")
    calculate_average_emissions( pathlib.Path(archive.get_archive_path()),
                                 pathlib.Path( posterior_emissions_path),
                                 )
    with open(os.path.join(archive.get_archive_path(), "ans_details.pickle"), "wb") as f:
        pickle.dump(metadata, f)
