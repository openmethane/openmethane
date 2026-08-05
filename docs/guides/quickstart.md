# Quickstart

This guide runs Open Methane end to end on `au-test` — a deliberately tiny
10 x 10 cell domain — using the published Docker images. Nothing is built from
source, and you don't need access to any private repositories.

The point of this guide is to confirm your machine, credentials and data
directories all work before you commit to a real domain. On consumer hardware
the daily workflow takes tens of minutes; the monthly workflow rather longer.

Once this works, see [Running your own domain](running-a-domain.md).

## 1. Prerequisites

- [Docker](https://www.docker.com/) 23 or later, able to run `linux/amd64`
  images.
- A local clone of this repository. You need it for the orchestration scripts
  and configuration files, not for the code itself:

  ```shell
  git clone https://github.com/openmethane/openmethane.git
  cd openmethane
  ```

  Run every command below from the repository root.
- Roughly 20 GB of free disk. Most of it goes on WRF's global geography data,
  which is downloaded once and reused.

You do not need Python, `uv`, or a compiler.

## 2. Credentials

One account is needed. The **Copernicus Atmosphere Data Store (ADS)** requires a
free account to download CAMS methane fields used as boundary conditions. Create
an account at
[ads.atmosphere.copernicus.eu](https://ads.atmosphere.copernicus.eu/) and copy
your API key from your profile page.

Put your ADS key in a `.env` file in the repository root. Start with:

```shell
cp .env.example .env
```

Then fill in:

```dotenv
CDSAPI_KEY=your-ads-api-key
CDSAPI_URL=https://ads.atmosphere.copernicus.eu/api
```

Note: the environment variable called `CDSAPI_KEY`, must contain credentials
from Copernicus **ADS**, not **CDS**. The two systems do not share credentials.

`.env` is not tracked by git. See [Configuration](../reference/configuration.md)
for how it relates to the other `.env.*` files.

Nothing else needs credentials. TROPOMI observations are found in the Copernicus
Data Space Ecosystem catalogue and downloaded from a public AWS mirror, both of
which are anonymous — see [TROPOMI data](../reference/tropomi.md).

## 3. Run the daily workflow

The daily workflow prepares one day of inputs and runs a single forward
simulation. Run it for a day that has TROPOMI coverage:

```shell
START_DATE=2022-10-29 bash scripts/docker-e2e-daily.sh
```

This pulls the three published images and runs each step of the
[daily workflow](../overview.md#daily-workflow) as a separate container,
mirroring how production runs them. Results are written to
`/tmp/openmethane-e2e/daily/au-test/v1/2022-10-29` — override the root with
`DATA_ROOT`.

Repeat for each day you want to include in the inversion. The monthly workflow
needs at least the full range of days it will cover:

```shell
for d in 2022-10-29 2022-10-30 2022-10-31; do
  START_DATE=$d bash scripts/docker-e2e-daily.sh
done
```

## 4. Run the monthly workflow

The monthly workflow reuses the meteorology and processed observations from the
daily runs, and performs the actual inversion:

```shell
START_DATE=2022-10-29 END_DATE=2022-10-31 bash scripts/docker-e2e-monthly.sh
```

Note: this invocation specifies 3 successive days, enough to test the system,
but normally a monthly run would include a full month of daily results.

Results land in `/tmp/openmethane-e2e/monthly/au-test/v1/2022-10-29`. The
inversion iterates the CMAQ forward and adjoint models, so this is by far the
most expensive step; `MAX_ITERATIONS` (default 20) caps it.

See [Outputs](../reference/outputs.md) for what the result files contain.

## 5. Create alerts (optional)

Alerts are independent of the inversion, and are produced by two scripts of
their own rather than as part of the daily or monthly workflow.

A cell is alerted when the difference between observed and simulated
concentrations is unusually large *for that cell*, so a **baseline** of how large
that difference normally is has to exist first. The baseline is built from a
period of completed daily runs:

```shell
START_DATE=2022-10-29 END_DATE=2022-10-31 bash scripts/docker-alerts-baseline.sh
```

Days in the range with no daily run are skipped with a warning; if none are
found the script tells you so and exits. The baseline is shared by every day of
the domain, so it is written once to
`/tmp/openmethane-e2e/alerts-baseline.au-test-v1.nc`.

Alerts are then created for a single day from that day's daily run:

```shell
START_DATE=2022-10-29 bash scripts/docker-create-alerts.sh
```

The result is `alerts.nc` in that day's run directory. The script checks for
both the daily run and the baseline up front and tells you which command to run
if either is missing.

> [!NOTE]
> `au-test` is 10 x 10 cells, far too small for a cell to collect the 30
> observations `ALERTS_COUNT_THRESHOLD` requires by default, so
> `docker-create-alerts.sh` lowers it to `2`. The resulting alerts are a check
> that the machinery works, not a meaningful result.

## Using locally built images

By default the scripts pull `ghcr.io/openmethane/*:stable`. To test local
changes instead, check out `openmethane-prior` and `setup-wrf` as siblings of
this repository and build:

```shell
BUILD_LOCAL_DOCKER=true bash scripts/docker-e2e-daily.sh
```

Building the `openmethane` image requires access to the private CMAQ-Adjoint
base image — see [Development](development.md).

Individual images can also be pinned without building, which is useful for
reproducing a specific run:

```shell
OPENMETHANE_IMAGE=ghcr.io/openmethane/openmethane:1.2.0 \
  bash scripts/docker-e2e-daily.sh
```

## If something fails

See [Troubleshooting](../troubleshooting.md). The most common first-run problems
are missing or misspelled ADS credentials in `.env`, an ADS account that has not
accepted the dataset's terms, and choosing a date with no TROPOMI granules
published yet — the archive lags acquisition by two to three days.