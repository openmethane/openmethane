# Troubleshooting

## Where to look first

Open Methane runs as a chain of processes, so the useful question is usually
*which stage* failed rather than what the final error said.

1. **Which step failed?** The workflow scripts echo each step before running it,
   and each container is named `e2e-{daily,monthly}-{step}` (or `alerts-baseline`
   / `create-alerts` for the alerts workflows). That tells you which script to
   investigate.
2. **Did configuration load?** Configuration is read at import time, so a missing
   required variable fails immediately with the variable's name in the message,
   before any real work. If a step failed instantly, suspect this first.
3. **Do the input files exist, at the paths the code expects?** Most stage
   failures are a previous stage's output not being where this stage looks. Print
   the resolved configuration — see
   [Configuration](reference/configuration.md#inspecting-the-resolved-configuration).
4. **Then read the logs.** Raise the verbosity with `LOG_LEVEL=DEBUG`.

## Common problems

### A required environment variable is missing

An exception naming the variable, raised on import. Either it is genuinely unset,
or `.env.${TARGET}` was not found — it must be in the **repository root**, and
scripts must be run from there.

Note that variables used in expansions inside a `.env.${TARGET}` file
(`START_DATE`, `STORE_PATH`, `DOMAIN_NAME`, …) must be set outside that file. See
[Configuration](reference/configuration.md#variable-expansion).

### Credentials rejected

Only CAMS needs credentials. Check that `CDSAPI_KEY` holds **Atmosphere** Data Store (ADS)
credentials, not Climate Data Store (CDS). The two services share a login and a
credentials format, and each dataset has terms that must be accepted separately
from its download page.

TROPOMI needs no credentials: the CDSE catalogue is searched anonymously and the
S3 requests are unsigned, so any AWS credentials in the environment are ignored.

### The TROPOMI fetch finds no granules

`fetch_tropomi.py` fails rather than leaving the next step nothing to read.
Usually the date is outside the archive: products are catalogued from
**2018-04-30** and lag acquisition by two to three days. Otherwise, check that
`DOMAIN_FILE` points at the domain you meant — the search area comes from it.
See [TROPOMI data](reference/tropomi.md).

### Paths inside a container resolve to nothing

Configuration passed into a container must use **container** paths. A host path
that happens to exist will not fail loudly; it will just resolve somewhere empty.
The workflow scripts distinguish `DATA_ROOT` (host) from `STORE_PATH`
(container, under `/app/data`).

### CMAQ preprocessing fails in MCIP, ICON or BCON

These are csh scripts in `scripts/cmaq/`, so:

- Confirm `csh` is installed. Without it they fail immediately. It is in the
  container; on a local install see
  [Installing locally](guides/local-install.md#1-system-packages).
- Confirm `CMAQ_BIN` contains `mcip`, `ICON_CH4only`, `BCON_CH4only` and the
  matching `GC_CH4only.nml` and `AE_CH4only.nml`.
- Read the generated script and its log in the run directory. The error is
  usually in there and more specific than what surfaces in Python.

### The domain has no cells, or grid dimensions are wrong

MCIP trims cells from every edge for boundary conditions, per `BOUNDARY_TRIM`.
The default of `5` removes 13 cells in each dimension, which on a small domain
removes everything. `au-test` uses `BOUNDARY_TRIM=1`. See
[Creating a custom domain](guides/custom-domain.md#grid).

### "File not found" for a file a previous stage should have written

Check `DOMAIN_MCIP_SUFFIX`. It appears in generated filenames and has **different
defaults in different code paths** (`LamCon_34S_150E` in CMAQ preprocessing,
`openmethane` in `fourdvar`), so relying on the default produces names one stage
writes and another does not look for. Set it explicitly, conventionally to
`${DOMAIN_NAME}_${DOMAIN_VERSION}`.

### Alerts are all NaN

`ALERTS_COUNT_THRESHOLD` (default 30) is the minimum number of observations a
cell needs before it can be assessed. On small domains or short periods no cell
reaches it, so every cell is `NaN`. `scripts/docker-create-alerts.sh` lowers it
to `2`, which is enough for `au-test` to produce something but not enough to
mean anything.

### Creating alerts exits immediately

`scripts/docker-create-alerts.sh` checks its inputs before starting a container
and names the command to run for whichever is missing: a daily run for
`START_DATE`, or the domain's alerts baseline at
`${DATA_ROOT}/alerts-baseline.${DOMAIN_NAME}-${DOMAIN_VERSION}.nc`. The baseline
is built by `scripts/docker-alerts-baseline.sh` from completed daily runs, so on
a new domain run the daily workflow for a period first. See
[Quickstart](guides/quickstart.md#5-create-alerts-optional).

### The alerts baseline is built from fewer days than expected

`scripts/docker-alerts-baseline.sh` warns for each day in the range with no
daily run and continues without it, reporting how many it found. If none exist
it exits. Check `${DATA_ROOT}/daily/${DOMAIN_NAME}/${DOMAIN_VERSION}/` for the
days you expected.

### The inversion runs but the posterior barely differs from the prior

Usually correct behaviour rather than a fault, and worth distinguishing between
two causes:

- **No observations.** Cells the satellite never saw are unconstrained and stay
  at the prior. Check coverage for the period before concluding anything.
- **The optimiser stopped early.** Check whether it hit `MAX_ITERATIONS`
  (default 20) rather than converging. The cost, bias and chi-squared for each
  iteration are logged.

### Disk fills up during a run

`CHK_PATH` holds CMAQ checkpoint files, which are large and rewritten on every
iteration. Point it at fast disk with room to spare. The container entrypoint
clears it when a command finishes, including on failure — so if you need to
inspect checkpoints after a crash, set `CHK_PATH` somewhere the entrypoint will
not clean, or run the step without the entrypoint.

## Logging

Open Methane packages should use the `get_logger` method in the `util/logger.py`
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

`OM_LOGGING_FILE` is a deprecated alias for `LOG_FILE` and logs a warning if set.

## Debugging the inversion

`scripts/fourdvar/singlestep.py` runs one full pass — forward simulation,
residual, adjoint — without optimising. It is the fastest way to find where a
change to the transform chain breaks, since a full run repeats the same chain
twenty times.

For changes to `fourdvar/transfunc/`, note that a wrong adjoint produces a
plausible-looking but incorrect answer rather than an error. Only gradient
verification catches it — see
[Architecture](reference/architecture.md#verifying-a-change).

## Integration tests

There are a few integration tests that can be run to check that `fourdvar` is working as expected.
These tests are in `tests/integration/fourdvar`.
These tests are run during the end to end test suite for the test domain and require the CMAQ preprocessing step to be run prior.

These tests can also be run directly using python within a docker container if you have the required data.
Be sure to set the correct values for the  `STORE_PATH` and `TARGET` environment variables before running the tests.

> [!NOTE]
> These tests depend on input data that has not been provided in a reproducible
> way, so they are excluded from the default test run and may not work without
> additional setup. They should be fixed when possible.

## Fetching results from S3

For local testing it is useful to fetch the results from a previous run to use as a starting point.

The following command will fetch the results from the S3 bucket `BUCKET_NAME` for the `aust-nsw` region for the month of July 2022.

```bash
aws-vault exec openmethane-sandbox-admin -- aws s3 sync s3://{BUCKET_NAME}/aust-nsw/monthly/2022/07 data/aust-nsw/monthly/2022/07 --exclude 'prior/intermediates/*' --exclude 'cams/*'
```

The CAMS and prior intermediate data are used in the preprocessing step, but aren't needed if you just want to run the model.

## Reproducing a specific version

To rule out your changes as the cause, run against a published image. Every
release and every pull request has one:

```shell
OPENMETHANE_IMAGE=ghcr.io/openmethane/openmethane:1.2.0 \
  bash scripts/docker-e2e-daily.sh
```

See [the package list](https://github.com/orgs/openmethane/packages) for
available tags.

## Getting help

If you are stuck, open an issue on
[GitHub](https://github.com/openmethane/openmethane/issues) or contact the team
at inquiries@openmethane.org. Include the failing step, the relevant log output,
and the resolved configuration for the run.
