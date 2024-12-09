import numpy as np
import pathlib

from postproc.calculate_average_emissions import calculate_average_emissions

def posterior_emissions_postprocess(
    posterior_multipliers: np.ndarray,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
):
    # what most of our downstream consumers are interested in is the actual
    # "measurable" emissions, which we can produce by multiplying the fourdvar
    # result by the template emission (prior) in each cell.
    return calculate_average_emissions(
        posterior_multipliers=normalise_posterior(posterior_multipliers),
        template_dir=template_dir,
        emis_template=emis_template,
    )

def normalise_posterior(
        posterior_multipliers: np.ndarray,
) -> np.ndarray:
    # we can't assume how many dimensions this will have, preserve the last two and average over all the rest
    PRESERVED_DIMENSIONS = 2
    if posterior_multipliers.ndim <= PRESERVED_DIMENSIONS:
        return posterior_multipliers

    averaged_dimensions = posterior_multipliers.ndim - PRESERVED_DIMENSIONS
    averaged_axes = tuple(range(averaged_dimensions))
    return posterior_multipliers.mean(axis=averaged_axes)
