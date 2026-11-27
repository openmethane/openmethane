# Installing locally

This guide covers running Open Methane directly on a Linux machine, without
Docker.

Most people should not do this. The published Docker images bundle every
dependency, including the compiled models, and are what production uses — see
the [Quickstart](quickstart.md). Install locally when you need to profile or
debug the models, integrate with a system that cannot run containers, or run on
an HPC cluster where containers are unavailable.

> [!IMPORTANT]
> **The CMAQ binaries are the hard part.** Everything else on this page installs
> from packages or from source in the usual way, but the models are compiled
> Fortran, and particular about their compilers and NetCDF build.
>
> Take them from the Debian packages attached to the
> [CMAQ](https://github.com/openmethane/CMAQ/releases) and
> [CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint/releases) releases,
> which are what the Docker image uses — see
> [Taking the binaries from the release packages](#taking-the-binaries-from-the-release-packages).

## What you need to provide

Open Methane calls out to compiled models. Under Docker these are already
present at `/opt/cmaq/bin`; locally you must supply them and point
[`CMAQ_BIN`](../reference/parameters.md) at the directory containing them:

| Path under `CMAQ_BIN` | Used for |
| --- | --- |
| `mcip.exe` | Converting WRF meteorology onto the CMAQ grid. |
| `ICON_CH4only/ICON_CH4only` | Initial conditions. |
| `BCON_CH4only/BCON_CH4only` | Boundary conditions. |
| `ADJOINT_FWD` | The CMAQ forward model. |
| `ADJOINT_BWD` | The CMAQ adjoint (backward) model. |

ICON and BCON must be built against the `CH4only` chemical mechanism, and are
each expected in a build directory named after the mechanism rather than as a
bare executable. `run.icon` and `run.bcon` read `GC_CH4only.nml`,
`AE_CH4only.nml`, `NR_CH4only.nml` and `Species_Table_TR_0.nml` from that same
directory, which is where the build leaves them.

`ADJOINT_FWD` and `ADJOINT_BWD` are configured separately by absolute path, so
they may live elsewhere.

### Taking the binaries from the release packages

The models are published as Debian 13 (trixie) packages attached to each GitHub
release: `openmethane-cmaq` from [CMAQ](https://github.com/openmethane/CMAQ/releases),
`openmethane-cmaq-adjoint` from
[CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint/releases) and
`openmethane-wrf` from [build-wrf](https://github.com/openmethane/build-wrf/releases). Use the
versions the [`Dockerfile`](../../Dockerfile) pins. You don't need to install
them: `dpkg-deb -x` unpacks a package into a folder, on any Linux system with
`dpkg-deb`, and without it `ar x <deb>` followed by `tar -xf data.tar.*` does the
same.

```shell
dpkg-deb -x openmethane-cmaq_<version>_amd64.deb ./cmaq-root
dpkg-deb -x openmethane-cmaq-adjoint_<version>_amd64.deb ./cmaq-root
```

The two CMAQ packages put their files under `opt/cmaq/bin`, so `CMAQ_BIN` is
`./cmaq-root/opt/cmaq/bin`, and `ADJOINT_FWD` and `ADJOINT_BWD` are the two
executables inside it. `openmethane-wrf` puts WRF under `opt/wrf` and WPS under
`opt/wps`, which are the folders `WRF_INSTALL_DIR` and `WPS_INSTALL_DIR` name.

The binaries are dynamically linked, so this only works on a host with
compatible libraries, which is any Debian 13 system or similar. List what they
need with:

```shell
dpkg-deb -f openmethane-cmaq-adjoint_<version>_amd64.deb Depends
```

and check with `ldd` that nothing is "not found". On a host with a different C
library or NetCDF, build from source instead.

### Building from source

Building the models from source is documented, but not supported: neither
repository supports native builds. The build documents are
[CMAQ's `docs/building.md`](https://github.com/openmethane/CMAQ/blob/main/docs/building.md)
and
[CMAQ-Adjoint's `docs/building.md`](https://github.com/openmethane/CMAQ-Adjoint/blob/main/docs/building.md).
Build the versions the `Dockerfile` pins.

Running the full pipeline additionally needs the prior, from
[openmethane-prior](https://github.com/openmethane/openmethane-prior), which has
its own installation instructions. The `wrf` command needs WRF and WPS, from
the package above or built from
[build-wrf's `docs/building.md`](https://github.com/openmethane/build-wrf/blob/main/docs/building.md).
Point [`WRF_INSTALL_DIR` and `WPS_INSTALL_DIR`](../reference/parameters.md#wrf)
at their install folders. The `wrf` command reads its settings from the environment only, not from the `.env.${TARGET}` file
described below. You can also mix
approaches: run WRF and the prior from their public Docker images and only the
rest of this repository natively.

## 1. System packages

The container installs these on top of Debian trixie; the equivalents are
needed locally. On a Debian or Ubuntu host:

```shell
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    csh \
    make \
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

The CMAQ, WRF and WPS binaries need NetCDF-Fortran and an MPI implementation
(`mpich`). If you took them from the release packages, `dpkg-deb -f <deb> Depends` lists exactly
what they need. If you built them yourself, these depend on how they were built,
so check against your build.

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
Methane domain (`domain.${DOMAIN_NAME}.nc`) files under `data/domains/`, from the
public data store. The `wrf` command downloads the `geo_em.d01.nc` it needs
itself.

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

uv run python -m pytest -r a -v -m "not wrf and not cmaq and not adjoint"
```

The tests set their own configuration and read test data tracked in the
repository, whatever your target. The `-m`
expression leaves out the tests that run WRF and the CMAQ programs. Some other
tests need tools like `ncatted`, and will fail if those are not on your `PATH`
— see
[Testing](testing.md#running-the-tests).

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
