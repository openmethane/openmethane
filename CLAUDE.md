# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Methane implements a 4D-Var data assimilation workflow using the CMAQ adjoint model to estimate gridded methane emissions across Australia. It ingests TropOMI satellite observations and CAMS meteorological data, runs the CMAQ adjoint forward/backward model, and produces posterior emissions estimates.

## Commands

```bash
# Install dependencies
uv sync

# Run tests locally (builds Docker image, then runs pytest inside it). Includes
# WRF for a real au-test day (about 5 minutes; 3.4 GB of FNL analyses are
# downloaded into data/fnl the first time)
make docker-test
# Inside the container, which has no uv:
pytest -r a -v
# Quicker, leaving out slow tests and those that reach third-party services:
pytest -r a -v -m "not slow and not network"

# Run a single test (must be run inside the Docker container)
pytest -v tests/unit/wrf/test_config.py::test_reads_the_production_job_environment
# Or from the host:
docker run --rm -v "$PWD":/app -v /app/.venv openmethane \
  pytest -v tests/unit/wrf/test_config.py::test_reads_the_production_job_environment

# Lint and format
uv run ruff check .
uv run ruff format .     # (or: make format)

# Regenerate regression test fixtures
make test-regen

# Draft changelog (before release)
make changelog-draft

# Build Docker image
make build
```

## Documentation

Documentation lives in `docs/`, indexed by `docs/README.md`. Task-oriented
guides are in `docs/guides/`, look-up material in `docs/reference/`. The root
`README.md` is deliberately kept to a project description plus signposting —
detail belongs in `docs/`.

When changing behaviour, check whether `docs/reference/parameters.md` (env vars),
`docs/reference/scripts.md` (script inventory) or `docs/reference/outputs.md`
(output files) need updating alongside.

## Architecture

The pipeline has four major stages that run sequentially:

### 1. WRF (`src/openmethane/wrf/`)
Produces hourly meteorology for MCIP. The `wrf` console script (`wrf run`; `uv run wrf run` from a checkout) downloads NCEP FNL analyses and the domain's published `geo_em`, runs ungrib, metgrid, real.exe and wrf.exe, averages the output and publishes it to `${STORE_PATH}/wrf/${DOMAIN_NAME}`. Unlike `fourdvar`, it reads its configuration from the environment when it starts (`WrfConfig.from_env`), never at import time, and doesn't load `.env.${TARGET}`. Domain geometry lives in `src/openmethane/wrf/domains/`. The output contract is `docs/reference/wrf-outputs.md`.

### 2. CMAQ Preprocessing (`scripts/cmaq_preprocess/`, `src/openmethane/cmaq_preprocess/`)
Prepares model inputs:
- `download_cams_input.py` — downloads CAMS CH4 boundary conditions
- `setup_for_cmaq.py` — drives MCIP/ICON/BCON csh scripts (`scripts/cmaq/run.mcip`, `run.icon`, `run.bcon`) to generate meteorological/boundary condition files
- `make_emis_template.py`, `make_template.py`, `make_prior.py` — create CMAQ emissions templates and prior flux estimate

### 3. Observation Preprocessing (`scripts/obs_preprocess/`, `src/openmethane/obs_preprocess/`)
- `fetch_tropomi.py` — finds TropOMI granules crossing the `DOMAIN_FILE` domain in the CDSE catalogue and downloads them from the public `meeo-s5p` S3 mirror (no credentials needed)
- `tropomi_methane_preprocess.py` — converts raw TropOMI into model-compatible observation files

### 4. 4D-Var Assimilation (`src/openmethane/fourdvar/`)
The core inversion. Key modules:
- `params/` — configuration loaded **at import time** from env vars + `.env.${TARGET}` file
- `datadef/` — typed data containers (PhysicalData, UnknownData, ModelInputData, etc.)
- `transfunc/` — transform functions between each data type in the chain
- `_main_driver.py` — cost function J(x) and gradient ∇J(x) using CMAQ forward+adjoint runs
- `user_driver.py` — L-BFGS-B optimization loop calling the driver
- `_transform.py` — orchestrates the full transform chain

Data flow in the transform chain:
```
PhysicalData → UnknownData → ModelInputData → ModelOutputData → ObsData
```

### Post-processing (`src/openmethane/postproc/`, `scripts/`)
Calculates posterior averages, generates alerts, and manages result archives.

## Configuration & Targets

Configuration is environment-based, loaded at import time by `fourdvar.params`. The `TARGET` environment variable (default: `docker`) controls which `.env.${TARGET}` file is loaded from the repository root.

Available targets: `docker`, `docker-test`, `docker-monthly`

NCI/Gadi is no longer supported. Its job scripts and example `.env.nci*` files live in `examples/nci/` and are provided as-is; they are not covered by tests.

For local development, set `TARGET=docker-test`. This target uses locally tracked test data under `tests/test-data/` and `data/`. Tests don't use it: `tests/conftest.py` clears configuration variables at startup and points `TARGET` at a name with no file, and tests that need configuration take the `au_test_config` fixture, which sets every variable. New tests must do the same rather than read a `.env` file.

Key env vars: `START_DATE`, `END_DATE`, `DOMAIN_NAME`, `DOMAIN_VERSION`, `STORE_PATH`, `CMAQ_BIN`, `ADJOINT_FWD`, `ADJOINT_BWD`. See `docs/reference/parameters.md` for the full list.

Sensitive credentials (EarthData, CAMS/ECMWF) go in `.env` (based on `.env.example`).

## Testing

Running the tests, markers, test data bundles and regression fixtures are in
`docs/guides/testing.md`; read it before changing tests or test data.

Tests use `pytest-regressions` for data regression testing — output files are compared against fixtures in `tests/test-data/`. When changing data-producing code, run `make test-regen` to update fixtures, then review the diffs carefully.

Many unit and integration tests require specific binaries to be present (i.e. the CMAQ adjoint binary, or tools like `ncatted`) and will fail if run locally. Excluding tests in `tests/integration/fourdvar/`, all tests should pass inside Docker, which can be run with `make docker-test`.

The `tests/integration/fourdvar/` tests rely on input data which hasn't been provided in a reproducible way. These should be fixed when possible.

Markers say what a test needs or costs: `network`, `wrf`, `cmaq`, `adjoint` and `slow`, registered in `pyproject.toml` and enforced by `--strict-markers`. Markers that follow from a fixture are added by the `FIXTURE_MARKERS` hook in `tests/conftest.py`. Plain `pytest` runs everything except `tests/integration/fourdvar/`, including the WRF test in `tests/integration/wrf/`. The WRF unit tests in `tests/unit/wrf/` use stub programs instead and run everywhere.

## Before opening a pull request

For any change that isn't mechanical (see "Code review" in
`docs/guides/development.md`), review it from a fresh context before opening
the pull request, and again after reworking it substantially. Skip this for
formatter runs, dependency bumps and experiments not for merge, or if the
operator asks you to.

Launch the `reviewer` subagent (`.claude/agents/reviewer.md`). Give it:

- the goal of the change and the diff range (e.g. `main...HEAD`)
- the numbers of any issues the change addresses
- any constraints the operator set during the task, such as an approach to use
  or avoid, or something to leave unchanged

Don't give it your reasoning or your view of whether the change is correct,
because it will tend to confirm what it's told.

Independent reviews of the same change find different problems. When a change
both alters science outputs or what production runs do, and touches error
handling, downloads, or several modules, offer the operator a second review,
run in parallel with the same brief. Each review costs tens of thousands of
tokens, so run the second only if the operator agrees. Merge the two reports,
counting a finding both raised once, before dealing with them.

Deal with each item it reports:

- **Wrong, with a clear fix:** fix it, if the fix stays within the scope of the
  task and doesn't go against the operator's instructions or the project's
  guidance.
- **Needs the operator's decision:** ask the operator, with the options and
  your recommendation. This includes items with an obvious fix that would
  change science outputs or methodology, widen the change beyond what was
  asked, or make the pull request need human review when it otherwise
  wouldn't.
- **Not a problem:** dismiss it, but list it in one line to the operator with
  your reason, because you're judging criticism of your own work.

This review is part of preparing the change. Don't mention it or its findings
in the pull request description or comments.

## Release Process

Changelog entries go in `changelog/` using towncrier conventions (named `{PR_NUMBER}.{type}.md` where type is `breaking`, `feature`, `improvement`, `fix`, `docs`, or `trivial`). A PR can have several entries, and each separate change needs its own file, because newlines in a file do not make separate bullets in the changelog. Add a counter to tell files apart, e.g. `123.feature.1.md` and `123.feature.2.md`, and use `breaking` for any change to existing behaviour. Releases are cut via the GitHub Actions `release.yaml` workflow.

Writing a changelog fragment (see `changelog/README.md`):
- Each fragment becomes one bullet in a section named for its type, so don't repeat the type in the text (no "Breaking change:" or "Fix:" prefix).
- Write for users of Open Methane, in the past tense ("Changed…", "Removed…", "Fixed…"), not about internal implementation.
- Short entries can be a single paragraph. Bullets are encouraged when an entry has several separate details, as breaking changes often do; they render as nested bullets under the entry.
- For `breaking` entries, say what the previous behaviour was, what it is now, and what a user must change. Put secondary caveats in a short final paragraph starting "Note:".
- Links must be absolute (`https://github.com/openmethane/openmethane/blob/main/docs/...`), since the changelog is also read in GitHub releases where relative paths don't resolve. towncrier appends the PR link itself.
- Run `make changelog-draft` and read the rendered output before committing.