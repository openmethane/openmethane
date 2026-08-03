# Running Open Methane on NCI (Gadi)

> [!WARNING]
> **NCI/Gadi is no longer officially supported.**
>
> Everything in this directory is provided **as-is** and may no longer work.
> These scripts and instructions are kept for reference for anyone wanting to
> run Open Methane on an HPC system, but they are not tested by CI and are not
> maintained alongside the rest of the project.
>
> The supported ways to run Open Methane are locally or via Docker.
> See the [main README](../../README.md).

This directory contains the PBS job scripts and example configuration that were
previously used to run Open Methane on the
[NCI](https://nci.org.au/) Gadi supercomputer.

## How NCI differs from Docker

The main structural difference is dependency management. With Docker, every
dependency — Python packages, CMAQ, the adjoint model — is bundled into the
container image. On NCI, you are responsible for providing all of them:

- System libraries come from Gadi's `module` system.
- Python dependencies are managed with [uv](https://docs.astral.sh/uv/).
- The CMAQ adjoint binaries must be built separately and their location
  supplied via configuration.

The remaining differences are configuration (mostly filesystem paths), which is
handled through the `TARGET` mechanism described below.

## Setup

### 1. Clone the repository

```shell
git clone git@github.com:openmethane/openmethane.git
cd openmethane
```

Some configuration refers to the location the code was cloned to, so run all
subsequent commands from the repository root.

### 2. Install uv

This project uses [uv](https://docs.astral.sh/uv/) to manage Python
dependencies. It is not available as a Gadi module, so install it into your home
directory using the
[standalone installer](https://docs.astral.sh/uv/getting-started/installation/):

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This installs `uv` to `~/.local/bin`. Make sure that directory is on your
`PATH` — add it to your `~/.bashrc` if the installer has not already:

```shell
export PATH="$HOME/.local/bin:$PATH"
```

Verify it is available:

```shell
uv --version
```

### 3. Load the environment

`load_p4d_modules.sh` loads the Gadi modules used to build CMAQ, checks that
`uv` is available, syncs the Python dependencies, and puts the resulting virtual
environment on your `PATH`.

It is sourced automatically by each of the job scripts here, but you can also
source it manually for interactive work. Run it from the repository root:

```shell
. examples/nci/load_p4d_modules.sh
```

### 4. Configure the target

Configuration is loaded at import time from a `.env.${TARGET}` file in the
repository root, selected by the `TARGET` environment variable.

The example NCI configurations in this directory must be **copied to the
repository root** to be picked up:

```shell
cp examples/nci/.env.nci .
```

| File | Domain | Notes |
| --- | --- | --- |
| `.env.nci` | `aust10km` | Full Australia domain |
| `.env.nci-nsw` | `aust-nsw` | Small NSW test domain |
| `.env.nci-test` | `au-test` | Uses the test data tracked in the repository |

Each file expects `CMAQ_BIN` to point at the directory containing your
CMAQ-Adjoint builds (defaulting to `~/cmaq_adjoint`), which must contain
`ADJOINT_FWD` and `ADJOINT_BWD`. Review the paths in the file you copy and
adjust them for your project and scratch space.

You will also need a `.env` file in the repository root, based on
[`.env.example`](../../.env.example), containing your EarthData and CAMS
credentials.

The PBS directives in these job scripts request the `q90` project. Change the
`#PBS -P` line in each script to your own project code.

See [`docs/parameters.md`](../../docs/parameters.md) for the full list of
configurable parameters.

### 5. Fetch the domain files

The WRF geometry files are required to run the pipeline. Create your own
or fetch provided domains with:

```shell
make fetch-domains
```

This downloads the `au-test` and `aust10km` domains from
[setup-wrf](https://github.com/openmethane/setup-wrf) into `data/domains`.

## Running

All job scripts are submitted from the repository root and rely on `#PBS -l wd`
to keep the repository root as the working directory.

### Full pipeline

`submit-run-all.sh` runs the complete pipeline — CMAQ preprocessing, TROPOMI
download and preprocessing, and the 4D-Var inversion — against the small NSW
test domain (`TARGET=nci-nsw`, roughly a 10x10 grid over a mine in NSW).

```shell
qsub examples/nci/submit-run-all.sh
```

### 4D-Var only

`submit.sh` runs just the inversion (`runscript.py`), assuming the preprocessing
outputs already exist.

```shell
qsub examples/nci/submit.sh
```

### Observation preprocessing

These steps are included in the full pipeline, but can be submitted separately:

```shell
# Download raw TROPOMI data
qsub examples/nci/obs_preprocess/submit_fetch.sh

# Convert raw TROPOMI data into model-compatible observation files
qsub examples/nci/obs_preprocess/submit_tropomi_methane_preprocess.sh
```

`submit_fetch.sh` has a hard-coded config file and date range — edit these
before submitting. `submit_tropomi_methane_preprocess.sh` reads its input glob
from `TROPOMI_SOURCE`, defaulting to `${STORE_PATH}/tropomi/*/*.nc4`.

### Gradient verification

The `tests/integration/fourdvar/` gradient checks can be run as PBS jobs:

```shell
qsub examples/nci/submit_test_grad_finite_diff.sh
qsub examples/nci/submit_test_grad_step.sh
```

> [!NOTE]
> These integration tests depend on input data that has not been provided in a
> reproducible way, so they may not run without additional setup.

## Known issues

These scripts were last exercised against an older version of the project, and
carry some known rough edges:

- The PBS resource requests (walltime, memory, CPU counts, jobfs) were tuned for
  particular domains and may not suit your run.
- `submit_fetch.sh` previously used the `conda/analysis3` module from
  `/g/data3/hh5`; it now uses the project's own dependencies via `uv`, which has
  not been verified on Gadi.
- The example configurations reference scratch and home paths that will need to
  be updated for your NCI project.
