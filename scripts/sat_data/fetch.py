import json
import os
import shutil
import sys
from time import sleep

import certifi
import click
import dotenv
import requests
import urllib3

dotenv.load_dotenv()

http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())
API_URL = "https://disc.gsfc.nasa.gov/service/subset/jsonwsp"
TOKEN=os.environ.get("EARTHDATA_TOKEN")


def get_http_data(request):
    hdrs = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {TOKEN}"}
    data = json.dumps(request)
    r = http.request("POST", API_URL, body=data, headers=hdrs)
    response = json.loads(r.data)
    # Check for errors
    if response["type"] == "jsonwsp/fault":
        print("API Error: faulty request")
    return response


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
def fetch_data(config_file, start, end):
    """Fetch TropOMI data

    Data from the TropOMI instrument on the Sentinel-5P satellite
    is available from the NASA GES DISC API.
    """
    config = json.load(config_file)

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

    response = get_http_data(initData)
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
        response = get_http_data(status_request)
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
    response = get_http_data(results_request)
    count = count + response["result"]["itemsPerPage"]
    results.extend(response["result"]["items"])

    # Increment the startIndex and keep asking for more results until we have them all
    total = response["result"]["totalResults"]
    while count < total:
        results_request["args"]["startIndex"] += batchsize
        response = get_http_data(results_request)
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
    if not os.path.exists(config["data"]):
        os.mkdir(config["data"])

    # TODO: change to ISO format
    start_str = start.strftime("%Y%m%d-%H-%M-%S")
    end_str = end.strftime("%Y%m%d-%H-%M-%S")
    boxString = "_".join(str(x) for x in config["box"])
    outDirName = f'{config["data"]}/{start_str}_{end_str}_{boxString}'
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
        result = requests.get(URL, timeout=30)
        try:
            result.raise_for_status()
            outfn = os.path.join(outDirName, item["label"])
            f = open(outfn, "wb")
            f.write(result.content)
            f.close()
            print(outfn)
        except Exception:
            print(result)
            print("Error! Status code is %d for this URL:\n%s" % (result.status_code, URL))
            print("Help for downloading data is at https://disc.gsfc.nasa.gov/data-access")


if __name__ == "__main__":
    fetch_data()
    print("Data fetched successfully!")
