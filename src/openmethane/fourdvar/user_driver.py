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

import pathlib

import numpy as np
import xarray as xr
from scipy.optimize import fmin_l_bfgs_b as minimize

import openmethane.fourdvar.datadef as d
import openmethane.fourdvar.transfunc as t
import openmethane.fourdvar.util.archive_handle as archive
import openmethane.fourdvar.util.cmaq_handle as cmaq
from openmethane.fourdvar._transform import transform
from openmethane.fourdvar.env import env
from openmethane.fourdvar.params import (
    archive_defn,
    data_access,
    input_defn,
    template_defn,
)
from openmethane.fourdvar.util import bcon_offset
from openmethane.postproc.posterior_emissions_postprocess import posterior_emissions_postprocess
from openmethane.util.logger import get_logger

logger = get_logger(__name__)

observed = None
background = None
iter_num = 0


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
    archive_gradient(current_vector, f"gradient_iter{iter_num:04}.ncf")
    if archive_defn.iter_model_output is True:
        current_model_output = d.ModelOutputData()
    if archive_defn.iter_obs_lite is True:
        current_model_output = d.ModelOutputData()
        current_obs = transform(current_model_output, d.ObservationData)
        current_obs.archive(f"obs_lite_iter{iter_num:04}.pic.gz", force_lite=True)

    logger.info(f"iter_num = {iter_num}")


def archive_gradient(current_vector, filename):
    """Archive the latest gradient, converted to physical space.
    input: np.array (the iterate the gradient should belong to), str
    output: None.
    """
    if data_access.prev_gradient is None:
        return
    # L-BFGS-B ends each line search on the accepted point, so the latest
    # gradient should be at current_vector. Recomputing it would cost an
    # extra adjoint run, so only warn if it is not.
    if not np.array_equal(data_access.prev_gradient_vector, current_vector):
        logger.warning(f"{filename} holds a gradient from a point other than the current iterate")
    current_gradient = t.uncondition_adjoint(d.UnknownData(data_access.prev_gradient))
    current_gradient.archive(filename)


def get_bounds(physical_template, allow_negative_emissions: bool) -> tuple[list[tuple], np.ndarray]:
    """Bounds on each unknown, in the order condition() lays them out.

    Returns the bounds and a mask of which unknowns are boundary offsets.

    Emissions are multipliers, bounded below by zero unless negative emissions
    are allowed. The boundary offsets are always bounded so that the BCON CMAQ
    reads, staged BCON plus offset, stays non-negative. The unknowns are
    scaled by their uncertainty, so each bound is divided by it too.
    """
    p = physical_template
    emis_len = p.nstep_emis * p.nlays_emis * p.nrows * p.ncols
    emis_bound = (None, None) if allow_negative_emissions else (0, None)
    bounds = []
    is_bcon = []
    for spc in p.spcs:
        if input_defn.inc_icon is True:
            bounds.append((None, None))
        bounds += emis_len * [emis_bound]
        lower = bcon_offset.offset_lower_bound(
            spc, p.bcon_region_map, p.bcon_step_start, p.bcon_step_end, p.bcon_region
        )
        scaled = (lower / p.bcon_unc[spc]).flatten()
        is_bcon += [False] * (len(bounds) - len(is_bcon))
        bounds += [(None if np.isinf(b) else float(b), None) for b in scaled]
        is_bcon += [True] * scaled.size
    return bounds, np.array(is_bcon)


def minim(
    cost_func,
    grad_func,
    init_guess: np.ndarray,
    allow_negative_emissions: bool = True,
    physical_template=None,
):
    """application: the minimizer function
    input: cost function, gradient function, prior estimate / background
    output: list (1st element is numpy.ndarray of solution, the rest are user-defined).
    """
    # turn on skipping of unneeded fwd calls
    data_access.allow_fwd_skip = True
    data_access.prev_gradient = None
    data_access.prev_gradient_vector = None

    start_cost = cost_func(init_guess, archive_obs_file="simulobs_first_guess.pic.gz")
    start_grad = grad_func(init_guess)
    # iter_num is 0 for a fresh run (the prior), or the iteration resumed from
    archive_gradient(init_guess, f"gradient_iter{iter_num:04}.ncf")
    start_dict = {"start_cost": start_cost, "start_grad": start_grad}

    bounds, is_bcon = get_bounds(physical_template, allow_negative_emissions)
    assert len(bounds) == init_guess.size, "bounds do not match the unknowns"
    maxiter = env.int("MAX_ITERATIONS", 20)
    logger.info(f"Running minimiser with a maximum of {maxiter} iteration")
    answer = minimize(
        cost_func,
        init_guess,
        bounds=bounds,
        fprime=grad_func,
        callback=callback_func,
        maxiter=maxiter,
        # Very verbose output on every successful iteration
        iprint=200,
    )
    # many boundary offsets on their bound suggest regions that span too wide a
    # range of concentrations
    lower = np.array([np.nan if lo is None else lo for lo, _ in bounds])
    at_bound = np.isclose(answer[0], lower) & is_bcon
    logger.info(f"{at_bound.sum()} of {is_bcon.sum()} boundary offsets are on their lower bound")
    # check answer warnflag, etc for success
    answer = [*list(answer), start_dict]
    return answer


def post_process(out_physical: d.PhysicalData, metadata):
    """application: how to handle/save results of minimizer
    input: PhysicalData (solution), list (user-defined output of minim)
    output: None.
    """
    # fourdvar solves for multipliers against the template emissions (prior)
    # for every grid cell. save the raw result, which will be useful internally.
    out_physical.archive("posterior-multipliers.nc")

    # open the prior emissions to use as a template format for the results file
    prior_emissions = xr.open_dataset(template_defn.prior_file)

    # what most of our downstream consumers are interested in is the actual
    # "measurable" emissions, which we can produce by multiplying the fourdvar
    # result by the template emission (prior) in each cell.
    species = "CH4"
    posterior_emissions = posterior_emissions_postprocess(
        posterior_multipliers=out_physical.emis[species],
        prior_emissions_ds=prior_emissions,
        template_dir=template_defn.template_dir,
        species=species,
    )
    posterior_emissions.to_netcdf(
        pathlib.Path(archive.get_archive_path(), "posterior-emissions.nc")
    )
