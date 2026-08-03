# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Methane implements a 4D-Var data assimilation workflow using the CMAQ adjoint model to estimate gridded methane emissions across Australia. It ingests TropOMI satellite observations and CAMS meteorological data, runs the CMAQ adjoint forward/backward model, and produces posterior emissions estimates.

## Commands

```bash
# Install dependencies
uv sync

# Run tests locally (builds Docker image, then runs pytest inside it)
make docker-test
# To run tests without Docker (only works inside the container):
TARGET=docker-test uv run python -m pytest -r a -v tests --ignore=tests/integration/fourdvar

# Run a single test (must be run inside the Docker container)
TARGET=docker-test uv run python -m pytest -v tests/unit/cmaq_preprocess/test_wrf.py::test_name
# Or from the host:
docker run --rm -v $(PWD):/app openmethane \
  TARGET=docker-test uv run python -m pytest -v tests/unit/cmaq_preprocess/test_wrf.py::test_name

# Lint and format
uv run ruff check .
uv run ruff format .     # (or: make format)

# Regenerate regression test fixtures
make test-regen

# Draft changelog (before release)
make changelog-draft

# Build Docker image (requires access to private CMAQ-Adjoint base image)
make build
```

## Architecture

The pipeline has three major stages that run sequentially:

### 1. CMAQ Preprocessing (`scripts/cmaq_preprocess/`, `src/openmethane/cmaq_preprocess/`)
Prepares model inputs:
- `download_cams_input.py` — downloads CAMS CH4 boundary conditions
- `setup_for_cmaq.py` — drives MCIP/ICON/BCON shell scripts (`mcip.run`, `icon.run`, `bcon.run`) to generate meteorological/boundary condition files
- `make_emis_template.py`, `make_template.py`, `make_prior.py` — create CMAQ emissions templates and prior flux estimate

### 2. Observation Preprocessing (`scripts/obs_preprocess/`, `src/openmethane/obs_preprocess/`)
- `fetch_tropomi.py` — downloads TropOMI satellite data (requires EarthData credentials)
- `tropomi_methane_preprocess.py` — converts raw TropOMI into model-compatible observation files

### 3. 4D-Var Assimilation (`src/openmethane/fourdvar/`)
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

Available targets: `docker`, `docker-test`

NCI/Gadi is no longer supported. Its job scripts and example `.env.nci*` files live in `examples/nci/` and are provided as-is; they are not covered by tests.

For tests and local development, always set `TARGET=docker-test`. This target uses locally tracked test data under `tests/test-data/` and `data/`.

Key env vars: `START_DATE`, `END_DATE`, `DOMAIN_NAME`, `STORE_PATH`, `CMAQ_SOURCE_DIR`, `ADJOINT_FWD`, `ADJOINT_BWD`. See `docs/parameters.md` for the full list.

Sensitive credentials (EarthData, CAMS/ECMWF) go in `.env` (based on `.env.example`).

## Testing

Tests use `pytest-regressions` for data regression testing — output files are compared against fixtures in `tests/test-data/`. When changing data-producing code, run `make test-regen` to update fixtures, then review the diffs carefully.

Many unit and integration tests require specific binaries to be present (i.e. the CMAQ adjoint binary, or tools like `ncatted`) and will fail if run locally. Excluding tests in `tests/integration/fourdvar/`, all tests should pass inside Docker, which can be run with `make docker-test`.

The `tests/integration/fourdvar/` tests rely on input data which hasn't been provided in a reproducible way. These should be fixed when possible.

## Release Process

Changelog entries go in `changelog/` using towncrier conventions (one file per PR, named `{PR_NUMBER}.{type}.md` where type is `breaking`, `feature`, `improvement`, `fix`, `docs`, or `trivial`). Releases are cut via the GitHub Actions `release.yaml` workflow.