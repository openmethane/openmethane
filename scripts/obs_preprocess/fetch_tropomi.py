"""
Download TropOMI data from the MEEO Sentinel-5P mirror on AWS

Granules are found with the Copernicus Data Space Ecosystem (CDSE) catalogue,
which supports a spatial filter, then downloaded from the public `meeo-s5p` S3
bucket that MEEO publish under the AWS Open Data Sponsorship Program. Neither
service needs credentials.

The catalogue does the work that the retired NASA GES DISC subsetting service
used to do, apart from the crop: it matches on each granule's swath footprint,
so only granules that cross the bounding box are downloaded.

Whichever product the catalogue holds for a date is the one fetched. It keeps a
single current product per orbit and deletes superseded ones, so it serves
reprocessed (RPRO) products where ESA's full mission reprocessing replaced the
originals, and offline (OFFL) products from 2022-07-26 onwards. Because two
products for one orbit would mean two copies of the same observations, that is
checked rather than assumed.

Granules are downloaded whole; the bucket offers no server-side subsetting.
`tropomi_methane_preprocess.py` drops observations outside the model grid, so
this costs bandwidth rather than accuracy. It is also the better input:
`destripe_smoothing` estimates the stripe pattern from a median over +/-100
scanlines along track, and a cropped granule gives that median less to work with
near the crop boundary.
"""

import datetime as dt
import json
import os
import re
import shutil

import boto3
import click
import dotenv
import requests
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from requests.adapters import HTTPAdapter, Retry

# Load environment variables from a local .env file
dotenv.load_dotenv()

# Public mirror of the ESA Sentinel-5P archive, maintained by MEEO
# See https://registry.opendata.aws/sentinel5p/
BUCKET = "meeo-s5p"
REGION = "eu-central-1"

# CDSE product catalogue. Searching needs no authentication.
# See https://documentation.dataspace.copernicus.eu/APIs/OData.html
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# Offline and reprocessed methane products. Near real time (NRTI) products are
# excluded: they cover the same orbits in much shorter granules, so including
# them alongside the OFFL product for an orbit would fetch the same observations
# twice.
PRODUCT_NAMES = "contains(Name,'OFFL_L2__CH4') or contains(Name,'RPRO_L2__CH4')"

# S5P_<timeliness>_L2__CH4____<start>_<end>_<orbit>_<collection>_<version>_<produced>.nc
GRANULE_TIMES = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_")


def create_session() -> requests.Session:
    """Create a session for catalogue requests that retries transient failures"""
    session = requests.Session()

    # Exponential backoff with jitter to avoid a thundering herd
    # Maximum duration would be 5 * 2 ** 4 = 80 seconds
    retries = Retry(
        total=4, backoff_factor=5.0, backoff_jitter=1.0, status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))

    return session


def create_client():
    """
    Create an S3 client for anonymous access to the public bucket

    Requests are unsigned so that the client works without AWS credentials, and
    ignores any that happen to be configured in the environment.
    """
    return boto3.client("s3", region_name=REGION, config=Config(signature_version=UNSIGNED))


def granule_period(name: str) -> tuple[dt.datetime, dt.datetime]:
    """Read the sensing period a granule covers from its filename"""
    match = GRANULE_TIMES.search(os.path.basename(name))
    if match is None:
        raise RuntimeError(f"Could not read a sensing period from the granule name {name}")

    return tuple(dt.datetime.strptime(value, "%Y%m%dT%H%M%S") for value in match.groups())


def granule_orbit(name: str) -> str:
    """Read the absolute orbit number from a granule's filename"""
    return name.split("_")[-4]


def reject_duplicate_orbits(names: list[str]) -> list[str]:
    """
    Fail if the catalogue returned more than one product for an orbit

    Each product covers a whole orbit, so two products for one orbit means two
    copies of the same observations, which the inversion would count twice. The
    catalogue keeps a single current product per orbit, but that is a property of
    what it publishes rather than something the query guarantees.
    """
    orbits: dict[str, list[str]] = {}
    for name in names:
        orbits.setdefault(granule_orbit(name), []).append(name)

    duplicated = {orbit: found for orbit, found in orbits.items() if len(found) > 1}
    if duplicated:
        detail = "; ".join(
            f"orbit {orbit}: {', '.join(sorted(found))}"
            for orbit, found in sorted(duplicated.items())
        )
        raise RuntimeError(f"The catalogue returned more than one product per orbit. {detail}")

    return names


def object_key(name: str) -> str:
    """
    Build the bucket key for a granule the catalogue returned

    The bucket is laid out by timeliness and by the UTC date a granule starts
    on, both of which are in the filename.
    """
    timeliness = name.split("_")[1]
    start, _ = granule_period(name)

    return f"{timeliness}/L2__CH4___/{start:%Y/%m/%d}/{name}"


def search_granules(
    session: requests.Session, start: dt.datetime, end: dt.datetime, box: list[float]
) -> list[str]:
    """
    Find the granules crossing a bounding box during a period

    The polygon has to close on itself, and its coordinates are EPSG 4326.
    """
    lon_min, lat_min, lon_max, lat_max = box
    polygon = (
        f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},"
        f"{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))"
    )

    response = session.get(
        CATALOGUE_URL,
        timeout=300,
        params={
            "$filter": " and ".join(
                [
                    "Collection/Name eq 'SENTINEL-5P'",
                    f"({PRODUCT_NAMES})",
                    f"ContentDate/Start lt {end:%Y-%m-%dT%H:%M:%S}.000Z",
                    f"ContentDate/End gt {start:%Y-%m-%dT%H:%M:%S}.000Z",
                    f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon}')",
                ]
            ),
            "$orderby": "ContentDate/Start",
            # Around four granules a day cross the Australian domain, so this is
            # far more than any sensible period needs and no paging is required.
            "$top": 1000,
            "$select": "Name",
        },
    )
    response.raise_for_status()

    names = [item["Name"] for item in response.json()["value"]]

    return [object_key(name) for name in reject_duplicate_orbits(names)]


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

    Data from the TropOMI instrument on the Sentinel-5P satellite is found with
    the CDSE catalogue and downloaded from the public MEEO mirror on AWS.
    """
    config = json.load(config_file)
    box = config["box"]

    print(f"Searching the CDSE catalogue between {start} and {end} within {box}")
    keys = search_granules(create_session(), start, end, box)
    print(f"Found {len(keys)} granules")

    # TropOMI covers the globe daily, so an empty period means the requested
    # dates fall outside the archive. Offline products lag acquisition by two to
    # three days, so the most recent dates are not published yet. Fail here
    # rather than leaving the preprocessing step to fail with nothing to read.
    if not keys:
        raise click.ClickException(
            f"No granules found between {start} and {end} within {box}. Products are "
            "catalogued from 2018-04-30, and lag acquisition by two to three days."
        )

    client = create_client()

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
        # The `.nc4` extension is what tropomi_methane_preprocess.py globs for
        outfn = os.path.join(outDirName, re.sub(r"\.nc$", "", os.path.basename(key)) + ".nc4")

        try:
            client.download_file(BUCKET, key, outfn)
        except (BotoCoreError, ClientError) as exc:
            print(f"Error! Failed to download this object:\ns3://{BUCKET}/{key}")
            print("The mirror is documented at https://registry.opendata.aws/sentinel5p/")

            # Abort if any files fail to download
            raise click.Abort() from exc

        print(f"{outfn} ({os.path.getsize(outfn):,} bytes)")

    print("Data fetched successfully!")


if __name__ == "__main__":
    fetch_data()
