#!/usr/bin/env python
"""
Download CAMS methane fields to use as boundary and initial conditions

Three products are available, chosen by CAMS_PRODUCT (the inversion by default):

- `eac4`: the CAMS reanalysis (EAC4) on pressure levels. CH4 is not assimilated
  in EAC4, it is a free-running model field. About 1.4GB / month.
  https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/cams-global-reanalysis-eac4
- `inversion`: the CAMS greenhouse gas inversion (TM5-MP 4D-Var, surface network
  plus satellite). The ADS cannot subset it, so each month is a 2.2GB global file
  which is fetched with parallel range requests, then cut to the domain.
  https://ads.atmosphere.copernicus.eu/datasets/cams-global-greenhouse-gas-inversion
- `forecasts`: the CAMS global greenhouse gas forecasts (IFS, assimilating TROPOMI,
  GOSAT and IASI), from March 2024. Each day's 00Z forecast at leads of 0, 6, 12
  and 18 h, flattened to one valid time axis.
  https://ads.atmosphere.copernicus.eu/datasets/cams-global-greenhouse-gas-forecasts

Assumes that the user has a valid ADS account and has set up the necessary credentials
in `~/.cdsapirc`.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import click

from openmethane.cmaq_preprocess.cams_download import (
    cut_inversion_to_domain,
    download_inversion,
    download_pressure_levels,
)
from openmethane.cmaq_preprocess.read_config_cmaq import load_config_from_env
from openmethane.fourdvar.env import create_env

DATETIME_FORMAT = "%Y-%m-%d"


@click.command()
@click.option(
    "-s",
    "--start-date",
    required=True,
    help="Start date in format YYYY-MM-DD",
)
@click.option(
    "-e",
    "--end-date",
    required=True,
    help="End date in format YYYY-MM-DD",
)
@click.argument(
    "output",
    type=click.Path(exists=False, path_type=Path),
    required=False,
)
def download_cams_input(
    start_date: str, end_date: str, output: str | Path | None, force: bool = False
):
    """
    Download CAMS methane fields for the date range

    The product is CAMS_PRODUCT. OUTPUT defaults to CAMS_FILE, or a name made from the
    product, the inversion's release and the dates.

    EAC4 data are stored on tape, so the download may be queued for several minutes
    while the data are retrieved.
    """
    start = datetime.strptime(start_date, DATETIME_FORMAT).date()
    end = datetime.strptime(end_date, DATETIME_FORMAT).date()
    if start > end:
        raise ValueError("Start date must be before end date")

    config = load_config_from_env()
    output = Path(output or config.input_cams_file)
    if not force and output.exists():
        print(f"CAMS file {output} already exists, skipping")
        return

    output.parent.mkdir(parents=True, exist_ok=True)

    domain_file = create_env().path("DOMAIN_FILE")
    if config.cams_product == "inversion":
        with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
            monthly_files = download_inversion(
                start, end, config.cams_inversion_version, Path(scratch)
            )
            cut_inversion_to_domain(monthly_files, domain_file, start, end, output)
    else:
        download_pressure_levels(config.cams_product, start, end, output, domain_file)


if __name__ == "__main__":
    download_cams_input()
