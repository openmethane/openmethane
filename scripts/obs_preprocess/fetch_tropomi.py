"""
Download TropOMI data from the NASA GES DISC API

Granules are discovered with the GES DISC subsetting API, then downloaded from
Cloud OPeNDAP with a DAP4 constraint expression that limits the download to the
variables and scanlines we actually need.

GES DISC retired the `SUBSET_LEVEL2` agent, which used to perform the spatial
crop server-side. Its replacement, the `OPeNDAP` agent, rejects `crop: True`
and only returns links to whole granules, so the crop is now done client-side
via DAP4 constraint expressions.
"""

import json
import os
import re
import shutil
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from time import sleep
from typing import Any

import click
import dotenv
import numpy as np
import requests
from netCDF4 import Dataset
from requests.adapters import HTTPAdapter, Retry

# Load environment variables from a local .env file
dotenv.load_dotenv()

API_URL = "https://disc.gsfc.nasa.gov/service/subset/jsonwsp"

DAP_NS = {"dap": "http://xml.opendap.org/ns/DAP/4.0#"}

# Stride used when scanning a granule's geolocation to find the scanlines that
# intersect the bounding box. A TropOMI scanline is ~7km along-track, so a
# stride of 10 locates the box to within ~70km, which the padding below covers.
GEOLOCATION_STRIDE = 10

# Variables required by scripts/obs_preprocess/tropomi_methane_preprocess.py,
# grouped by their trailing dimensions so the right constraint can be built.
#
# Only the scanline dimension is subset. The full 215-pixel swath is kept
# because destripe_smoothing() in the preprocessor operates across the swath,
# so narrowing ground_pixel would change its results.

# (time, scanline, ground_pixel)
SWATH_VARIABLES = (
    "/PRODUCT/latitude",
    "/PRODUCT/longitude",
    "/PRODUCT/qa_value",
    "/PRODUCT/methane_mixing_ratio_bias_corrected",
    "/PRODUCT/methane_mixing_ratio_precision",
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/solar_zenith_angle",
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/viewing_zenith_angle",
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/solar_azimuth_angle",
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/viewing_azimuth_angle",
    "/PRODUCT/SUPPORT_DATA/INPUT_DATA/pressure_interval",
    "/PRODUCT/SUPPORT_DATA/DETAILED_RESULTS/surface_albedo_SWIR",
    "/PRODUCT/SUPPORT_DATA/DETAILED_RESULTS/aerosol_optical_thickness_SWIR",
)

# (time, scanline, ground_pixel, corner|layer)
SWATH_VARIABLES_4D = (
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/latitude_bounds",
    "/PRODUCT/SUPPORT_DATA/GEOLOCATIONS/longitude_bounds",
    "/PRODUCT/SUPPORT_DATA/INPUT_DATA/methane_profile_apriori",
    "/PRODUCT/SUPPORT_DATA/DETAILED_RESULTS/column_averaging_kernel",
)

# (time, scanline)
SWATH_VARIABLES_2D = ("/PRODUCT/time_utc",)

# Requested unsliced so that the `level` dimension is present in the output;
# the preprocessor reads `product.dimensions["level"].size` but never the
# variable's data. See the note on unsliced requests in build_constraint().
COORDINATE_VARIABLES = ("/PRODUCT/level",)


def create_session() -> requests.Session:
    """
    Create a new requests session

    Creates the .netrc file with the Earthdata credentials if it does not exist.
    Uses the EARTHDATA_USERNAME and EARTHDATA_PASSWORD environment variables if available
    to setup the required `~/.netrc` file.
    See [Data Access](https://disc.gsfc.nasa.gov/information/documents?title=Data%20Access)
    for more information about accessing NASA data.

    In the case where the `.netrc` file already exists,
    users must add the required line manually.
    """
    session = requests.Session()

    # Retry on 429 (too many requests) and 500 status codes
    # Exponential backoff with jitter to avoid a thundering herd
    # Maximum duration would be 5 * 2 ** 6 = 320 seconds
    retries = Retry(
        total=6, backoff_factor=5.0, backoff_jitter=1.0, status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    credentials_path = Path("~/.netrc").expanduser()
    if not credentials_path.exists():
        # Create the .netrc file with the Earthdata credentials
        if not os.environ.get("EARTHDATA_USERNAME") or not os.environ.get("EARTHDATA_PASSWORD"):
            raise click.ClickException(
                "EARTHDATA_USERNAME or EARTHDATA_PASSWORD environment variables missing"
            )

        print("Writing .netrc file")

        with open(credentials_path, "a") as file:
            file.write(
                "machine urs.earthdata.nasa.gov login {} password {}".format(
                    os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
                )
            )

    return session


def get_http_data(body: dict[str, Any], session: requests.Session):
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    response = session.post(API_URL, json=body, headers=hdrs, timeout=30)
    response.raise_for_status()

    content = response.json()
    # Check for errors
    if content["type"] == "jsonwsp/fault":
        print("API Error: faulty request")
        raise RuntimeError(f"Invalid type found in {content}")
    return content


def search_granules(session: requests.Session, box: list[float], start, end) -> list[dict]:
    """
    Find the granules intersecting a bounding box and time period

    Uses the GES DISC subsetting API, which returns Cloud OPeNDAP links to whole
    granules. The bounding box only filters which granules are returned; the
    granules themselves are not cropped.
    """
    init_data = {
        "methodname": "subset",
        "args": {
            "box": box,
            "crop": False,
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": "OPeNDAP",
            "role": "subset",
            "data": [{"datasetId": "S5P_L2__CH4____HiR_2"}],
        },
        "type": "jsonwsp/request",
        "version": "1.0",
    }

    print(f"Submitting request to the API: {init_data}")

    response = get_http_data(init_data, session)
    myJobId = response["result"]["jobId"]

    # Construct JSON WSP request for API method: GetStatus
    status_request = {
        "methodname": "GetStatus",
        "version": "1.0",
        "type": "jsonwsp/request",
        "args": {"jobId": myJobId},
    }

    while response["result"]["Status"] in ["Accepted", "Running"]:
        sleep(1)
        response = get_http_data(status_request, session)
        status = response["result"]["Status"]
        percent = response["result"]["PercentCompleted"]
        print("Job status: %s (%d%c complete)" % (status, percent, "%"))

    if response["result"]["Status"] == "Succeeded":
        print("Job Finished:  {}".format(response["result"]["message"]))
    else:
        print("Job Failed: {}".format(response["fault"]["code"]))
        sys.exit(1)

    # Construct JSON WSP request for API method: GetResult
    batchsize = 20
    results_request = {
        "methodname": "GetResult",
        "version": "1.0",
        "type": "jsonwsp/request",
        "args": {"jobId": myJobId, "count": batchsize, "startIndex": 0},
    }

    # Retrieve the results in JSON in multiple batches
    # Initialize variables, then submit the first GetResults request
    # Add the results from this batch to the list and increment the count
    results = []
    count = 0
    response = get_http_data(results_request, session)
    count = count + response["result"]["itemsPerPage"]
    results.extend(response["result"]["items"])

    # Increment the startIndex and keep asking for more results until we have them all
    total = response["result"]["totalResults"]
    while count < total:
        results_request["args"]["startIndex"] += batchsize
        response = get_http_data(results_request, session)
        count = count + response["result"]["itemsPerPage"]
        results.extend(response["result"]["items"])

    # Check on the bookkeeping
    print("Retrieved %d out of %d expected items" % (len(results), total))

    # Sort the results into documents and URLs
    docs = []
    granules = []
    for item in results:
        try:
            if item["start"] and item["end"]:
                granules.append(item)
        except Exception:
            docs.append(item)

    # Print out the documentation links, but do not download them
    print("\nDocumentation:")
    for item in docs:
        print(item["label"] + ": " + item["link"])

    return granules


def granule_filename(label: str) -> str:
    """
    Derive an output filename from a Cloud OPeNDAP result label

    Labels look like
    `S5P_L2__CH4____HiR.2%3AS5P_OFFL_L2__CH4____20221207T011249_....nc.dap.nc4`.
    The `.SUB.nc4` suffix is kept for consistency with the files the retired
    `SUBSET_LEVEL2` agent produced, which downstream globs still expect.
    """
    name = urllib.parse.unquote(label).split(":")[-1]
    return re.sub(r"\.nc(\.dap\.nc4)?$", "", name) + ".SUB.nc4"


def opendap_base_url(link: str) -> str:
    """Strip the response suffix from a Cloud OPeNDAP link to get its base URL"""
    return re.sub(r"\.dap\.nc4$", "", link)


def dap_request(session: requests.Session, url: str, constraint: str) -> requests.Response:
    """Issue a DAP4 request, raising for any non-success response"""
    response = session.get(url, params={"dap4.ce": constraint}, timeout=600)
    response.raise_for_status()
    return response


def count_scanlines(session: requests.Session, base_url: str) -> int:
    """
    Read a granule's scanline count from its DAP4 metadata response

    Constraining the DMR to a single variable keeps this to ~10kB rather than
    the ~400kB of the full metadata response.
    """
    response = dap_request(session, base_url + ".dmr", "/PRODUCT/latitude")

    # The DMR comes from the authenticated Earthdata OPeNDAP server
    root = ET.fromstring(response.content)  # noqa: S314
    for dimension in root.iter(f"{{{DAP_NS['dap']}}}Dimension"):
        if dimension.get("name") == "scanline":
            return int(dimension.get("size"))

    raise RuntimeError(f"No scanline dimension found in the DMR for {base_url}")


def find_scanline_range(
    session: requests.Session, base_url: str, box: list[float], n_scanlines: int
) -> tuple[int, int] | None:
    """
    Find the range of scanlines that intersect the bounding box

    Downloads a strided sample of the granule's geolocation, then pads the
    matched range by one stride on each side so that no intersecting scanline
    is dropped.

    Returns None if the granule does not intersect the bounding box. The
    granule search filters on each granule's bounding polygon, which is coarser
    than the swath itself, so some granules genuinely do not overlap.
    """
    lon_min, lat_min, lon_max, lat_max = box

    stride = f"[0][0:{GEOLOCATION_STRIDE}:{n_scanlines - 1}][]"
    response = dap_request(
        session, base_url + ".dap.nc4", f"/PRODUCT/latitude{stride};/PRODUCT/longitude{stride}"
    )

    # netCDF4 can only open a file on disk, so buffer the response in memory
    with Dataset("geolocation.nc4", memory=response.content) as ds:
        latitude = ds["/PRODUCT/latitude"][0]
        longitude = ds["/PRODUCT/longitude"][0]

    in_box = (
        (longitude >= lon_min)
        & (longitude <= lon_max)
        & (latitude >= lat_min)
        & (latitude <= lat_max)
    )
    sampled = np.where(in_box.any(axis=1))[0]
    if sampled.size == 0:
        return None

    first = max(0, (int(sampled.min()) - 1) * GEOLOCATION_STRIDE)
    last = min(n_scanlines - 1, (int(sampled.max()) + 1) * GEOLOCATION_STRIDE)
    return first, last


def build_constraint(first_scanline: int, last_scanline: int) -> str:
    """
    Build the DAP4 constraint expression for a scanline range

    Note that every swath variable is sliced. A constraint whose result covers a
    variable's full extent makes Hyrax reuse the source chunk layout, and the
    resulting file has an invalid fletcher32 checksum that netCDF cannot read.
    Any strict subset is rewritten without the checksum and reads correctly.
    """
    scanlines = f"[0][{first_scanline}:{last_scanline}]"

    variables = list(COORDINATE_VARIABLES)
    variables += [f"{name}{scanlines}" for name in SWATH_VARIABLES_2D]
    variables += [f"{name}{scanlines}[]" for name in SWATH_VARIABLES]
    variables += [f"{name}{scanlines}[][]" for name in SWATH_VARIABLES_4D]

    return ";".join(variables)


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

    Data from the TropOMI instrument on the Sentinel-5P satellite
    is available from the NASA GES DISC API.
    """
    config = json.load(config_file)
    session = create_session()

    box = config["box"]
    granules = search_granules(session, box, start, end)

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

    print("\nCloud OPeNDAP output:")

    for item in granules:
        base_url = opendap_base_url(item["link"])

        try:
            n_scanlines = count_scanlines(session, base_url)
            scanline_range = find_scanline_range(session, base_url, box, n_scanlines)

            if scanline_range is None:
                print(f"{item['label']}: no overlap with the bounding box, skipping")
                continue

            first_scanline, last_scanline = scanline_range
            response = dap_request(
                session,
                base_url + ".dap.nc4",
                build_constraint(first_scanline, last_scanline),
            )
        except requests.exceptions.RequestException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            print(f"Error! Status code is {status_code} for this URL:\n{base_url}")
            if status_code == 401:
                print("Unauthorised: Check your Earthdata credentials in the ~/.netrc file")
            print("Help for downloading data is at https://disc.gsfc.nasa.gov/data-access")

            # Abort if any files fail to download
            raise click.Abort() from exc

        outfn = os.path.join(outDirName, granule_filename(item["label"]))
        with open(outfn, "wb") as f:
            f.write(response.content)

        kept = last_scanline - first_scanline + 1
        print(f"{outfn} ({kept} of {n_scanlines} scanlines, {len(response.content):,} bytes)")

    print("Data fetched successfully!")


if __name__ == "__main__":
    fetch_data()
