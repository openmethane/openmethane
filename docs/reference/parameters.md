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
| `NUM_PROC_TOTAL` | int | Number of MPI ranks to decompose the grid across. The shape of the decomposition is derived from the domain size — see [MPI domain decomposition](#mpi-domain-decomposition). | `1` |
| `NUM_PROC_ROWS` | int | MPI decomposition of the grid, rows. Pins the decomposition instead of deriving it. | derived |
| `NUM_PROC_COLS` | int | MPI decomposition of the grid, columns. Pins the decomposition instead of deriving it. | derived |
| `MIN_CELLS_PER_RANK` | int | Fewest grid cells a subdomain may span in either direction | `10` |
| `MPI_EXTRA_ARGS` | str | Extra arguments passed to `mpirun`, ahead of the CMAQ executable. Used to bind ranks to cores — see [Rank binding](performance.md#rank-binding). Ignored for a serial run. | unset |
| `NCPUS` | int | Parallelism for TROPOMI preprocessing and alerts | `1` |
| `USE_JOBFS` | bool | Put checkpoints on PBS job-local storage (`$PBS_JOBFS`). HPC only; warns and falls back if not run under `qsub`. | `false` |
| `EXECUTION_ID` | str | Unique identifier for this execution. Only required when `CHK_PATH` is exactly `/mnt/scratch`, where it is appended to keep concurrent runs apart. | *conditionally required* |
| `WRITE_VADV_TOPFLX` | bool | Write the gridded model-top advective flux from each forward run, to `{CMAQ_BASE}/output/VADV_TOPFLX.<YYYYMMDD>.nc`. See [Model-top advective flux](#model-top-advective-flux). | `false` |

### Model-top advective flux

CMAQ gives methane no top boundary condition, and vertical advection sets the
velocity at the model top from the column air-mass budget residual rather than
to zero, so methane crosses the lid in both directions. `ADJOINT_FWD` measures
that, upward and downward separately, for methane and for air.

The domain integral at every interface goes to the CMAQ log every
synchronisation step and cannot be turned off. `WRITE_VADV_TOPFLX` additionally
writes a gridded file of the model-top interface at each output step, which is
what says *where* the flux happens — useful because the boundary conditions are
injected on the perimeter.

`docs/vadv-top-flux.md` in
[openmethane/CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint) covers
the units, the log line format and the mass conversion.

#### What is kept, and where

Everything is filed under `{CMAQ_BASE}/output/vadv-topflx/<pass>/`, one
directory per forward pass, numbered from `0001`:

| File | Holds |
| --- | --- |
| `VADV_TOPFLX.<YYYYMMDD>.nc` | the gridded model-top flux, per output step |
| `vadv_flux.<forward log name>` | the `VADVTOP` and `VADVFLX` records taken out of that day's CMAQ log |

Both halves are needed. The gridded file covers the model top alone; the
domain-integrated flux at *every* layer interface, which is what closes the
vertical mass budget, exists only in the log.

Neither can be left where the model writes it. `wipeout_fwd` clears the forward
output before each pass and again as the driver exits, and `_cleanup` replaces
the date tag with a wildcard, so a whole month would go at once — the CMAQ
forward log is the first entry in that list. Collecting the diagnostic is a copy
off the run directory after the job has finished, so it has to survive both.

An inversion runs a forward pass per line search evaluation, and each pass is
kept. The flux under a trial control vector says as much about what the
optimiser is doing as the flux under whichever vector the search happened to try
last — the upper-level `bcon` elements of the control vector act directly on the
top layer that sets this flux.

#### Cost

Per forward pass, for a month on `aust10km` (454 x 430 cells, hourly output):

| | Size |
| --- | --- |
| gridded file | 2.3 GB |
| log records | 8.5 MB |

A forward-only month is one pass. A full inversion is one pass per line search
evaluation, so tens of them — budget accordingly, or run forward-only, which is
what the diagnostic is mainly for.

### MPI domain decomposition

CMAQ splits the domain into a grid of `NUM_PROC_COLS` x `NUM_PROC_ROWS`
subdomains and runs one MPI rank per subdomain.

Normally only `NUM_PROC_TOTAL` needs to be set, to the number of cores the run
has available. The shape is then derived from the size of the domain, keeping
subdomains as square as possible and no smaller than `MIN_CELLS_PER_RANK` cells
in either direction. Fewer ranks than requested are used if the domain is too
small to be split that finely, down to a single rank for a domain that is
smaller than the minimum. This means the same `NUM_PROC_TOTAL` can be used for
every domain.

Setting `NUM_PROC_COLS` or `NUM_PROC_ROWS` pins the decomposition instead, and
`NUM_PROC_TOTAL` is then ignored. If neither is set, CMAQ runs in serial.

[Performance and hardware](performance.md) covers how to choose
`NUM_PROC_TOTAL` for a machine and how to measure whether it is the right
value.

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
| `OM_METRICS` | bool | Log a `[om-metrics]` resource usage line when a container starts and finishes. Temporary, see [Measuring a run](performance.md#measuring-a-run). Set to `0` to turn off. | `1` |
| `OM_METRICS_INTERVAL` | int | Seconds between memory samples taken for those lines | `30` |

See [Troubleshooting](../troubleshooting.md#logging).

## Credentials

| Variable | Description |
| --- | --- |
| `CDSAPI_KEY`, `CDSAPI_URL` | Copernicus **Atmosphere** Data Store (ADS) API credentials, for downloading CAMS data. Create an account at [ads.atmosphere.copernicus.eu](https://ads.atmosphere.copernicus.eu/). Not interchangeable with Climate Data Store (CDS) credentials. |
| `CDSE_USERNAME`, `CDSE_PASSWORD` | Copernicus Data Space Ecosystem account, used by `fetch_tropomi.py` only to download a granule directly from CDSE when the copy in the MEEO mirror is unusable. Optional: neither the catalogue search nor the mirror download needs credentials. Create a free account at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/). |

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
