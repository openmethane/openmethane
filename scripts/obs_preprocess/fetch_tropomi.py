"""
Download TropOMI data from the MEEO Sentinel-5P mirror on AWS

Granules are found with the Copernicus Data Space Ecosystem (CDSE) catalogue,
which is queried for granules that intersect with the domain bounding box in
the period of interest. Granules are then downloaded by name from the public
`meeo-s5p` S3 bucket published by MEEO under the AWS Open Data Sponsorship
Program. Neither service needs credentials.

Granules are downloaded whole, unlike the previous NASA GES DISC subsetting
service.
"""

import datetime as dt
import os
import re

import boto3
import click
import dotenv
import pyproj
import requests
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from requests.adapters import HTTPAdapter, Retry

from openmethane.fourdvar.env import env
from openmethane.util.domain import domain_bounding_box

# Load environment variables from a local .env file
dotenv.load_dotenv()

# Public mirror of the ESA Sentinel-5P archive, maintained by MEEO
# See https://registry.opendata.aws/sentinel5p/
BUCKET = "meeo-s5p"
REGION = "eu-central-1"

# CDSE product catalogue. Searching needs no authentication.
# See https://documentation.dataspace.copernicus.eu/APIs/OData.html
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CATALOGUE_CRS = pyproj.CRS.from_epsg(4326)


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

# S5P_<timeliness>_L2__CH4____<start>_<end>_<orbit>_<collection>_<version>_<produced>.nc
GRANULE_TIMES = re.compile(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_")

def granule_period(name: str) -> tuple[dt.datetime, dt.datetime]:
    """Read the sensing period a granule covers from its filename"""
    match = GRANULE_TIMES.search(os.path.basename(name))
    if match is None:
        raise RuntimeError(f"Could not read a sensing period from the granule name {name}")

    return tuple(dt.datetime.strptime(value, "%Y%m%dT%H%M%S") for value in match.groups())


def granule_orbit(name: str) -> str:
    """Read the absolute orbit number from a granule's filename"""
    return name.split("_")[-4]


def granule_precedence(name: str) -> tuple[str, int]:
    """
    Rank a granule against others covering the same orbit

    Processor version comes first, since a later version supersedes an earlier
    one. Versions are zero padded, so they compare correctly as strings. Where two
    products share a version, the reprocessed one wins, having been produced with
    the whole mission in view rather than within days of the overpass.
    """
    version = name.split("_")[-2]
    timeliness = name.split("_")[1]

    return version, timeliness == "RPRO"


def select_one_per_orbit(names: list[str]) -> list[str]:
    """
    Keep a single product for each orbit, preferring the most recent

    Each product covers a whole orbit, so two products for one orbit would put the
    same observations into the inversion twice. The catalogue publishes one current
    product per orbit and deletes those a reprocessing supersedes, so this is not
    expected to do anything; it warns rather than failing if it ever does, because
    picking the better of the two is not a reason to stop a run.
    """
    orbits: dict[str, list[str]] = {}
    for name in names:
        orbits.setdefault(granule_orbit(name), []).append(name)

    selected = []
    for orbit, found in orbits.items():
        chosen = max(found, key=granule_precedence)

        if len(found) > 1:
            print(
                f"Warning: the catalogue returned {len(found)} products for orbit {orbit} "
                f"({', '.join(sorted(found))}); using {chosen}"
            )

        selected.append(chosen)

    return selected


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

    # Offline (OFFL) and reprocessed (RPRO) methane products. OFFL is how each
    # granule is initially released. If a granule appears in RPRO it means a
    # major improvement to the model, and OFFL is deprecated for that granule.
    # Near real time (NRTI) products are excluded.
    product_names = "contains(Name,'OFFL_L2__CH4') or contains(Name,'RPRO_L2__CH4')"

    response = session.get(
        CATALOGUE_URL,
        timeout=300,
        params={
            "$filter": " and ".join(
                [
                    "Collection/Name eq 'SENTINEL-5P'",
                    f"({product_names})",
                    f"ContentDate/Start lt {end:%Y-%m-%dT%H:%M:%S}.000Z",
                    f"ContentDate/End gt {start:%Y-%m-%dT%H:%M:%S}.000Z",
                    f"OData.CSC.Intersects(area=geography'SRID={CATALOGUE_CRS.to_epsg()};{polygon}')",
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

    return [object_key(name) for name in select_one_per_orbit(names)]


@click.command()
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
def fetch_data(start, end, output):
    """Fetch TropOMI data

    Data from the TropOMI instrument on the Sentinel-5P satellite is found with
    the CDSE catalogue and downloaded from the public MEEO mirror on AWS.

    The area to fetch comes from the domain file named by DOMAIN_FILE.
    """
    domain_file = env.path("DOMAIN_FILE")
    box = domain_bounding_box(domain_file, CATALOGUE_CRS)
    print(f"Domain {domain_file} covers {box}")

    print(f"Searching the CDSE catalogue between {start} and {end} within {box}")
    keys = search_granules(create_session(), start, end, box)
    print(f"Found {len(keys)} granules")

    # An empty result can mean the requested dates fall outside the archive,
    # that offline products haven't caught up yet (they lag acquisition by two
    # to three days), or a genuine instrument outage. None of those should
    # fail the daily workflow: downstream steps cope with there being no
    # TROPOMI data for the day, so just carry on with nothing to download.
    if not keys:
        print(
            f"No granules found between {start} and {end} within {box}. Products are "
            "catalogued from 2018-04-30 and lag acquisition by two to three days; this "
            "may also mean an instrument outage. Continuing with no TROPOMI data."
        )

    client = create_client()

    os.makedirs(output, exist_ok=True)

    print(f"\nDownloading to {output}:")

    for key in keys:
        # Granules keep the name they have in the bucket, which is unique and
        # carries the sensing period, so nothing here has to invent one.
        outfn = os.path.join(output, os.path.basename(key))

        # `download_file` writes to a temporary name and renames on success, so a
        # file being present means it downloaded completely and can be reused.
        if os.path.exists(outfn):
            print(f"{outfn} already present, skipping")
            continue

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
