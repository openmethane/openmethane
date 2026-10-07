# CMAQ preprocessing

CMAQ preprocessing turns the outputs of the other two repositories — WRF
meteorology and the prior emissions estimate — into the specific set of files the
CMAQ adjoint expects to find on disk.

This is the stage that most commonly fails on a new domain, because it is where
grid geometry, file naming conventions and the compiled models all have to agree.

The whole stage runs via:

```shell
bash scripts/cmaq_preprocess/run-cmaq-preprocess.sh
```

## Prerequisites

Before this stage can run:

- **WRF has been run** for the period, producing output in `WRF_DIR`, and the
  domain geometry file `geo_em.d??.nc` is in `GEO_DIR`. Both come from
  [setup-wrf](https://github.com/openmethane/setup-wrf). Example WRF output for
  the `au-test` domain is tracked in `tests/test-data/wrf`.
- **The prior has been generated**, at `PRIOR_FILE`, by
  [openmethane-prior](https://github.com/openmethane/openmethane-prior).
- **The CMAQ binaries are available** in `CMAQ_BIN`, and the adjoint executables
  at `ADJOINT_FWD` and `ADJOINT_BWD`.

## Steps

`run-cmaq-preprocess.sh` runs the following in order. Each can be skipped with an
environment variable, which is how the monthly workflow avoids repeating work the
daily runs already did.

### download_cams_input

Downloads global methane fields from CAMS to `CAMS_FILE`, which defaults to
`${STORE_PATH}/cams/cams_{product}[_{release}]_methane_{start}-{end}.nc`. The
inversion's release is in the name, so a file from another release is never
reused. The fields supply what
methane is entering the domain from outside, which the regional model cannot
know on its own. `CAMS_PRODUCT` chooses the product:

| `CAMS_PRODUCT` | Product | Notes |
| --- | --- | --- |
| `eac4` | [CAMS global reanalysis (EAC4)](https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/cams-global-reanalysis-eac4), 25 pressure levels, 3-hourly | CH4 is not assimilated: it is a free-running model field, about 110–120 ppb below the satellite-constrained products over the domain. |
| `inversion` (default) | [CAMS greenhouse gas inversion](https://ads.atmosphere.copernicus.eu/datasets/cams-global-greenhouse-gas-inversion), surface and satellite, 34 hybrid levels, 6-hourly | Constrained by the NOAA surface network and TROPOMI. Covers up to the end of the latest release's last year. Releases re-process past dates, so `CAMS_INVERSION_VERSION` is pinned and recorded. |

The inversion cannot be subset on the ADS. Each month is a 2.2 GB global file,
which the script fetches with parallel range requests (about 4 minutes) and cuts
to the domain, plus 3° of padding, before saving. It needs that much temporary
disk next to `CAMS_FILE`. If the dates are beyond the inversion's coverage the
download fails with an error that says so.

Requires ADS credentials. Skip with `SKIP_CAMS_DOWNLOAD`.

### setup_for_cmaq

The substantial step. `scripts/cmaq_preprocess/setup_for_cmaq.py`:

- checks the required WRF output files exist
- runs **MCIP** to extract meteorology from the WRF output and interpolate it
  onto the CMAQ grid
- prepares initial and boundary conditions using **ICON** and **BCON**
- interpolates the CAMS data onto the CMAQ grid. A reader for each product
  (`cams_readers.py`) returns methane in ppmV and the pressure of every level, on
  the CAMS grid and levels. This is a common intermediate, not the CMAQ format,
  so both products take the same path from there: the nearest CAMS cell for each
  CMAQ column, then linear interpolation in log-pressure from that cell's levels
  onto the column's own CMAQ layer pressures. The result is written to the ICON
  and BCON files on CMAQ's own cells and layers, with `CAMS_PRODUCT` and, for the
  inversion, `CAMS_RELEASE` as global attributes.

Afterwards there are results in `MET_DIR` and `CTM_DIR`.

Skip with `SKIP_CMAQ_SETUP`, which the monthly workflow sets because the daily
runs already produced MCIP output.

> [!NOTE]
> MCIP trims cells from the edge of the domain to use as boundary conditions,
> controlled by `BOUNDARY_TRIM`. The output grid is therefore smaller than the
> WRF grid — see
> [Creating a custom domain](../guides/custom-domain.md#grid) for the arithmetic.
> On a small domain the default trim can consume the entire grid.

This step invokes the csh run scripts in `scripts/cmaq/` (`run.mcip`, `run.icon`,
`run.bcon`), with arguments assembled in
`src/openmethane/cmaq_preprocess/run_scripts.py`. When MCIP, ICON or BCON fail,
the error comes from those scripts, and the generated script plus its log in the
run directory is the place to look.

### Template generation

Three scripts, skipped together with `SKIP_TEMPLATE_GENERATION`:

**`make_emis_template.py`** creates the CMAQ emissions template from the prior.

**`make_template.py`** creates the template files `fourdvar` uses to generate
input files on each iteration. It:

- copies an emissions template into the input directory
- defines CMAQ filenames for the first day of the model run
- prepares the CMAQ run directories
- redefines `cmaq_config` values that depend on the template files
- generates sample files by running **one day of CMAQ, forwards and backwards**
- makes a forcing file with the same attributes as the concentration file, zeroed
- creates templates for the concentration, forcing and sensitivity files
- cleans up the files CMAQ created

Because it runs CMAQ, this step needs the adjoint binaries and takes real time.
It also means a failure here may be a CMAQ configuration problem rather than a
template problem.

**`make_prior.py`** creates the prior in the form `fourdvar` consumes, including
initial conditions if `input_defn.inc_icon` is set.

These three can be run on their own:

```shell
make prepare-templates
```

### bias_correct_cams

Not part of `run-cmaq-preprocess.sh`, but part of the same stage in the
workflows, run afterwards as
`scripts/cmaq_preprocess/bias_correct_cams.py`.

CAMS and CMAQ disagree systematically about background methane concentration.
Left uncorrected, that offset is indistinguishable from a domain-wide emissions
signal, and the inversion would attempt to explain it by adjusting emissions.

The correction is measured by running the forward model once over the month at
the prior emissions and differencing the mean simulated column from the mean
observed column, over every sounding. That residual is the same quantity the
inversion driver reports as its first-guess `bias`, so applying it to the ICON
and BCON fields drives that report to zero. Because each sounding's column
operator puts a total weight of `W` on the model, the residual is divided by `W`
to express it as a shift of the concentration field. `O`, `F` and `W` are all
logged.

The correction is confined to what the observations see by construction: only
cells carrying observation weight enter the simulated mean, so no separate
regional masking is applied. A fixed additional offset can be applied with
`CAMS_TO_CMAQ_BIAS`.

The size of the correction is logged. Against EAC4 it is about +108 ppb. The
inversion is already anchored to TROPOMI, so expect a few ppb with
`CAMS_PRODUCT=inversion`: a large value points to a units or mapping error.

## Verifying the output

After a successful run, `MET_DIR` and `CTM_DIR` are populated, and
`run-cmaq-preprocess.sh` prints a tree of both.

Worth checking on a new domain, before running anything expensive:

- The MCIP grid dimensions match what you expect after `BOUNDARY_TRIM`.
- Filenames contain the `DOMAIN_MCIP_SUFFIX` that later stages will look for.
  This variable has different defaults in different code paths, so mismatched
  names here are a common cause of "file not found" much later.
- `GRIDDESC` in the MCIP output directory describes the intended projection.
