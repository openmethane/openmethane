import json
import os
import shutil
import sys
from datetime import datetime
from time import sleep

import certifi
import requests
import urllib3

configFile = open("config.json")
config = json.load(configFile)

http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())
API_URL = "https://disc.gsfc.nasa.gov/service/subset/jsonwsp"


def get_http_data(request):
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(request)
    r = http.request("POST", API_URL, body=data, headers=hdrs)
    response = json.loads(r.data)
    # Check for errors
    if response["type"] == "jsonwsp/fault":
        print("API Error: faulty request")
    return response


initData = {
    "methodname": "subset",
    "args": {
        "box": config["box"],
        "crop": True,
        "start": config["start"],
        "end": config["end"],
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

start = datetime.fromisoformat(config["start"]).strftime("%Y%m%d-%H-%M-%S")
end = datetime.fromisoformat(config["end"]).strftime("%Y%m%d-%H-%M-%S")
boxString = "_".join(str(x) for x in config["box"])
outDirName = f'{config["data"]}/{start}_{end}_{boxString}'
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
        print("Error! Status code is %d for this URL:\n%s" % (result.status.code, URL))
        print("Help for downloading data is at https://disc.gsfc.nasa.gov/data-access")
