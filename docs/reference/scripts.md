# Scripts

Every stage of Open Methane is a script that reads its configuration from the
environment. This page is the inventory: what each script does, what it needs
first, and what it leaves behind.

Most scripts assume they are run **from the repository root**, since some
configuration is resolved relative to it. All of them require the environment to
be configured — see [Configuration](configuration.md).

## Workflow orchestration

Run whole workflows. These are the entry points for most users.

| Script | Description |
| --- | --- |
| `scripts/docker-e2e-daily.sh` | Runs the complete [daily workflow](../overview.md#daily-workflow) as a sequence of containers. Pulls published images by default. |
| `scripts/docker-e2e-monthly.sh` | Runs the complete [monthly workflow](../overview.md#monthly-workflow), including the inversion. |
| `scripts/docker-alerts-baseline.sh` | Builds the [alerts baseline](../overview.md#alerts-workflows) for a domain from the daily runs between `START_DATE` and `END_DATE`. |
| `scripts/docker-create-alerts.sh` | Creates alerts for the single day `START_DATE`, from that day's daily run and the domain's baseline. |
| `scripts/docker-build-all.sh` | Builds `setup-wrf`, `openmethane-prior` and `openmethane` images from local checkouts. Invoked by the above when `BUILD_LOCAL_DOCKER=true`. |
| `scripts/run-all.sh` | Runs CMAQ preprocessing, TROPOMI fetch and preprocessing, bias correction and the inversion in one process, inside a single container. Simpler than the e2e scripts but assumes WRF output and the prior already exist. |

All four `docker-*` workflow scripts source `scripts/docker-common.sh`, which
holds the settings and helpers they share: image names, `DATA_ROOT`, the run
parameters (`START_DATE`, `DOMAIN_NAME`, …), loading `.env`, downloading the
domain file, and writing the per-run env file passed to each container. Every
variable in it is set with `:-`, so anything already in the environment wins.
It is sourced, not run directly.

`scripts/environment.sh` is sourced by the shell scripts to load
`.env.${TARGET}` without clobbering existing environment variables. It is not run
directly.

`scripts/docker-entrypoint.sh` is the container entrypoint. It runs the given
command and clears `CHK_PATH` afterwards, including on failure.

## CMAQ preprocessing

Turns WRF meteorology and the prior into inputs CMAQ can read. See
[CMAQ preprocessing](cmaq-preprocess.md) for detail.

| Script | Description |
| --- | --- |
| `scripts/cmaq_preprocess/run-cmaq-preprocess.sh` | Runs the whole stage in order. Honours `SKIP_CAMS_DOWNLOAD`, `SKIP_CMAQ_SETUP` and `SKIP_TEMPLATE_GENERATION`. |
| `scripts/cmaq_preprocess/download_cams_input.py` | Downloads CAMS methane on pressure levels for the date range. Needs ADS credentials. Takes `-s`/`-e` and an output path. |
| `scripts/cmaq_preprocess/setup_for_cmaq.py` | Runs MCIP, ICON and BCON, and interpolates CAMS onto the CMAQ grid. Requires WRF output and the CAMS file. |
| `scripts/cmaq_preprocess/make_emis_template.py` | Builds the CMAQ emissions template from the prior. |
| `scripts/cmaq_preprocess/make_template.py` | Prepares CMAQ run directories and the concentration, forcing and sensitivity templates, by running one day of CMAQ forwards and backwards. Requires the adjoint binaries. |
| `scripts/cmaq_preprocess/make_prior.py` | Builds the prior in the form `fourdvar` consumes. |
| `scripts/cmaq_preprocess/bias_correct_cams.py` | Corrects bias between CAMS boundary conditions and CMAQ. Honours `DISABLE_CORRECT_BIAS_BY_REGION`. |
| `scripts/cmaq_preprocess/upload-domains.py` | Publishes domain files to the data store. Maintainers only; needs CloudFlare R2 credentials. |

The last three template steps can be run together:

```shell
make prepare-templates
```

`scripts/cmaq/run.mcip`, `run.icon` and `run.bcon` are the csh run scripts that
`setup_for_cmaq.py` invokes. They are not run by hand, but are where to look when
MCIP, ICON or BCON fail — the arguments passed to them come from
`src/openmethane/cmaq_preprocess/run_scripts.py`.

## Observation preprocessing

| Script | Description |
| --- | --- |
| `scripts/obs_preprocess/fetch_tropomi.py` | Finds TROPOMI methane granules crossing the domain in the CDSE catalogue and downloads them whole from the public `meeo-s5p` S3 mirror. Takes `-s`/`-e` datetimes and an output directory; the area comes from `DOMAIN_FILE`. Needs no credentials. |
| `scripts/obs_preprocess/fetch_tropomi.sh` | Wrapper used by the daily workflow. Fetches into `data/tropomi/${START_DATE}`. |
| `scripts/obs_preprocess/tropomi_methane_preprocess.py` | Converts raw granules into the observation format `fourdvar` reads, dropping observations outside the model grid. Takes `--source` as a glob. |
| `scripts/obs_preprocess/process_tropomi.sh` | Wrapper used by the daily workflow. |

Granules already present in the output directory are skipped, so rerunning a
failed fetch only downloads what is missing. See
[TROPOMI data](tropomi.md) for which products are served and how far back they
go.

## Inversion

| Script | Description |
| --- | --- |
| `runscript.py` | **The inversion.** Runs the L-BFGS-B optimisation to convergence or `MAX_ITERATIONS`. This is the monthly workflow's main step. |
| `scripts/fourdvar/run_daily_step.py` | One forward simulation from the prior, producing simulated observations. The daily workflow's main step; performs no optimisation. |
| `scripts/fourdvar/singlestep.py` | A single forward and adjoint step. Useful for debugging the transform chain without a full optimisation. |
| `scripts/fourdvar/archive_cmaq_input.py` | Archives the CMAQ input files for a run. |
| `restart_script.py` | Resumes an inversion from a previous run's state. |

## Alerts

| Script | Description |
| --- | --- |
| `scripts/alerts/alerts_baseline.py` | Builds the alert baseline from a set of completed daily runs, matched by the `ALERTS_BASELINE_DIRS` glob. Run by `docker-alerts-baseline.sh`. |
| `scripts/alerts/create_alerts.py` | Raises alerts for one day by comparing it against the baseline. Run by `docker-create-alerts.sh`. |

Both read the outputs of daily runs rather than of the inversion, and the
baseline must exist before alerts can be created. The two `docker-*` wrappers
above check their inputs up front and name the command to run if something is
missing.

## Post-processing

| Script | Description |
| --- | --- |
| `scripts/manual_postproc.py` | Converts posterior multipliers into posterior emissions by hand, for a run whose post-processing did not complete. Takes `-f` for the multipliers file. |

## Unmaintained scripts

`extra_scripts/` holds one-off and exploratory scripts kept for reference. They
are not part of any workflow, are not covered by tests, and may not work against
the current code:

- `cost_function.py`, `make_icon_bcon_template.py`, `plot_obs_coverage.py`,
  `reset_dates.py`

`examples/nci/` holds the PBS job scripts from when Open Methane ran on NCI
(Gadi). NCI is no longer supported — see
[`examples/nci/README.md`](../../examples/nci/README.md).

## Make targets

`make` wraps the most common invocations. `make help` is not defined, so the
[`Makefile`](../../Makefile) itself is the list; the useful ones are:

| Target | Description |
| --- | --- |
| `install` | `uv sync` |
| `build` | Build the `openmethane` Docker image. Needs the private base image. |
| `start` | Build and drop into a shell in the container. |
| `run` | Run the full pipeline on the test domain in the container. |
| `test` | Run the test suite. Requires the container. |
| `docker-test` | Build the image, then run the tests inside it. |
| `test-regen` | Regenerate regression fixtures. |
| `prepare-templates` | Run the three template generation scripts. |
| `fetch-domains` | Download the WRF geometry and Open Methane domain files for `aust10km` and `au-test` into `data/`. |
| `fetch-test-data` | Download the `au-test` geometry and domain files, plus the CAMS file the tests need. Run by `docker-test`. |
| `sync-domains-from-cf` | Sync all domain data from CloudFlare. Needs credentials. |
| `changelog-draft` | Preview the next release's changelog. |
| `format` | Format with ruff. |
| `clean` | Delete generated files under `data/`, preserving `data/tropomi`. |
