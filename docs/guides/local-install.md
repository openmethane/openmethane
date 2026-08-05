# Installing locally

This guide covers running Open Methane directly on a Linux machine, without
Docker.

Most people should not do this. The published Docker images bundle every
dependency, including the compiled models, and are what production uses — see
the [Quickstart](quickstart.md). Install locally when you need to profile or
debug the models, integrate with a system that cannot run containers, or run on
an HPC cluster where containers are unavailable.

> [!IMPORTANT]
> **The CMAQ adjoint binaries are the blocker.** Everything else on this page is
> installable from public sources, but the adjoint model is built from
> [CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint), which is a private
> repository, and its compiled image
> (`ghcr.io/openmethane/cmaq-adjoint`) is not publicly pullable.
>
> If you do not already have these binaries, you cannot complete a local
> install. Please open an issue or contact the team at
> inquiries@openmethane.org.

## What you need to provide

Open Methane calls out to compiled models. Under Docker these are already
present at `/opt/cmaq/bin`; locally you must supply them and point
[`CMAQ_BIN`](../reference/parameters.md) at the directory containing them:

| Binary | Used for |
| --- | --- |
| `mcip` | Converting WRF meteorology onto the CMAQ grid. |
| `ICON_CH4only` | Initial conditions. |
| `BCON_CH4only` | Boundary conditions. |
| `ADJOINT_FWD` | The CMAQ forward model. |
| `ADJOINT_BWD` | The CMAQ adjoint (backward) model. |

`ICON_CH4only` and `BCON_CH4only` must be built against the `CH4only` chemical
mechanism, and the run scripts also expect `GC_CH4only.nml` and `AE_CH4only.nml`
alongside them in `CMAQ_BIN`.

`ADJOINT_FWD` and `ADJOINT_BWD` are configured separately by absolute path, so
they may live elsewhere.

Running the full pipeline additionally needs WRF itself, from
[setup-wrf](https://github.com/openmethane/setup-wrf), and the prior, from
[openmethane-prior](https://github.com/openmethane/openmethane-prior). Each has
its own installation instructions. You can also mix approaches: run those two
stages from their public Docker images and only this repository natively.

## 1. System packages

The container installs these on top of Debian bookworm; the equivalents are
needed locally. On a Debian or Ubuntu host:

```shell
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    ca-certificates \
    csh \
    nco \
    jq \
    curl \
    tree
```

Two of these are load-bearing and easy to overlook:

- **`csh`** — the MCIP, ICON and BCON run scripts in `scripts/cmaq/` are csh
  scripts. Without it, CMAQ preprocessing fails immediately.
- **`nco`** — provides `ncatted`, `ncks` and friends, used to manipulate NetCDF
  attributes. Some tests and preprocessing steps depend on it.

The CMAQ binaries themselves will have their own runtime library requirements,
typically NetCDF, I/O API and an MPI implementation. These depend on how they
were built, so check against your build.

## 2. Python dependencies

The project targets Python 3.12 and uses
[uv](https://docs.astral.sh/uv/) to manage dependencies:

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repository root:

```shell
uv sync
```

This creates a `.venv` with the locked dependency versions. Prefix commands with
`uv run`, or activate the environment.

The repository uses a `src/` layout, so scripts under `scripts/` need the
package on the import path. `uv run` handles this because the project is
installed into the environment; if you invoke Python another way, set:

```shell
export PYTHONPATH="$(pwd)/src"
```

## 3. Configuration

Configuration is loaded at import time from a `.env.${TARGET}` file in the
repository root, chosen by the `TARGET` environment variable. The two tracked
targets both assume container paths, so a local install needs its own.

Create `.env.local` describing your machine's layout. Start from
[`.env.docker`](../../.env.docker) and replace the container paths — in
particular `CMAQ_BIN`, `ADJOINT_FWD` and `ADJOINT_BWD`:

```dotenv
MET_DIR="${STORE_PATH}/mcip"
CTM_DIR="${STORE_PATH}/cmaq"
WRF_DIR="${STORE_PATH}/wrf/${DOMAIN_NAME}"
GEO_DIR="${STORE_PATH}/wrf/${DOMAIN_NAME}"
CAMS_FILE="${STORE_PATH}/cams/cams_eac4_methane_${START_DATE}-${END_DATE}.nc"

DOMAIN_MCIP_SUFFIX="${DOMAIN_NAME}_${DOMAIN_VERSION}"

PRIOR_FILE="${STORE_PATH}/prior/outputs/prior-emissions.nc"
ICON_FILE="${CTM_DIR}/<YYYY-MM-DD>/d01/ICON.d01.${DOMAIN_MCIP_SUFFIX}.CH4only.nc"
BCON_FILE="${CTM_DIR}/<YYYY-MM-DD>/d01/BCON.d01.${DOMAIN_MCIP_SUFFIX}.CH4only.nc"

CMAQ_BIN=/path/to/your/cmaq/bin
ADJOINT_FWD=/path/to/your/cmaq/bin/ADJOINT_FWD
ADJOINT_BWD=/path/to/your/cmaq/bin/ADJOINT_BWD
```

`START_DATE`, `END_DATE`, `DOMAIN_NAME`, `DOMAIN_VERSION` and `STORE_PATH` must
be set in the surrounding environment rather than in this file, because the file
expands them. Credentials go in `.env`, as in the
[Quickstart](quickstart.md#2-credentials).

Then select it:

```shell
export TARGET=local
```

See [Configuration](../reference/configuration.md) for the full mechanism and
precedence rules.

## 4. Fetch the domain data

If using an official Open Methane domain, the domain files can be downloaded with:

```shell
make fetch-domains
```

This places the `au-test` and `aust10km` WRF geometry (`geo_em.d01.nc`) and Open
Methane domain (`domain.${DOMAIN_NAME}.nc`) files under `data/domains/`.

## 5. Verify the install

Work upwards, so a failure tells you which layer is wrong.

Check the environment loads and the paths resolve:

```shell
TARGET=local uv run python -c "
from openmethane.fourdvar.params import cmaq_config
print(cmaq_config.fwd_prog, cmaq_config.bwd_prog)
print(cmaq_config.mcip_output_path)
"
```

An exception here means a required variable is missing — the message names it.

Then run the test suite, which exercises most of the Python code without needing
the adjoint:

```shell
make fetch-test-data # fetch domains and data required for the test suite

TARGET=docker-test uv run python -m pytest -r a -v tests \
  --ignore=tests/integration/fourdvar
```

The `docker-test` target uses test data tracked in the repository. Some tests
require the external binaries (`mcip`, `ncatted`) and will fail if those are not
on your `PATH` or in `CMAQ_BIN` — see
[Development](development.md#running-the-tests).

Finally, run a single day of CMAQ preprocessing against your own target, which
is the first step that genuinely exercises the compiled models:

```shell
TARGET=local bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh
```

## Running on HPC

Open Methane previously ran on the NCI (Gadi) supercomputer. That is no longer
supported, but the PBS job scripts and example configuration are kept in
[`examples/nci`](../../examples/nci/README.md) and are the closest thing to a
worked example of a non-Docker install, including module loading and putting the
adjoint binaries in place.
