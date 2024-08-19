## Fetching results from S3

For local testing it is useful to fetch the results from a previous run to use as a starting point.

The following command will fetch the results from the S3 bucket `BUCKET_NAME` for the `aust-nsw` region for the month of July 2022.

```bash
aws-vault exec openmethane-sandbox-admin -- aws s3 sync s3://{BUCKET_NAME}/aust-nsw/monthly/2022/07 data/aust-nsw/monthly/2022/07 --exclude 'prior/intermediates/*' --exclude 'cams/*'
```

The CAMs and prior intermediate data are used in during the preprocessing step, but aren't needed if you are just wanting to run the model.


## Integration tests

There are a few integration tests that can be run to check that `fourdvar` is working as expected. 
These tests are in `tests/integration/fourdvar`.
These tests are run during the end to end test suite for the test domain and require the CMAQ preprocessing step to be run prior.

These tests can also be run directly using python within a docker container if you have the required data. 
Be sure to set the correct values for the  `STORE_PATH` and `TARGET` environment variables before running the tests.
