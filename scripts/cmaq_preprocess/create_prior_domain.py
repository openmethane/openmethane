#!/usr/bin/env python
#
# Copyright 2023 The Superpower Institute Ltd.
#
# This file is part of OpenMethane.
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

"""
Generate domain file for use by the prior

The generated file is based on the WRF Geometry file and then is subset to match the CMAQ domain.
The domain for OpenMethane is a combination of the WRF domain as specified in the setup-wrf
repository and the value of BTRIM for the CMAQ domain (namely in MCIP).
The generated domain file is then published to a Cloudflare bucket to be consumed by the prior.

Each domain file has a domain name and version associated with it.

Initially we are using the semver versioning scheme of `MAJOR.MINOR.PATCH`:
* increasing MAJOR version means breaking changes (your "bad" case)
* increasing MINOR version means new features/changes but no change to existing
* increasing PATCH typically means a bug fix or no-op change

This only needs to be run once for each new domain/modification.
"""

import os
import pathlib

import click
import xarray as xr

# implicitly loads the .env.{TARGET} file
from fourdvar.params import cmaq_config, date_defn
from fourdvar.util.date_handle import replace_date

root_dir = pathlib.Path(__file__).parents[2]


def create_domain_info(
    geometry_file: pathlib.Path,
    cross_file: pathlib.Path,
    dot_file: pathlib.Path,
) -> xr.Dataset:
    """
    Create a new domain from the input WRF domain and subsets it to match the CMAQ domain

    Parameters
    ----------
    geometry_file
        Path to the WRF geometry file
    cross_file
        Path to the MCIP cross file
    dot_file
        Path to the MCIP dot file

    Returns
    -------
        The regridded domain information as an xarray dataset
    """
    domain_ds = xr.Dataset()

    with xr.open_dataset(geometry_file) as geomXr:
        for attr in ["DX", "DY", "TRUELAT1", "TRUELAT2", "MOAD_CEN_LAT", "STAND_LON"]:
            domain_ds.attrs[attr] = geomXr.attrs[attr]

    with xr.open_dataset(cross_file) as croXr:
        for var in ["LAT", "LON"]:
            domain_ds[var] = croXr[var]
            domain_ds[var] = croXr[var].squeeze(
                dim="LAY", drop=True
            )  # copy but remove the 'LAY' dimension

        domain_ds["LANDMASK"] = croXr["LWMASK"].squeeze(
            dim="LAY", drop=True
        )  # copy but remove the 'LAY' dimension

    with xr.open_dataset(dot_file) as dotXr:
        # some repetition between the geom and grid files here, XCELL=DX and YCELL=DY
        # - XCELL, YCELL: size of a single cell in m
        # - XCENT, YCENT: lat/long of grid centre point
        # - XORIG, YORIG: position of 0,0 cell in grid coordinates (in m)
        for attr in ["XCELL", "YCELL", "XCENT", "YCENT", "XORIG", "YORIG"]:
            domain_ds.attrs[attr] = croXr.attrs[attr]
        for var in ["LATD", "LOND"]:
            domain_ds[var] = dotXr[var].rename({"COL": "COL_D", "ROW": "ROW_D"})

    return domain_ds


def write_domain_info(domain_ds: xr.Dataset, domain_path: pathlib.Path):
    """
    Write the domain information to a netcdf file

    Parameters
    ----------
    domain_ds
        The domain information as a xarray dataset
    domain_path
        The path to write the domain information to
    """
    print(f"Writing domain to {domain_path}")
    domain_path.parent.mkdir(parents=True, exist_ok=True)

    domain_ds.to_netcdf(domain_path)


def validate_mcip_path(required_content: str):
    def validator(ctx, param, value):
        path = pathlib.Path(value)

        # Existence of the file is checked by `click.Path`

        if not path.name.startswith(required_content):
            raise click.BadParameter(f"Filename must start with {required_content}")

        return pathlib.Path(value)

    return validator


def clean_directories(geometry_directory, output_directory, name, version):
    geometry_directory = pathlib.Path(geometry_directory)

    if output_directory is None:
        output_directory = geometry_directory
    else:
        output_directory = pathlib.Path(output_directory)

    if not geometry_directory.exists():
        raise click.BadParameter(
            f"WRF geometry for domain {name}@{version} does not exist. Check {geometry_directory}"
        )
    return geometry_directory, output_directory


@click.command(name="create_prior_domain")
@click.option(
    "--name",
    type=str,
    required=True,
    help="Name of the WRF domain",
    default=lambda: os.environ.get("DOMAIN_NAME"),
)
@click.option(
    "--version",
    type=str,
    required=True,
    help="Version identifier of the WRF domain. Must start with v",
    default=lambda: os.environ.get("DOMAIN_VERSION"),
)
@click.option(
    "--domain-index",
    type=int,
    default=1,
    help="Number of the domain to process (Currently we don't support nested domains)",
)
@click.option(
    "--cross",
    type=click.Path(exists=True, file_okay=True),
    callback=validate_mcip_path("GRIDCRO2D"),
    required=True,
    help="Path to the GRIDCRO2D file for the domain",
    default=lambda: replace_date(cmaq_config.grid_cro_2d, date_defn.start_date),
)
@click.option(
    "--dot",
    type=click.Path(exists=True, file_okay=True),
    callback=validate_mcip_path("GRIDDOT2D"),
    required=True,
    help="Path to the GRIDDOT2D file for the domain",
    default=lambda: replace_date(cmaq_config.grid_dot_2d, date_defn.start_date),
)
@click.option(
    "--geometry-directory",
    help="Override the geometry directory. Assumes that there is a `geo_em.d{domain_index:02}.nc`"
    " file present in the directory",
    type=click.Path(dir_okay=True, file_okay=False),
    default=lambda: os.environ.get("GEO_DIR"),
)
@click.option(
    "--output-directory",
    help="Override the output directory",
    default=None,
    type=click.Path(dir_okay=True, file_okay=False),
)
def main(
    name: str,
    version: str,
    domain_index: int,
    cross: pathlib.Path,
    dot: pathlib.Path,
    geometry_directory: str,
    output_directory: str | None,
):
    """
    Generate domain file for use by the prior

    This assumes that the WRF domain has been fetched and is present in `data/domains`
    """

    if not version.startswith("v"):
        raise click.BadParameter("Version should not start with v")

    geometry_directory, output_directory = clean_directories(
        geometry_directory, output_directory, name, version
    )

    domain = create_domain_info(
        geometry_file=geometry_directory / f"geo_em.d{domain_index:02}.nc",
        cross_file=pathlib.Path(cross),
        dot_file=pathlib.Path(dot),
    )

    filename = f"prior_domain_{name}_{version}.d{domain_index:02}.nc"
    write_domain_info(domain, output_directory / filename)


if __name__ == "__main__":
    main()
