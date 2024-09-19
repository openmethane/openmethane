#!/usr/bin/env python
"""
Download CAMS data on pressure levels

Here we use EAC4 data product,
which is the latest generation of the Copernicus Atmosphere Monitoring Service (CAMS)
reanalysis data products.

Download volume: ~1.4GB / month
Description: https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/cams-global-reanalysis-eac4

Assumes that the user has a valid ADS account and has set up the necessary credentials
in `~/.cdsapirc`.
"""

from datetime import datetime
from pathlib import Path

import cdsapi
import click

DATETIME_FORMAT = "%Y-%m-%d"


@click.command()
@click.option(
    "-s",
    "--start-date",
    required=True,
    help="Start date in format YYYY-MM-DD",
    default="2023-01-01",
)
@click.option(
    "-e",
    "--end-date",
    required=True,
    help="End date in format YYYY-MM-DD",
    default="2023-01-31",
)
@click.argument(
    "output",
    type=click.Path(exists=False, path_type=Path),
    default="data/inputs/cams_eac4_methane.nc",
)
def download_cams_input(start_date: str, end_date: str, output: str | Path):
    """
    Download Methane chemistry data from CAMS on pressure levels

    These data are stored on tape, so the download may be queued for several minutes
    while the data are retrieved.
    """
    c = cdsapi.Client()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if datetime.strptime(start_date, DATETIME_FORMAT) > datetime.strptime(
        end_date, DATETIME_FORMAT
    ):
        raise ValueError("Start date must be before end date")

    # fmt: off
    c.retrieve(
        "cams-global-reanalysis-eac4",
        {
            "variable": "methane_chemistry",
            "pressure_level": [
                "1", "2", "3", "5", "7", "10", "20",
                "30", "50", "70", "100", "150", "200",
                "250", "300", "400", "500", "600", "700",
                "800", "850", "900", "925", "950", "1000",
            ],
            "date": f"{start_date}/{end_date}",
            "time": [f"{hour:02d}:00" for hour in range(0, 24, 3)],
            "format": "netcdf",
        },
        output,
    )
    # fmt: on


if __name__ == "__main__":
    download_cams_input()
