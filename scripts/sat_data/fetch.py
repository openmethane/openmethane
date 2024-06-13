"""
Download TropOMI data from the NASA GES DISC API

Uses a bounding box to limit the required data.
"""

import json
import os
import shutil
import sys
from pathlib import Path
from time import sleep
from typing import Any

import click
import dotenv
import requests

# Load environment variables from a local .env file
dotenv.load_dotenv()

API_URL = "https://disc.gsfc.nasa.gov/service/subset/jsonwsp"


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

    credentials_path = Path("~/.netrc").expanduser()
    if not credentials_path.exists():
        # Create the .netrc file with the Earthdata credentials
        if not os.environ.get("EARTHDATA_USERNAME") or not os.environ.get("EARTHDATA_PASSWORD"):
            raise click.ClickException(
                "EARTHDATA_USERNAME or EARTHDATA_PASSWORD environment variables missing"
            )
            raise click.Abort()

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
    return content


@click.command()
@click.option(
    "-c",
    "--config-file",
    help="Path to configuration file",
    default="config.json",
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

    initData = {
        "methodname": "subset",
        "args": {
            "box": config["box"],
            "crop": True,
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": "SUBSET_LEVEL2",
            "presentation": "CROP",
            "role": "subset",
            "data": [{"datasetId": "S5P_L2__CH4____HiR_2"}],
        },
        "type": "jsonwsp/request",
        "version": "1.0",
    }

    response = get_http_data(initData, session)
    myJobId = response["result"]["jobId"]

    # Construct JSON WSP request for API method: GetStatus
    status_request = {
        "methodname": "GetStatus",
        "version": "1.0",
        "type": "jsonwsp/request",
        "args": {"jobId": myJobId},
    }

    while response["result"]["Status"] in ["Accepted", "Running"]:
        sleep(5)
        response = get_http_data(status_request, session)
        status = response["result"]["Status"]
        percent = response["result"]["PercentCompleted"]
        print("Job status: %s (%d%c complete)" % (status, percent, "%"))

    if response["result"]["Status"] == "Succeeded":
        print("Job Finished:  %s" % response["result"]["message"])
    else:
        print("Job Failed: %s" % response["fault"]["code"])
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
    urls = []
    for item in results:
        try:
            if item["start"] and item["end"]:
                urls.append(item)
        except Exception:
            docs.append(item)

    # Print out the documentation links, but do not download them
    print("\nDocumentation:")
    for item in docs:
        print(item["label"] + ": " + item["link"])

    # Use the requests library to submit the HTTP_Services URLs and write out the results.
    print("\nHTTP_services output:")

    # make directory to store outputs if it doesn't already exist
    os.makedirs(output, exist_ok=True)

    # TODO: change to ISO format
    start_str = start.strftime("%Y%m%d-%H-%M-%S")
    end_str = end.strftime("%Y%m%d-%H-%M-%S")
    boxString = "_".join(str(x) for x in config["box"])
    outDirName = os.path.join(output, f"{start_str}_{end_str}_{boxString}")
    isExist = os.path.exists(outDirName)

    if not isExist:
        os.mkdir(outDirName)

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

    for item in urls:
        URL = item["link"]
        result = session.get(URL, timeout=30)
        try:
            result.raise_for_status()
            outfn = os.path.join(outDirName, item["label"])
            f = open(outfn, "wb")
            f.write(result.content)
            f.close()
            print(outfn)
        except requests.exceptions.RequestException:
            print("Error! Status code is %d for this URL:\n%s" % (result.status_code, URL))
            print("Help for downloading data is at https://disc.gsfc.nasa.gov/data-access")
    print("Data fetched successfully!")


if __name__ == "__main__":
    fetch_data()
