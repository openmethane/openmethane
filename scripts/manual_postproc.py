import click
import glob
import pathlib

from netCDF4 import Dataset

from postproc.posterior_emissions_postprocess import posterior_emissions_postprocess, normalise_posterior

SOLUTION_FILENAME = "posterior_multipliers.nc"

@click.command()
@click.option(
    "-f",
    "--posterior-file",
    help="Path to posterior multipliers",
    type=click.File(),
)
@click.option(
    "-a",
    "--archive-dir",
    help="Path to the archive folder for the monthly run",
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    required=True,
)
@click.option(
    "-t",
    "--template-dir",
    help="Path to the template folder for the monthly run",
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    required=True,
)
@click.option(
    "-i",
    "--iter-template",
    help="Filename glob for iteration files in the archive folder",
    default="iter*.ncf",
    type=click.STRING,
)
def manual_postproc(
        archive_dir: pathlib.Path,
        template_dir: pathlib.Path,
        iter_template: str,
        posterior_file: pathlib.Path | None = None,
):
    if posterior_file is not None:
        posterior_file = posterior_file
    else:
        posterior_file = find_last_iteration(archive_dir, iter_template)

    with Dataset(posterior_file) as posterior_nc:
        emis_array = posterior_nc['/emis']['CH4'][...]

    posterior_emissions = posterior_emissions_postprocess(
        posterior_multipliers=emis_array,
        template_dir=template_dir,
    )

    output_file = pathlib.Path(archive_dir, "posterior_emissions.nc")
    print(f"writing postprocessed file to {output_file}")
    posterior_emissions.to_netcdf(output_file)


def find_last_iteration(
        archive_dir: pathlib.Path,
        iter_template: str
) -> pathlib.Path:
    """ returns successful convergence output if present, otherwise last iteration """
    solution_path = pathlib.Path(archive_dir, SOLUTION_FILENAME)
    if solution_path.is_file():
        return solution_path
    else:
        iter_glob = pathlib.Path(archive_dir, iter_template)
        iter_files = glob.glob(str(iter_glob))
        if iter_files is not None:
            iter_files.sort()
            return iter_files[-1]
        raise ValueError(f'no converged iterations found at {iter_glob}')


if __name__ == "__main__":
    manual_postproc()