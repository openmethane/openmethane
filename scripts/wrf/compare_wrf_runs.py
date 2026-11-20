"""
Compare the output folders of two WRF runs and report every difference.

Usage: compare_wrf_runs.py OURS THEIRS [--ignore GLOB]...

Exits 0 if the runs match, 1 if they differ. Logs are never compared.
"""

import pathlib
import sys

import click

from openmethane.wrf.compare import compare_runs


@click.command()
@click.argument("ours", type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path))
@click.argument("theirs", type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path))
@click.option("--ignore", multiple=True, help="Glob of relative paths to leave out")
def main(ours: pathlib.Path, theirs: pathlib.Path, ignore: tuple[str, ...]):
    report = compare_runs(ours, theirs, ignore)
    for path, differences in report.items():
        click.echo(path)
        for difference in differences:
            click.echo(f"  {difference}")
    click.echo("The runs match." if not report else f"{len(report)} files differ.")
    sys.exit(1 if report else 0)


if __name__ == "__main__":
    main()
