## Fetching results from S3

For local testing it is useful to fetch the results from a previous run to use as a starting point.

The following command will fetch the results from the S3 bucket `BUCKET_NAME` for the `aust-nsw` region for the month of July 2022.

```bash
aws-vault exec openmethane-sandbox-admin -- aws s3 sync s3://{BUCKET_NAME}/aust-nsw/monthly/2022/07 data/aust-nsw/monthly/2022/07 --exclude 'prior/intermediates/*' --exclude 'cams/*'
```

The CAMS and prior intermediate data are used in the preprocessing step, but aren't needed if you just want to run the model.


## Integration tests

There are a few integration tests that can be run to check that `fourdvar` is working as expected. 
These tests are in `tests/integration/fourdvar`.
These tests are run during the end to end test suite for the test domain and require the CMAQ preprocessing step to be run prior.

These tests can also be run directly using python within a docker container if you have the required data. 
Be sure to set the correct values for the  `STORE_PATH` and `TARGET` environment variables before running the tests.

## Logging

Open Methane packages should use the`get_logger` method in the `util/logger.py`
package for logging. This is a wrapper around the standard `logging` library
with automatic parsing of the `LOG_LEVEL` and `LOG_FILE` environment variables.

### `LOG_LEVEL`

Specify the desired log level from one of the standard python
[logging levels](https://docs.python.org/3/library/logging.html#logging-levels).

This will cause all modules which use `util.logger` to log at the requested
level, including the python base logger.

### `LOG_FILE`

Specify a file path to send logs to a file in addition to stdout. Can be used
in conjunction with `LOG_LEVEL` to write only a desired level of logging to file.

Accepts an absolute path, or a path relative to `STORE_PATH`.

If there is an existing file at the same path as specified by `LOG_FILE`, the
existing file will be moved, following a pattern like:
- `path/000.filename`
- `path/001.filename`
- etc
