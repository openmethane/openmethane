"""
Download TropOMI data from the MEEO Sentinel-5P mirror on AWS

Granules are listed from the public `meeo-s5p` S3 bucket, which MEEO publish
under the AWS Open Data Sponsorship Program. The bucket is anonymously
readable, so no credentials are needed.

The bucket serves whole granules; there is no server-side subsetting. Granules
that do not overlap the configured bounding box are discarded after download,
and the rest are kept intact. `tropomi_methane_preprocess.py` already drops
observations outside the model grid, so keeping whole granules costs bandwidth
rather than accuracy. It is also the more defensible input: `destripe_smoothing`
takes medians along both swath axes, so its results depend on how much of the
orbit is present.
"""

import datetime as dt
import json
import os
import re
import shutil

import boto3
import click
import dotenv
import numpy as np
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from netCDF4 import Dataset

# Load environment variables from a local .env file
dotenv.load_dotenv()

# Public mirror of the ESA Sentinel-5P archive, maintained by MEEO
# See https://registry.opendata.aws/sentinel5p/
BUCKET = "meeo-s5p"
REGION = "eu-central-1"

# Offline (OFFL) methane products. The bucket also carries `NRTI` and `RPRO`
# under the same layout, so switching timeliness is a change to this prefix.
PREFIX = "OFFL/L2__CH4___"

# S5P_OFFL_L2__CH4____<start>_<end>_<orbit>_<collection>_<version>_<produced>.nc
GRANULE_TIMES = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_")


def create_client():
    """
    Create an S3 client for anonymous access to the public bucket

    Requests are unsigned so that the client works without AWS credentials, and
    ignores any that happen to be configured in the environment.
    """
    return boto3.client("s3", region_name=REGION, config=Config(signature_version=UNSIGNED))


def granule_period(key: str) -> tuple[dt.datetime, dt.datetime]:
    """Read the sensing period a granule covers from its filename"""
    match = GRANULE_TIMES.search(os.path.basename(key))
    if match is None:
        raise RuntimeError(f"Could not read a sensing period from the granule name {key}")

    return tuple(dt.datetime.strptime(value, "%Y%m%dT%H%M%S") for value in match.groups())


def list_granules(client, start: dt.datetime, end: dt.datetime) -> list[str]:
    """
    List the granules covering a period

    Granules are stored under the UTC date they start on. One that starts late
    on the preceding day can still run into the period, so that day is listed
    too and the sensing period from each filename decides what is kept.
    """
    keys = []

    date = start.date() - dt.timedelta(days=1)
    while date <= end.date():
        prefix = f"{PREFIX}/{date:%Y/%m/%d}/"
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)

        for page in pages:
            for item in page.get("Contents", []):
                granule_start, granule_end = granule_period(item["Key"])
                if granule_start < end and granule_end > start:
                    keys.append(item["Key"])

        date += dt.timedelta(days=1)

    return sorted(keys)


def intersects_box(path: str, box: list[float]) -> bool:
    """
    Check whether a granule holds any observation inside the bounding box

    Read after download rather than before, because every geolocation variable
    is stored as a single compressed chunk spanning the whole orbit; a ranged
    read could not fetch less than all of it.
    """
    lon_min, lat_min, lon_max, lat_max = box

    with Dataset(path) as ds:
        latitude = ds["/PRODUCT/latitude"][:]
        longitude = ds["/PRODUCT/longitude"][:]

    return bool(
        np.any(
            (longitude >= lon_min)
            & (longitude <= lon_max)
            & (latitude >= lat_min)
            & (latitude <= lat_max)
        )
    )


def output_filename(key: str) -> str:
    """
    Derive an output filename from an object key

    The `.nc4` extension is what `tropomi_methane_preprocess.py` globs for.
    """
    return re.sub(r"\.nc$", "", os.path.basename(key)) + ".nc4"


@click.command()
@click.option(
    "-c",
    "--config-file",
    help="Path to configuration file",
    default="config/obs_preprocess/config.json",
    type=click.File(),
)
@click.option(
    "-s",
    "--start",
    help="Datetime of start of the period to fetch",
    type=click.DateTime(),
    required=True,
)
@click.option(
    "-e",
    "--end",
    help="Datetime of end of the period to fetch",
    type=click.DateTime(),
    required=True,
)
@click.argument("output", type=click.Path(file_okay=False, dir_okay=True, writable=True))
def fetch_data(config_file, start, end, output):
    """Fetch TropOMI data

    Data from the TropOMI instrument on the Sentinel-5P satellite is available
    from the public MEEO mirror on AWS.
    """
    config = json.load(config_file)
    box = config["box"]
    client = create_client()

    print(f"Listing granules between {start} and {end} in s3://{BUCKET}/{PREFIX}")
    keys = list_granules(client, start, end)
    print(f"Found {len(keys)} granules")

    # TropOMI covers the globe daily, so an empty period means the requested
    # dates are outside the archive or the mirror has fallen behind. Fail here
    # rather than leaving the preprocessing step to fail with nothing to read.
    if not keys:
        raise click.ClickException(
            f"No granules found between {start} and {end} in s3://{BUCKET}/{PREFIX}"
        )

    os.makedirs(output, exist_ok=True)

    start_str = start.strftime("%Y-%m-%dT%H%M")
    end_str = end.strftime("%Y-%m-%dT%H%M")
    boxString = "_".join(str(x) for x in box)
    outDirName = os.path.join(output, f"{start_str}_{end_str}_{boxString}")

    os.makedirs(outDirName, exist_ok=True)

    # empty output directory if necessary
    for filename in os.listdir(outDirName):
        file_path = os.path.join(outDirName, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

    print(f"\nDownloading to {outDirName}:")

    for key in keys:
        outfn = os.path.join(outDirName, output_filename(key))

        try:
            client.download_file(BUCKET, key, outfn)
        except (BotoCoreError, ClientError) as exc:
            print(f"Error! Failed to download this object:\ns3://{BUCKET}/{key}")
            print("The mirror is documented at https://registry.opendata.aws/sentinel5p/")

            # Abort if any files fail to download
            raise click.Abort() from exc

        if not intersects_box(outfn, box):
            os.unlink(outfn)
            print(f"{os.path.basename(key)}: no overlap with the bounding box, discarded")
            continue

        print(f"{outfn} ({os.path.getsize(outfn):,} bytes)")

    print("Data fetched successfully!")


if __name__ == "__main__":
    fetch_data()
