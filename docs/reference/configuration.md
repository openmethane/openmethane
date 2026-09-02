# Configuration

All Open Methane configuration is environment variables. There is no
configuration file format of its own; the `.env` files are just convenient ways
to set environment variables.

For the meaning of each individual variable, see
[Parameters](parameters.md). This page explains how they are loaded.

## Loaded at import time

Configuration is read when `openmethane.fourdvar.params` is first imported, by
`openmethane.fourdvar.env`. Two consequences follow:

- **A missing required variable raises on import**, before any work starts.
  That's deliberate — better to fail immediately than after an hour of CMAQ.
- **Changing an environment variable mid-process has no effect.** Anything that
  needs different configuration must be a separate process.

## Targets

The `TARGET` environment variable (default `docker`) names an environment. On
import, `.env.${TARGET}` is read from the **repository root**.

Targets exist because most configuration is filesystem paths, and those are the
part that changes between a container, a developer's machine and a cluster. The
scientifically meaningful settings — dates, domain — are passed in per run.

Tracked targets:

| Target | Purpose |
| --- | --- |
| `docker` | Running in the container. Paths under `STORE_PATH`, which is supplied per run. |
| `docker-test` | Tests and development. Points at test data tracked in the repository under `tests/test-data/`, so it needs no network access and no previous run. Also pins `START_DATE`, `END_DATE` and `DOMAIN_NAME`. |
| `docker-monthly` | The monthly workflow, where meteorology and observations come from previous daily runs rather than being generated. |

For tests and local development, always set `TARGET=docker-test`.

Unsupported example targets for NCI/Gadi are in
[`examples/nci`](../../examples/nci/README.md). They must be copied to the
repository root to be picked up.

To add a target, create `.env.yourname` in the repository root and set
`TARGET=yourname`. `.env.*` files other than the tracked ones are ignored by
git. See [Installing locally](../guides/local-install.md#3-configuration).

## Precedence

**Existing environment variables always win over the `.env.${TARGET}` file.**
The file is loaded with `override=False`.

This is what makes the targets usable: the file supplies the stable layout, and
the caller supplies what varies per run.

```shell
# .env.docker provides paths; the caller provides the run
START_DATE=2023-01-01 END_DATE=2023-01-31 DOMAIN_NAME=aust10km \
  TARGET=docker python runscript.py
```

Shell scripts that need the same variables exported into their own environment
source `scripts/environment.sh`, which loads `.env.${TARGET}` while preserving
pre-existing values, matching the Python behaviour.

### Variable expansion

`.env.${TARGET}` files may reference other variables:

```dotenv
MET_DIR="${STORE_PATH}/mcip"
CAMS_FILE="${STORE_PATH}/cams/cams_eac4_methane_${START_DATE}-${END_DATE}.nc"
```

Variables used in expansions must be defined **outside** the file — this is why
`.env.docker` lists `START_DATE`, `END_DATE`, `DOMAIN_NAME`, `DOMAIN_VERSION` and
`STORE_PATH` in comments rather than setting them. Defining them in the same file
that expands them clashes.

### Date placeholders

Some path variables are templates expanded per simulation day, not by the shell:

| Placeholder | Expands to |
| --- | --- |
| `<YYYY-MM-DD>` | The day, e.g. `2023-01-15` |
| `<YYYYMMDD>` | The day without separators, e.g. `20230115` |
| `<YYYY>`, `<MM>`, `<DD>` | Individual components |

For example:

```dotenv
ICON_FILE="${CTM_DIR}/<YYYY-MM-DD>/d01/ICON.d01.${DOMAIN_MCIP_SUFFIX}.CH4only.nc"
MET_DIR="${STORE_PATH}/${DOMAIN_NAME}/daily/<YYYY>/<MM>/<DD>/mcip"
```

Leave these in angle brackets. They are not shell syntax and must not be quoted
away or pre-expanded.

## Credentials

Credentials are kept separate from targets, in a `.env` file in the repository
root, which is not tracked by git. Start from
[`.env.example`](../../.env.example):

```shell
cp .env.example .env
```

| Variable | For |
| --- | --- |
| `CDSAPI_KEY`, `CDSAPI_URL` | Downloading CAMS methane fields for boundary conditions. Requires a Copernicus [Atmosphere Data Store](https://ads.atmosphere.copernicus.eu/) account. |

> [!NOTE]
> `CDSAPI_KEY` must hold credentials for the Atmosphere Data Store (**ADS**), not
> the Climate Data Store (**CDS**). The two share a credentials file format and
> an ECMWF login but are separate services with separate terms to accept.

The Docker workflow scripts read `.env` on the host and pass the relevant values
into each container as needed, rather than mounting the file.

## Run-scoped paths

`STORE_PATH` is the root of a single run's data. Most other paths default to
somewhere beneath it, so one run's inputs, intermediates and results stay
together and separate runs do not collide.

The end-to-end scripts derive it as:

```
${DATA_ROOT}/{daily|monthly}/${DOMAIN_NAME}/${DOMAIN_VERSION}/${START_DATE}
```

`DATA_ROOT` is a host path; `STORE_PATH` is the corresponding path inside the
container (under `/app/data`). When passing paths into a container, they
must be container paths — a host path that happens to exist will silently
resolve to nothing useful inside.

One path deliberately sits outside `STORE_PATH`: `CHK_PATH`, holding CMAQ
checkpoint files. These are large and rewritten constantly, so they belong on
fast scratch disk. The container entrypoint clears `CHK_PATH` when a command
finishes.

## Inspecting the resolved configuration

To see what a target actually resolves to:

```shell
TARGET=docker-test uv run python -c "
from openmethane.fourdvar.params import cmaq_config, date_defn, root_path_defn
print('store  ', root_path_defn.store_path)
print('dates  ', date_defn.start_date, '->', date_defn.end_date)
print('met    ', cmaq_config.mcip_output_path)
print('chk    ', cmaq_config.chk_path)
print('adjoint', cmaq_config.fwd_prog, cmaq_config.bwd_prog)
"
```

`scripts/environment.sh` also prints the full environment after loading a
target, which is what the workflow scripts log at the start of each step.
