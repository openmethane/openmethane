# Overview

Open Methane estimates gridded methane emissions over an area of interest by
combining an initial emissions estimate with observations of atmospheric
methane using a technique called **inversion modelling**.

The basic idea:

1. Build an estimate of methane emissions for each grid cell, from
   inventories and public data. In an inversion this is called a **prior**.
2. Run an **atmospheric transport model** forwards to predict what the
   atmospheric methane concentration should look like given those emissions.
3. Compare the prediction against what a satellite or other measurement 
   device **actually observed**.
4. Run the transport model **backwards** (its adjoint) to work out which
   changes to the emissions would best explain the difference.
5. Repeat many iterations until the simulated concentrations match the
   observations as closely as the data supports. The result is the
   **posterior** emissions estimate.

Steps 2–5 are a 4D-Var (four-dimensional variational) data assimilation, which
is where the name of the `fourdvar` package comes from. Large differences
between simulated and observed concentrations are also published as **alerts**,
independently of the inversion.

For a longer, non-technical explanation of the method, see
[the methodology notes](methodology/). For the internals of the inversion
itself, see [Architecture](reference/architecture.md).

## Repositories

Running the full pipeline needs three repositories.

| Repository | Responsibility |
| --- | --- |
| [openmethane-prior](https://github.com/openmethane/openmethane-prior) | Produces the prior emissions estimate for a domain, by sector (livestock, fugitives, industry, wetlands, fires, …). Ships with downloadable input data so it runs out of the box for Australia. |
| [setup-wrf](https://github.com/openmethane/setup-wrf) | Runs the WRF weather model to produce the meteorology that drives atmospheric transport. Also holds the domain definitions. |
| **openmethane** (this repo) | Converts WRF output into CMAQ inputs, processes TROPOMI satellite observations, and runs the CMAQ adjoint inversion. |

Each publishes a public Docker image to the GitHub Container Registry, so you do
not need to install any of them from source to run the pipeline. See the
[Quickstart](guides/quickstart.md).

The CMAQ adjoint model itself is built in
[CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint) and baked into this
repository's Docker image. That repository and its image are private; see
[Installing locally](guides/local-install.md) if you need the binaries outside
the published image.

## Two workflows

Open Methane runs as two separate workflows on different cadences. This split
exists because the expensive, parallelisable work (weather, observations) is
per-day, while the inversion needs a longer window to constrain emissions
usefully.

`scripts/docker-e2e-daily.sh` and `scripts/docker-e2e-monthly.sh` run these
workflows end to end using Docker. They are the most reliable description of
what actually runs, and are what the [Quickstart](guides/quickstart.md) uses.

Open Methane Alerts are considered a secondary product and can be produced
as part of the daily/monthly workflows, or in two smaller standalone workflows.
See `scripts/docker-alerts-baseline.sh` and `scripts/docker-create-alerts.sh`
for the steps required to produce alerts.

### Daily workflow

Runs once per calendar day. It prepares that day's inputs and simulates the
atmosphere forwards from the prior. It does **not** perform an inversion.

These steps are independent and can run in parallel:

- **WRF** — runs `scripts/run-wrf.sh` in setup-wrf to produce meteorology.
- **Prior** — runs `scripts/run.sh` in openmethane-prior to produce
  `prior-emissions.nc`.
- **Fetch observations** — downloads the day's TROPOMI methane granules.

Then, in sequence:

- **CMAQ preprocessing** — converts WRF output and the prior into CMAQ inputs
  (meteorology via MCIP, initial and boundary conditions via ICON/BCON,
  emissions and CMAQ templates).
- **Process observations** — converts raw TROPOMI granules into the observation
  format `fourdvar` consumes.
- **Daily forward run** — `scripts/fourdvar/run_daily_step.py`: a single forward
  simulation producing *simulated observations*, i.e. what the satellite should
  have seen given the prior.

The day's outputs are then archived, because the monthly workflow and the alerts
workflows all reuse them.

<img src="images/stepfunctions_graph_daily.svg">

### Monthly workflow

Runs over a month of daily outputs and performs the actual inversion.

First, the prior is generated for the whole period, and the MCIP meteorology and
processed observations from each daily run covering the period are loaded.

Then, in sequence:

- **CMAQ preprocessing** — prepares CMAQ inputs from the prior. MCIP is skipped
  (`SKIP_CMAQ_SETUP=true`) because the daily runs already produced it.
- **Bias correction** — corrects bias between the CAMS boundary conditions and
  CMAQ.
- **Inversion** — `runscript.py`, the L-BFGS-B optimisation that iterates the
  CMAQ forward and adjoint models to find the emissions best matching the
  month's observations.

<img src="images/stepfunctions_graph_monthly.svg">

### Alerts workflows

Alerts are graded against a **baseline** of how large the difference between
simulated and observed concentrations normally is in each cell, so they run in
two stages, both reading the outputs of completed daily runs:

- **Alerts baseline** — `scripts/alerts/alerts_baseline.py`, over a period of
  daily runs. Run once per domain, and reused by every day of that domain.
- **Create alerts** — `scripts/alerts/create_alerts.py`, for one day, comparing
  that day against the baseline.

Neither depends on the inversion, so anomalies surface without waiting for a
monthly run.

## Key concepts

A few ideas recur throughout the configuration and documentation.

**Domain.** The area being modelled, together with the grid it is divided into
and the map projection that grid sits on. Domains are versioned and identified
by `DOMAIN_NAME` and `DOMAIN_VERSION` — for example `aust10km` `v1`, the whole
Australian land mass in 10 km cells. Domains must be defined in a way that WRF
and MCIP accept, so they originate in setup-wrf. See
[Creating a custom domain](guides/custom-domain.md).

**Target.** Which environment the code is running in, set by the `TARGET`
environment variable. It selects a `.env.${TARGET}` file of mostly filesystem
paths. See [Configuration](reference/configuration.md).

**Store path.** `STORE_PATH` is the root directory for a single run's data. Most
other paths are defined relative to it, so one run's inputs, intermediates and
results stay together.

**Prior and posterior.** The prior is the emissions estimate going in; the
posterior is the corrected estimate coming out. The inversion solves for
per-cell multipliers on the prior rather than for emissions directly, so the
posterior is published both as multipliers and as absolute emissions.