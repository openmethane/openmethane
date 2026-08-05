# Parameters

Every Open Methane setting is an environment variable. This page lists them all.
For how they are loaded — targets, `.env` files, precedence, placeholders — see
[Configuration](configuration.md).

Variables with **no default** are required: an exception is raised on import if
they are not set. Variables are grouped by what they control rather than
alphabetically; a run typically only needs to set the first two groups
explicitly.

`{CMAQ_BASE}` below refers to `${STORE_PATH}/run-cmaq`.

## Run definition

What is being modelled. These are the settings that change between runs.

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `START_DATE` | date | First day of the run | `2022-07-01` |
| `END_DATE` | date | Last day of the run, inclusive | `2022-07-30` |
| `DOMAIN_NAME` | str | The domain to model | *required* |
| `DOMAIN_VERSION` | str | Version of that domain | *required* |
| `STORE_PATH` | path | Root directory for this run's data | *required* |
| `EXPERIMENT` | str | Name of the experiment, used in archive paths | `openmethane` |
| `TARGET` | str | Which `.env.${TARGET}` file to load | `docker` |

## Domain and grid

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `DOMAIN_FILE` | path | The domain definition NetCDF file. Required by the alerts scripts and by the TROPOMI fetch, which takes the area to search from it. | *required* |
| `DOMAIN_INDEX` | int | WRF domain index, i.e. the `d0N` nest | `1` |
| `DOMAIN_MCIP_SUFFIX` | str | Suffix in generated MCIP filenames. Conventionally `${DOMAIN_NAME}_${DOMAIN_VERSION}`. | `LamCon_34S_150E` in CMAQ preprocessing, `openmethane` in `fourdvar` |
| `DOMAIN_MAP_PROJECTION` | str | Projection name recorded in generated files | `LamCon_34S_150E` |
| `BOUNDARY_TRIM` | int | Cells trimmed from each domain edge for boundary conditions. Small domains need a smaller value — see [Creating a custom domain](../guides/custom-domain.md#grid). | `5` |

> [!NOTE]
> `DOMAIN_MCIP_SUFFIX` has two different defaults depending on which code path
> reads it, so relying on the default will produce filenames that don't match
> between stages. Set it explicitly.

## Input and output paths

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `MET_DIR` | path | MCIP output directory | *required* |
| `CTM_DIR` | path | CMAQ template/output directory | *required* |
| `WRF_DIR` | path | WRF output directory, from setup-wrf | *required* |
| `GEO_DIR` | path | Directory containing the `geo_em.d??.nc` geometry file, from setup-wrf | *required* |
| `TEMPLATE_DIR` | path | CMAQ template directory | `${STORE_PATH}/templates` |
| `CHK_PATH` | path | CMAQ checkpoint files. Large and frequently rewritten — use fast scratch disk. Cleared by the container entrypoint. | `{CMAQ_BASE}/chkpnt` |
| `PRIOR_FILE` | path | The prior emissions estimate, from openmethane-prior | *required* |
| `CAMS_FILE` | path | CAMS CH4 field used for boundary conditions | *required* |
| `ICON_FILE` | path | ICON template file | *required* |
| `BCON_FILE` | path | BCON template file | *required* |
| `EMIS_FILE` | path | Emissions files | `{CMAQ_BASE}/emissions/emis.<YYYY-MM-DD>.nc` |
| `FORCE_FILE` | path | Adjoint forcing template file | `{CMAQ_BASE}/force/ADJ_FORCE.<YYYYMMDD>.nc` |
| `OBS_FILE_GLOB` | str | Glob matching the processed observation files, relative to `STORE_PATH` | `input/test_obs.pic.gz` |
| `ROOT_DIR` | path | Repository root, used to locate the bundled CMAQ run scripts | derived from the installed package location |

Several of these accept date placeholders such as `<YYYY-MM-DD>`, expanded per
simulation day — see
[Configuration](configuration.md#date-placeholders).

## Models and execution

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `CMAQ_BIN` | path | Directory containing `mcip`, `ICON_CH4only`, `BCON_CH4only` and their `.nml` files | *required* |
| `ADJOINT_FWD` | path | CMAQ forward model executable | *required* |
| `ADJOINT_BWD` | path | CMAQ adjoint (backward) model executable | *required* |
| `NUM_PROC_ROWS` | int | MPI decomposition of the grid, rows | `1` |
| `NUM_PROC_COLS` | int | MPI decomposition of the grid, columns | `1` |
| `NCPUS` | int | Parallelism for TROPOMI preprocessing and alerts | `1` |
| `USE_JOBFS` | bool | Put checkpoints on PBS job-local storage (`$PBS_JOBFS`). HPC only; warns and falls back if not run under `qsub`. | `false` |
| `EXECUTION_ID` | str | Unique identifier for this execution. Only required when `CHK_PATH` is exactly `/mnt/scratch`, where it is appended to keep concurrent runs apart. | *conditionally required* |

## Inversion

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `MAX_ITERATIONS` | int | Cap on successful L-BFGS-B iterations | `20` |
| `ALLOW_NEGATIVE_EMISSIONS` | bool | Permit the inversion to produce negative emissions. Normally left off, since negative methane emissions are unphysical for most sources. | `false` |

## CMAQ preprocessing

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `FORCE_UPDATE` | bool | Regenerate CMAQ preprocessing outputs even when they already exist | `true` |
| `CAMS_TO_CMAQ_BIAS` | float | Fixed bias correction applied when interpolating CAMS onto the CMAQ grid | `0.0` |
| `DISABLE_CORRECT_BIAS_BY_REGION` | str | Set to exactly `"true"` to compute the CAMS bias over the whole domain instead of only the region sampled by observations. Any other value, including unset, uses regional correction. | unset |
| `SKIP_CAMS_DOWNLOAD` | str | Set to any non-empty value to skip the CAMS download in `run-cmaq-preprocess.sh` | unset |
| `SKIP_CMAQ_SETUP` | str | Set to any non-empty value to skip MCIP/ICON/BCON. Used by the monthly workflow, where the daily runs already produced them. | unset |
| `SKIP_TEMPLATE_GENERATION` | str | Set to any non-empty value to skip template generation | unset |
| `SKIP_TROPOMI_DOWNLOAD` | str | Set to any non-empty value to skip the TROPOMI download in `run-all.sh` | unset |

## Observation preprocessing

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `DEFAULT_WS1` | int | Smoothing window size along the second axis, used to remove low-frequency stripes from TROPOMI retrievals. Default recommended by SRON. | `7` |
| `DEFAULT_WS2` | int | Smoothing window size along the first axis, for the same destriping. Default recommended by SRON. | `100` |
| `OPENMETHANE_MODEL_UNCERTAINTY` | float | Model-side observation uncertainty in ppb, combined in quadrature with twice the TropOMI retrieval precision to give each observation's uncertainty | `10.0` |

## Alerts

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `ALERTS_BASELINE_FILE` | path | The alerts baseline. Written by `alerts_baseline.py`, read by `create_alerts.py`. The workflow scripts set it to `${DATA_ROOT}/${ALERTS_BASELINE_NAME}` so one baseline is shared by every day of a domain. | `alerts-baseline.nc` |
| `ALERTS_BASELINE_DIRS` | str | Glob matching the daily run directories to build the baseline from | *required by `alerts_baseline.py`* |
| `ALERTS_DAILY_DIR` | path | Daily run directory to raise alerts for. Falls back to `STORE_PATH`. | `${STORE_PATH}` |
| `ALERTS_OUTPUT_FILE` | path | Where to write the alerts | `alerts.nc` |
| `ALERTS_OBS_FILE_TEMPLATE` | str | Observed-concentration file, relative to each daily directory | `input/test_obs.pic.gz` |
| `ALERTS_SIM_FILE_TEMPLATE` | str | Simulated-concentration file, relative to each daily directory | `simulobs.pic.gz` |
| `ALERTS_NEAR_THRESHOLD` | float | Near-field radius. Euclidean distance in degrees of latitude/longitude from the target cell. | `0.2` |
| `ALERTS_FAR_THRESHOLD` | float | Far-field outer radius, in the same units. The far field is the annulus between the two thresholds. | `1.0` |
| `ALERTS_THRESHOLD` | float | Enhancement, in ppb, above which a cell is flagged | `5.0` |
| `SIGNIFICANCE_THRESHOLD` | float | Statistical significance required to flag a cell | `3.0` |
| `ALERTS_COUNT_THRESHOLD` | int | Minimum observations in a cell before it can be flagged. Small test domains need this lowered. | `30` |

See [Outputs](outputs.md#alerts) for what the resulting file contains.

## Logging

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `LOG_LEVEL` | str | One of the standard Python [logging levels](https://docs.python.org/3/library/logging.html#logging-levels) | `INFO` |
| `LOG_FILE` | path | Write logs to this file in addition to stdout. Absolute, or relative to `STORE_PATH`. Existing files are rotated to `000.filename`, `001.filename`, … | unset |
| `OM_LOGGING_FILE` | path | **Deprecated.** Use `LOG_FILE`. Logs a warning if set. | unset |

See [Troubleshooting](../troubleshooting.md#logging).

## Domain upload

Used only by `scripts/cmaq_preprocess/upload-domains.py`, which publishes domain
files to the data store. Requires CloudFlare R2 credentials.

| Variable | Type | Description | Default |
| --- | --- | --- | --- |
| `GEO_DIR` | str | Local domain directory to upload from | `data/domains` |
| `EXTRA_R2_ARGS` | str | Extra arguments passed to the upload command | `""` |
| `FORCE` | bool | Overwrite existing remote files | `false` |

## Credentials

| Variable | Description |
| --- | --- |
| `CDSAPI_KEY`, `CDSAPI_URL` | Copernicus **Atmosphere** Data Store (ADS) API credentials, for downloading CAMS data. Create an account at [ads.atmosphere.copernicus.eu](https://ads.atmosphere.copernicus.eu/). Not interchangeable with Climate Data Store (CDS) credentials. |

These belong in `.env`, not in a target file — see
[Configuration](configuration.md#credentials).

## Workflow script variables

Read by the `scripts/docker-*.sh` workflow scripts on the host — mostly in the
shared `scripts/docker-common.sh` — rather than by the Python code. They are not
part of the model configuration.

| Variable | Description | Default |
| --- | --- | --- |
| `DATA_ROOT` | Host directory holding all runs, mounted into each container at `/app/data` | `/tmp/openmethane-e2e` |
| `OPENMETHANE_IMAGE` | Image used for openmethane steps | `ghcr.io/openmethane/openmethane:stable` |
| `OPENMETHANE_PRIOR_IMAGE` | Image used for the prior | `ghcr.io/openmethane/openmethane-prior:stable` |
| `SETUP_WRF_IMAGE` | Image used for WRF | `ghcr.io/openmethane/setup-wrf:stable` |
| `BUILD_LOCAL_DOCKER` | Set `true` to build the three images from local checkouts instead of pulling | `false` |
| `ALERTS_BASELINE_NAME` | Filename of the domain's shared alerts baseline, at the root of `DATA_ROOT` | `alerts-baseline.${DOMAIN_NAME}-${DOMAIN_VERSION}.nc` |
| `RUN_TYPE` | `daily` or `monthly`, set by each script | — |

The run parameters `START_DATE`, `END_DATE`, `DOMAIN_NAME`, `DOMAIN_VERSION`,
`NCPUS` and `BOUNDARY_TRIM` are also defaulted here (to a single day of
`au-test`) and written into the env file passed to each container.
