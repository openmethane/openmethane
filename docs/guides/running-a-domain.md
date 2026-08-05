# Running your own domain

This guide covers running Open Methane over an area and time period you care
about, rather than the tiny test domain.

Work through the [Quickstart](quickstart.md) first. It establishes that Docker,
your credentials and the workflow scripts all work, which is much easier to
debug on a 10 x 10 grid than on a real domain.

## Before you start: what Open Methane assumes

Open Methane was built to estimate methane emissions over Australia, and some of
that is baked in rather than configurable. Check these against your intended run
before investing time in it.

**The prior is Australia-specific.** `openmethane-prior` builds its emissions
estimate from Australian sources — the National Greenhouse and Energy Report,
the National Inventory, and Australian land-use data — supplemented by global
datasets for wetlands and fires. Outside Australia it has no inventory to
distribute, so a domain elsewhere will not produce a meaningful prior, and
without a meaningful prior the inversion has nothing to correct.

**The inversion needs a reasonable window.** A single day rarely constrains
emissions usefully. The workflows are built around inverting roughly a month of
daily runs at a time.

## Usable time periods

**Open Methane can be run from 2018 onwards.** The recent end of the range is
not a hard cut-off but a gradual loss of accuracy: the input data sources age at
different rates, and the prior degrades as you approach the present.

The most significant of these is the **Australian National Inventory, which is
published on roughly a two-year lag**. For a period more recent than the latest
available inventory, the prior has to fall back on older inventory data, so it
no longer reflects the activity actually occurring in the period being modelled.
The inversion will still run and still correct the prior where observations
constrain it, but the starting point is less trustworthy, and cells with little
observational coverage stay close to that less trustworthy starting point.
Treat very recent runs as provisional.

The 2018 lower bound comes from the two input datasets with the latest start
dates:

- **Meteorology.** WRF is driven by the NCEP FNL analysis, which begins
  **2015-07-09**. Earlier dates fail at the WRF step.
- **Observations.** Open Methane uses the TROPOMI methane product from the
  Copernicus Data Space Ecosystem. Sentinel-5P launched in October 2017 and
  products are catalogued from **2018-04-30**, which is the primary constraint.
  At the recent end, products lag acquisition by two to three days, so the last
  few days are never available — see [TROPOMI data](../reference/tropomi.md).

Coverage within the usable range is also uneven. TROPOMI retrieves methane only
in cloud-free daylight conditions over suitable surfaces, so some days over your
domain will yield few or no usable observations. This affects how much a given
month can actually constrain, and is worth checking before attributing a result
to a change in emissions.

## 1. Choose or create a domain

Existing domains, defined in
[setup-wrf](https://github.com/openmethane/setup-wrf/tree/main/domains):

| Domain     | Coverage | Notes |
|------------| --- | --- |
| `aust10km` | All of Australia, 10 km cells | The production domain. 454 x 430 cells. |
| `aust25km` | All of Australia, 25 km cells | Coarser and considerably cheaper. |
| `aust-nsw` | New South Wales | Regional. |
| `au-test`  | Tiny | Test domain, not scientifically meaningful. |

If none of these cover your area of interest at the resolution you need, see
[Creating a custom domain](custom-domain.md). Expect this to be the most
involved part of the process: a domain has to satisfy WRF and MCIP, and both
the prior and this repository need a matching domain file.

Set your choice with `DOMAIN_NAME` and `DOMAIN_VERSION`.

## 2. Point `DOMAIN_FILE` at your domain

The area observations are fetched for is taken from the domain definition file
named by `DOMAIN_FILE`: `scripts/obs_preprocess/fetch_tropomi.py` reads the
domain's bounding box and asks the catalogue for granules whose swath crosses
it. There is no separate bounding box to keep in step with the domain, and
nothing to configure per domain beyond `DOMAIN_FILE` itself.

The end-to-end scripts set `DOMAIN_FILE` for you, downloading
`domain.${DOMAIN_NAME}.nc` from the public data store into the run directory. A
custom domain has to be placed there yourself — see
[Creating a custom domain](custom-domain.md#using-your-domain).

Granules are downloaded whole, since the mirror offers no server-side
subsetting; `tropomi_methane_preprocess.py` drops observations outside the model
grid. For a small domain that means downloading considerably more data than
ends up being used. See [TROPOMI data](../reference/tropomi.md).

## 3. Size the run

Cost scales with the number of grid cells and the number of days, and the
inversion multiplies that by the number of iterations. A full `aust10km` month
is a serious computation — production runs it on cloud infrastructure, and it
will take many hours to days on a workstation.

Relevant settings:

| Setting | Effect |
| --- | --- |
| `NUM_PROC_ROWS`, `NUM_PROC_COLS` | Decompose the CMAQ grid across MPI processes. Their product is the number of processes CMAQ uses. |
| `NCPUS` | Parallelism for WRF and for TROPOMI preprocessing. |
| `MAX_ITERATIONS` | Caps the inversion at this many successful L-BFGS-B iterations (default 20). Lower it to bound runtime. |
| `BOUNDARY_TRIM` | Cells removed from each edge of the domain for boundary conditions. `5` for `aust10km`; small domains need a smaller value or MCIP will trim the domain away entirely. |
| `CHK_PATH` | Where CMAQ checkpoint files go. These are large and written repeatedly — put them on fast local disk. |

See [Parameters](../reference/parameters.md) for the full list.

## 4. Run the daily workflow for each day

Every day in your period needs a daily run before the inversion can use it. Set
the domain and date, and give the run somewhere with enough disk to live:

```shell
export DATA_ROOT=/data/openmethane
export DOMAIN_NAME=aust10km
export DOMAIN_VERSION=v1
export BOUNDARY_TRIM=5
export NCPUS=8

for d in $(seq 0 30); do
  START_DATE=$(date -d "2023-01-01 + $d day" +%Y-%m-%d) \
    bash scripts/docker-e2e-daily.sh
done
```

Each run writes to `${DATA_ROOT}/daily/${DOMAIN_NAME}/${DOMAIN_VERSION}/${START_DATE}`.

Days are independent, so they can be run in parallel or across machines if you
have the capacity — the only shared state is WRF's geography data under
`${DATA_ROOT}/geog`, which is downloaded once.

## 5. Run the inversion

Once the daily runs covering your period are complete:

```shell
START_DATE=2023-01-01 END_DATE=2023-01-31 \
  bash scripts/docker-e2e-monthly.sh
```

This collects the daily meteorology and processed observations, regenerates the
prior for the whole period, and runs the inversion. Results are written to
`${DATA_ROOT}/monthly/${DOMAIN_NAME}/${DOMAIN_VERSION}/${START_DATE}`.

`END_DATE` is inclusive. The period does not have to be a calendar month despite
the workflow's name, but shorter periods give the inversion less to work with.

## 6. Produce alerts (optional)

Alerts are separate from the inversion and are run by their own scripts. Build a
baseline once per domain from a period of daily runs, then create alerts for
individual days against it:

```shell
START_DATE=2023-01-01 END_DATE=2023-01-31 \
  bash scripts/docker-alerts-baseline.sh

START_DATE=2023-01-15 bash scripts/docker-create-alerts.sh
```

The baseline is written to
`${DATA_ROOT}/alerts-baseline.${DOMAIN_NAME}-${DOMAIN_VERSION}.nc` and reused by
every day of that domain, so it only needs rebuilding when you want it to cover
a different period. `ALERTS_COUNT_THRESHOLD` (default 30) is the minimum number
of observations a cell needs before it can be assessed at all; on a real domain
the default is usually appropriate.

## 7. Interpret the results

See [Outputs](../reference/outputs.md) for the files produced and what their
variables mean. The headline results are the posterior emissions and the
per-cell multipliers applied to the prior.

Two things worth checking before drawing conclusions from a run:

- **Did the inversion converge, or did it hit `MAX_ITERATIONS`?** The
  optimisation log records this. Hitting the cap means the answer is wherever
  the optimiser happened to be, not a converged solution.
- **How much observational coverage did the period actually have?** Cells the
  satellite never saw are unconstrained, and their posterior will sit at or near
  the prior. That is the correct behaviour, but it means "no change from prior"
  and "confirmed as correct" look identical unless you check coverage.

## Running individual steps

The end-to-end scripts are convenient but coarse: each one runs a whole
workflow, and re-running repeats work. When iterating, it is often better to run
single steps directly in the container. Each step is a script — see
[Scripts](../reference/scripts.md) for the inventory, and
[Configuration](../reference/configuration.md) for the environment each expects.
