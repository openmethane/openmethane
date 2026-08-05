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

Downloads methane fields from
[CAMS](https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/cams-global-reanalysis-eac4)
on pressure levels, to `CAMS_FILE`. CAMS is a global atmospheric reanalysis; it
supplies what methane is entering the domain from outside, which the regional
model cannot know on its own.

Requires ADS credentials. Skip with `SKIP_CAMS_DOWNLOAD`.

### setup_for_cmaq

The substantial step. `scripts/cmaq_preprocess/setup_for_cmaq.py`:

- checks the required WRF output files exist
- runs **MCIP** to extract meteorology from the WRF output and interpolate it
  onto the CMAQ grid
- prepares initial and boundary conditions using **ICON** and **BCON**
- interpolates the CAMS data onto the CMAQ grid

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
signal, and the inversion would attempt to explain it by adjusting emissions. The
correction is computed over the region actually sampled by observations, unless
`DISABLE_CORRECT_BIAS_BY_REGION` is set to exactly `"true"`, in which case the
whole domain is used. A fixed additional offset can be applied with
`CAMS_TO_CMAQ_BIAS`.

## Verifying the output

After a successful run, `MET_DIR` and `CTM_DIR` are populated, and
`run-cmaq-preprocess.sh` prints a tree of both.

Worth checking on a new domain, before running anything expensive:

- The MCIP grid dimensions match what you expect after `BOUNDARY_TRIM`.
- Filenames contain the `DOMAIN_MCIP_SUFFIX` that later stages will look for.
  This variable has different defaults in different code paths, so mismatched
  names here are a common cause of "file not found" much later.
- `GRIDDESC` in the MCIP output directory describes the intended projection.
