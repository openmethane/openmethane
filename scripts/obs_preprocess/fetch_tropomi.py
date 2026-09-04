"""
Download TropOMI data from the MEEO Sentinel-5P mirror on AWS

Granules are found with the Copernicus Data Space Ecosystem (CDSE) catalogue,
which is queried for granules that intersect with the domain bounding box in
the period of interest. Granules are then downloaded by name from the public
`meeo-s5p` S3 bucket published by MEEO under the AWS Open Data Sponsorship
Program. Neither service needs credentials.

A small number of granules are known to be unreliable objects in the mirror,
having never synced correctly from ESA - either zero bytes, or a non-zero size
that is still short of what the granule really is. Both are detected by
comparing the mirror's reported size against the size CDSE's catalogue has for
the same granule, before spending time on the transfer. Either way, the
granule is instead downloaded directly from CDSE, which does need an
account's credentials (CDSE_USERNAME/CDSE_PASSWORD).

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

# Downloading a product directly (rather than searching the catalogue) does
# need an account's credentials.
# See https://documentation.dataspace.copernicus.eu/APIs/OData.html#authentication-and-authorisation
CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"  # noqa: S105
)
CDSE_DOWNLOAD_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"


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


class UnreliableMirrorObject(RuntimeError):
    """A granule's object in the mirror cannot be trusted to hold the whole granule"""


def download_from_mirror(client, key: str, outfn: str, expected_size: int | None = None) -> None:
    """
    Download one granule from the MEEO mirror to outfn

    The mirror has been found to hold a handful of unreliable objects for
    granules that never synced correctly from ESA - some report zero bytes,
    others a non-zero size that is still wrong - so the object's size is
    checked before spending time on the transfer. Passing `expected_size` (the
    granule's real size, from the CDSE catalogue) catches the latter case too;
    without it, only a zero-byte object is caught. `download_file` writes to a
    temporary name and renames onto `outfn` on success, so a truncated
    transfer should not be possible; the download is still re-checked and
    retried once, since the mirror is outside our control.
    """
    remote_size = client.head_object(Bucket=BUCKET, Key=key)["ContentLength"]

    if remote_size == 0:
        raise UnreliableMirrorObject(f"{key} is an empty (0 byte) object in the {BUCKET} mirror")

    if expected_size is not None and remote_size != expected_size:
        raise UnreliableMirrorObject(
            f"{key} is {remote_size:,} bytes in the {BUCKET} mirror but {expected_size:,} "
            "bytes in the CDSE catalogue"
        )

    for attempt in range(2):
        client.download_file(BUCKET, key, outfn)

        if os.path.getsize(outfn) == remote_size:
            return

        os.remove(outfn)

    raise RuntimeError(
        f"{key} did not download to its expected size of {remote_size:,} bytes "
        f"after {attempt + 1} attempts"
    )


def cdse_access_token(session: requests.Session) -> str:
    """
    Get a bearer token for downloading directly from CDSE

    Unlike the catalogue search and the mirror, this needs a real CDSE
    account's credentials, read from CDSE_USERNAME/CDSE_PASSWORD. An account
    can be registered for free at https://dataspace.copernicus.eu/.
    """
    username = env.str("CDSE_USERNAME", None)
    password = env.str("CDSE_PASSWORD", None)

    if not username or not password:
        raise click.ClickException(
            "CDSE_USERNAME and CDSE_PASSWORD must be set to fall back to CDSE for a "
            "granule that is empty in the MEEO mirror. Register a free account at "
            "https://dataspace.copernicus.eu/"
        )

    response = session.post(
        CDSE_TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    response.raise_for_status()

    return response.json()["access_token"]


def find_product_id(session: requests.Session, name: str) -> str:
    """Look up a granule's id in the CDSE catalogue by its filename"""
    response = session.get(
        CATALOGUE_URL,
        timeout=60,
        params={"$filter": f"Name eq '{name}'", "$select": "Id"},
    )
    response.raise_for_status()
    products = response.json()["value"]

    if not products:
        raise click.ClickException(f"{name} was not found in the CDSE catalogue")

    return products[0]["Id"]


def download_from_cdse(session: requests.Session, token: str, key: str, outfn: str) -> None:
    """
    Download one granule directly from CDSE, bypassing the MEEO mirror

    Used as a fallback for the handful of granules known to be empty in the
    mirror. Streams to a temporary name and renames onto `outfn` on success,
    matching the mirror download's all-or-nothing guarantee.
    """
    name = os.path.basename(key)
    product_id = find_product_id(session, name)

    response = session.get(
        f"{CDSE_DOWNLOAD_URL}({product_id})/$value",
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=300,
    )
    response.raise_for_status()

    tmp_outfn = f"{outfn}.part"
    try:
        with open(tmp_outfn, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    except Exception:
        os.remove(tmp_outfn)
        raise

    os.rename(tmp_outfn, outfn)


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
) -> list[tuple[str, int]]:
    """
    Find the granules crossing a bounding box during a period

    Returns each granule's bucket key alongside its size in the CDSE
    catalogue, so a caller can tell whether the mirror's copy of it is
    trustworthy before downloading it.

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
            "$select": "Name,ContentLength",
        },
    )
    response.raise_for_status()

    sizes = {item["Name"]: item["ContentLength"] for item in response.json()["value"]}

    return [(object_key(name), sizes[name]) for name in select_one_per_orbit(list(sizes))]


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

    session = create_session()

    print(f"Searching the CDSE catalogue between {start} and {end} within {box}")
    granules = search_granules(session, start, end, box)
    print(f"Found {len(granules)} granules")

    # An empty result can mean the requested dates fall outside the archive,
    # that offline products haven't caught up yet (they lag acquisition by two
    # to three days), or a genuine instrument outage. None of those should
    # fail the daily workflow: downstream steps cope with there being no
    # TROPOMI data for the day, so just carry on with nothing to download.
    if not granules:
        print(
            f"No granules found between {start} and {end} within {box}. Products are "
            "catalogued from 2018-04-30 and lag acquisition by two to three days; this "
            "may also mean an instrument outage. Continuing with no TROPOMI data."
        )

    client = create_client()

    os.makedirs(output, exist_ok=True)

    print(f"\nDownloading to {output}:")

    unrecoverable = []
    cdse_token = None

    for key, expected_size in granules:
        # Granules keep the name they have in the bucket, which is unique and
        # carries the sensing period, so nothing here has to invent one.
        outfn = os.path.join(output, os.path.basename(key))

        # A file being present and non-empty means it downloaded completely and
        # can be reused. A zero-byte file is never treated as done, so a granule
        # left behind by an older bug (or genuinely empty in the mirror) is
        # retried instead of being skipped forever.
        if os.path.exists(outfn) and os.path.getsize(outfn) > 0:
            print(f"{outfn} already present, skipping")
            continue

        try:
            download_from_mirror(client, key, outfn, expected_size)
        except UnreliableMirrorObject as exc:
            print(f"Warning: {exc}")
            print(f"Falling back to CDSE for {os.path.basename(key)}")

            try:
                if cdse_token is None:
                    cdse_token = cdse_access_token(session)

                download_from_cdse(session, cdse_token, key, outfn)
            except click.ClickException:
                raise
            except Exception as exc:  # reported below, not fatal to the other granules
                print(f"Error! CDSE fallback also failed for {key}:\n{exc}")
                unrecoverable.append(key)
                continue

            print(f"{outfn} ({os.path.getsize(outfn):,} bytes) [via CDSE]")
            continue
        except (BotoCoreError, ClientError) as exc:
            print(f"Error! Failed to download this object:\ns3://{BUCKET}/{key}")
            print("The mirror is documented at https://registry.opendata.aws/sentinel5p/")

            # Abort if any files fail to download
            raise click.Abort() from exc

        print(f"{outfn} ({os.path.getsize(outfn):,} bytes)")

    if unrecoverable:
        raise click.ClickException(
            "The following granules are unreliable in the MEEO mirror and could not be "
            "downloaded from CDSE either:\n"
            + "\n".join(f"  s3://{BUCKET}/{key}" for key in unrecoverable)
        )

    print("Data fetched successfully!")


if __name__ == "__main__":
    fetch_data()
