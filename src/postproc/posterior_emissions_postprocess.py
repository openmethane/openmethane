import pathlib

from fourdvar.datadef import PhysicalData
from postproc.calculate_average_emissions import calculate_average_emissions

def posterior_emissions_postprocess(
    posterior_multipliers: PhysicalData,
    template_dir: pathlib.Path,
    emis_template: str = "emis_*.nc",
):
    # what most of our downstream consumers are interested in is the actual
    # "measurable" emissions, which we can produce by multiplying the fourdvar
    # result by the template emission (prior) in each cell.
    return calculate_average_emissions(
        posterior_multipliers=posterior_multipliers,
        template_dir=template_dir,
        emis_template=emis_template,
    )