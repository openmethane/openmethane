# Changelog

Versions follow [Semantic Versioning](https://semver.org/) (`<major>.<minor>.<patch>`).

Backward incompatible (breaking) changes will only be introduced in major versions
with advance notice in the **Deprecations** section of releases.


<!--
You should *NOT* be adding new changelog entries to this file, this
file is managed by towncrier. See changelog/README.md.

You *may* edit previous changelogs to fix problems like typo corrections or such.
To add a new changelog entry, please see
https://pip.pypa.io/en/latest/development/contributing/#news-entries,
noting that we use the `changelog` directory instead of news, md instead
of rst and use slightly different categories.
-->

<!-- towncrier release notes start -->

## openmethane v1.3.0 (2026-09-03)

### ⚠️ Breaking Changes

- Update Dockerfile to use base image based on openmethane/CMAQ

  If using the Dockerfile, no manual changes should be necessary. If running
  locally or in an environment that doesn't support docker, CMAQ will need
  to be provided in such a way that all CMAQ tools (MCIP, BCON, ICON) are built
  into a single location, specified in CMAQ_BIN.

  See https://github.com/openmethane/CMAQ Dockerfile for an example of how to
  configure and build CMAQ binaries into a single location like /opt/cmaq/bin. ([#190](https://github.com/openmethane/openmethane/pull/190))
- Fetch TropOMI methane data from the public `meeo-s5p` S3 bucket instead of the
  NASA GES DISC subsetting API, which no longer performs spatial cropping.

  The bucket is anonymously readable, so `EARTHDATA_USERNAME` and
  `EARTHDATA_PASSWORD` are no longer needed and have been removed from
  the project.

  Granules are now downloaded whole rather than cropped to the bounding box,
  and `tropomi_methane_preprocess.py` drops out-of-domain observations
  as it already did.

  This changes retrieved methane values for small domains. `destripe_smoothing`
  estimates the stripe pattern from a median over +/-100 scanlines along track, so
  only pixels within 100 scanlines of a crop boundary can change; pixels further
  in are unaffected. The practical effect is that there is no change to processed
  observations in the `aust10km` domain where the boundaries fall over ocean.
  For a domain shorter than 200 scanlines, such as `au-test`, every pixel is
  within the band and values shift by of order the single-pixel precision. The
  `destripe_smoothing` was actually intended for whole granules, so the new
  values are the more correct ones.

  Take the area to fetch TropOMI data for from the domain definition file named by
  the `DOMAIN_FILE` environment variable, as `scripts/alerts/alerts_baseline.py`
  already does, rather than from a bounding box in `config/obs_preprocess/`. ([#209](https://github.com/openmethane/openmethane/pull/209))
- Fetched TROPOMI files now go directly into the specified output directory with
  no nested directories, instead of into a subdirectory named after the period
  and bounding box, since whole granules are now fetched.

  The output directory is no longer emptied before a fetch, which could have
  deleted the contents of a directory chosen by the caller. Granules already
  present are skipped instead, so a rerun after a failure only fetches what is
  missing. This is possible because S3 fetches write files to a temp location and
  only move them to the destination when they're complete, so incomplete fetches
  will never appear in the output folder. ([#209](https://github.com/openmethane/openmethane/pull/209))
- The `fetch_tropomi` script now uses the bounding box of the domain for its
  search constraint instead of generic bounds in `config/obs_preprocess/config.json`.
  Domain path should be specified in the `DOMAIN_FILE` environment variable.
  Config files in `config/obs_preprocess` are no longer needed and are removed. ([#209](https://github.com/openmethane/openmethane/pull/209))
- Commands in the docker container now run as `app` user (uid: 1000, gid: 1000) ([#213](https://github.com/openmethane/openmethane/pull/213))
- Required python version is now 3.12. Realistically everything still works with 3.10 and 3.11, but the project will only officially support newer versions moving forward. ([#213](https://github.com/openmethane/openmethane/pull/213))
- Project is moved from `/opt/project` to `/app` in the docker image, to ensure no downstream breakage:
  - data directory should now be mounted under `/app/data`
  - external references to `/opt/project` should be replaced with `/app`

  ([#214](https://github.com/openmethane/openmethane/pull/214))
- Apply the TropOMI column averaging kernel when simulating observations. ([#222](https://github.com/openmethane/openmethane/pull/222))

### 🎉 Improvements

- Replace templated run scripts with environment variables ([#191](https://github.com/openmethane/openmethane/pull/191))
- Change default output folder to "archive/openmethane" from "archive_Pert/202207_test" ([#195](https://github.com/openmethane/openmethane/pull/195))
- Official docker images from GitHub Container Registry are now the default for
  `docker-e2e-daily.sh` and `docker-e2e-monthly.sh` scripts. The scripts can be
  configured to build and use local images (the previous behaviour) with:
  ```shell
  OPENMETHANE_IMAGE=openmethane OPENMETHANE_PRIOR_IMAGE=openmethane-prior \
    SETUP_WRF_IMAGE=setup-wrf BUILD_LOCAL_DOCKER=true \
    scripts/docker-e2e-daily.sh
  ``` ([#197](https://github.com/openmethane/openmethane/pull/197))
- Move alerts-baseline and create-alerts out of docker-e2e scripts into their own workflows. Resolves #202. ([#206](https://github.com/openmethane/openmethane/pull/206))
- Sped up the alerts baseline by two to three orders of magnitude. Observations
  are now indexed spatially instead of being scanned once per grid cell, and
  `NCPUS` spreads the work over days rather than over grid cells, where it was
  previously sending hundreds of gigabytes between processes and made the run
  slower than using a single core. A month of `aust10km` inputs takes minutes
  rather than hours. ([#217](https://github.com/openmethane/openmethane/pull/217))
- Store the TropOMI column mixing ratio precision with each observation, and build
  the observation uncertainty from it as
  `sqrt(model_uncertainty**2 + (2 * ch4_column_precision)**2)`. The model term
  covers everything that is not retrieval noise, defaults to 10 ppb and is set by
  the new `OPENMETHANE_MODEL_UNCERTAINTY` environment variable, replacing the
  hard-coded 20 ppb. This reweights every observation in the cost function. ([#222](https://github.com/openmethane/openmethane/pull/222))

### 🐛 Bug Fixes

- Fix "patch" version bump adding an extra increment during release ([#193](https://github.com/openmethane/openmethane/pull/193))
- generalised test_grad_cmaq.py and matched sensitivity units to CMAQ-Adjoint-2.0.0 ([#215](https://github.com/openmethane/openmethane/pull/215))
- `alerts_baseline` now fails with a clear error when `ALERTS_BASELINE_DIRS` is
  unset or matches no directories, instead of failing later with a confusing
  error. ([#217](https://github.com/openmethane/openmethane/pull/217))
- fix emission sensitivity units to match new CMAQ ([#219](https://github.com/openmethane/openmethane/pull/219))


## openmethane v1.2.0 (2026-01-28)

### ⚠️ Breaking Changes

- Archive scripts (`scripts/archive.py`, `scripts/load_from_archive.py`), which
  are specific to Open Methane production infrastructure, have been removed and
  are now part of the om-infra repo. ([#184](https://github.com/openmethane/openmethane/pull/184))
- Move sub-packages in src/ into top-level "openmethane" package ([#185](https://github.com/openmethane/openmethane/pull/185))
- Replace poetry with uv for tool and dependency management ([#185](https://github.com/openmethane/openmethane/pull/185))

### 🐛 Bug Fixes

- Fix docker-e2e-daily and docker-e2e-monthly using incorrect prior env vars ([#188](https://github.com/openmethane/openmethane/pull/188))


## openmethane v1.1.1 (2025-10-06)

### 🎉 Improvements

- Allow manual_postproc.py to be configured via environment variables ([#178](https://github.com/openmethane/openmethane/pull/178))


## openmethane v1.1.0 (2025-08-31)

### 🎉 Improvements

- Fetch domain file in load_from_archive.py for daily workflow ([#176](https://github.com/openmethane/openmethane/pull/176))


## openmethane v1.0.0 (2025-08-25)

### ⚠️ Breaking Changes

- Default output filenames have changed to use - instead of _, including:
  - posterior_emissions.nc to posterior-emissions.nc
  - posterior_multipliers.nc to posterior-multipliers.nc
  - alerts_baseline.nc to alerts-baseline.nc

  ([#170](https://github.com/openmethane/openmethane/pull/170))

### 🎉 Improvements

- Update archive scripts to support new 'baseline' workflow ([#156](https://github.com/openmethane/openmethane/pull/156))
- Adding archiving of first-guess simulation of observations ([#158](https://github.com/openmethane/openmethane/pull/158))
- Support new openmethane-prior output format ([#168](https://github.com/openmethane/openmethane/pull/168))
- Fix errors and inconsistencies in CF attributes and variables:
  - replace integer grid cell coordinates in `x` and `y` with grid projection coordinates
  - remove `lat_bounds` and `lon_bounds` from output in favour of `x_bounds` and `y_bounds`
  - fix and add required CF attributes such as `history` and `Conventions`

  ([#168](https://github.com/openmethane/openmethane/pull/168))
- Add prior sector estimates to posterior output file ([#169](https://github.com/openmethane/openmethane/pull/169))
- Update openmethane to support new domain format ([#173](https://github.com/openmethane/openmethane/pull/173))
- Remove create_prior_domain script which has moved to openmethane-prior ([#173](https://github.com/openmethane/openmethane/pull/173))

### 🐛 Bug Fixes

- setting non-neg emissions and configuring via environment ([#157](https://github.com/openmethane/openmethane/pull/157))
- Fix typo in `do_ICs` fork of `interpolate_from_cams_to_cmaq_grid` ([#165](https://github.com/openmethane/openmethane/pull/165))

### 🔧 Trivial/Internal Changes

- [#175](https://github.com/openmethane/openmethane/pull/175)


## openmethane v0.9.5 (2025-03-13)

### 🐛 Bug Fixes

- Fix archive.py store path when run after a workflow failure ([#155](https://github.com/openmethane/openmethane/pull/155))


## openmethane v0.9.4 (2025-03-10)

### 🐛 Bug Fixes

- Skip tropomi files with no `methane_mixing_ratio_bias_corrected` data ([#154](https://github.com/openmethane/openmethane/pull/154))


## openmethane v0.9.3 (2025-03-06)

### 🐛 Bug Fixes

- Fix `long_name` attributes on CH4 and prior_CH4 variables in results file ([#152](https://github.com/openmethane/openmethane/pull/152))


## openmethane v0.9.2 (2025-03-04)

### 🔧 Trivial/Internal Changes

- [#151](https://github.com/openmethane/openmethane/pull/151)


## openmethane v0.9.1 (2025-03-04)

### 🎉 Improvements

- Upload alerts to public data store when daily run is successful ([#150](https://github.com/openmethane/openmethane/pull/150))


## openmethane v0.9.0 (2025-02-27)

### 🎉 Improvements

- Add ability to filter out observations where albedo was below a threshold ([#147](https://github.com/openmethane/openmethane/pull/147))
- Adding SWIR aod filter and storing SWIR aod in obs output ([#148](https://github.com/openmethane/openmethane/pull/148))


## openmethane v0.8.9 (2025-02-26)

### 🐛 Bug Fixes

- Fix multiple threads reading METCRO2D file simultaneously ([#146](https://github.com/openmethane/openmethane/pull/146))

### 🔧 Trivial/Internal Changes

- [#145](https://github.com/openmethane/openmethane/pull/145)


## openmethane v0.8.8 (2025-02-20)

### 🎉 Improvements

- Add common logging module which can be controlled via environment vars ([#139](https://github.com/openmethane/openmethane/pull/139))
- Update alerts baseline file format to follow CF conventions ([#142](https://github.com/openmethane/openmethane/pull/142))

### 🐛 Bug Fixes

- fixing indexing error ([#143](https://github.com/openmethane/openmethane/pull/143))
- Fix alerts baseline creation being dependent on uncertain x, y coordinates ([#144](https://github.com/openmethane/openmethane/pull/144))


## openmethane v0.8.7 (2025-02-18)

### 🎉 Improvements

- calculating alerts with new baseline methodology ([#141](https://github.com/openmethane/openmethane/pull/141))


## openmethane v0.8.6 (2025-02-17)

### 🐛 Bug Fixes

- Fix alerts baseline not handling NaN values ([#140](https://github.com/openmethane/openmethane/pull/140))


## openmethane v0.8.5 (2025-02-13)

### 🎉 Improvements

- Update create_alerts output to follow CF Conventions ([#138](https://github.com/openmethane/openmethane/pull/138))


## openmethane v0.8.4 (2025-02-12)

### 🐛 Bug Fixes

- Fix incorrect s3 path if TARGET_BUCKET doesn't contain a trailing slash ([#137](https://github.com/openmethane/openmethane/pull/137))


## openmethane v0.8.3 (2025-02-12)

### 🎉 Improvements

- Add logging to alerts scripts ([#136](https://github.com/openmethane/openmethane/pull/136))


## openmethane v0.8.2 (2025-02-11)

### 🐛 Bug Fixes

- Fix incorrect paths in _s3_object_fetch calls (41af1e3)

## openmethane v0.8.1 (2025-02-11)

### 🐛 Bug Fixes

- Make `ALERTS_BASELINE_REMOTE` env optional in `load_from_archive.py` (e04bb95)

## openmethane v0.8.0 (2025-02-11)

### 🆕 Features

- Add methane alerts baseline and detection ([#131](https://github.com/openmethane/openmethane/pull/131))

### 🐛 Bug Fixes

- Fix failing tests due to xarray-datatree ([#135](https://github.com/openmethane/openmethane/pull/135))

## openmethane v0.7.1 (2025-02-02)

### 🐛 Bug Fixes

- Fix bug in cmaq_preprocess when mcip folder is loaded from archive without wrf folder ([#130](https://github.com/openmethane/openmethane/pull/130))


## openmethane v0.7.0 (2025-01-29)

### 🎉 Improvements

- Add "daily" sync type to sync a single daily folder during daily reprocessing ([#120](https://github.com/openmethane/openmethane/pull/120))
- Improving bias correction ([#129](https://github.com/openmethane/openmethane/pull/129))


## openmethane v0.6.6 (2025-01-15)

### 🎉 Improvements

- More updates to debug output and logging when running cmaq ([#124](https://github.com/openmethane/openmethane/pull/124))


## openmethane v0.6.5 (2025-01-13)

### 🎉 Improvements

- Collect more debug output and logging in cmaq_preprocess ([#123](https://github.com/openmethane/openmethane/pull/123))


## openmethane v0.6.4 (2025-01-13)

### 🐛 Bug Fixes

- Revert bwd wipeout change in cmaq_preprocess ([#122](https://github.com/openmethane/openmethane/pull/122))


## openmethane v0.6.3 (2025-01-08)

No significant changes.


## openmethane v0.6.2 (2025-01-08)

### 🐛 Bug Fixes

- Fix OPENMETHANE_VERSION being incorrectly populated in container images ([#119](https://github.com/openmethane/openmethane/pull/119))


## openmethane v0.6.1 (2025-01-08)

### 🐛 Bug Fixes

- Fix GitHub Actions script to support dash shell syntax ([#118](https://github.com/openmethane/openmethane/pull/118))


## openmethane v0.6.0 (2025-01-08)

### 🎉 Improvements

- Make OPENMETHANE_VERSION environment variable available inside the container ([#108](https://github.com/openmethane/openmethane/pull/108))
- Set top of model domain to top pressure level. Removes impact of
  unmodelled top of atmosphere on observation operator. Resolves #111. ([#112](https://github.com/openmethane/openmethane/pull/112))
- Add scripts for running dockerised workflows locally ([#113](https://github.com/openmethane/openmethane/pull/113))
- Add post-processing integration test ([#115](https://github.com/openmethane/openmethane/pull/115))
- Adding regional bias correction ([#116](https://github.com/openmethane/openmethane/pull/116))
- Improve monthly results format to adopt more of CF Conventions and make the file plottable in panoply ([#117](https://github.com/openmethane/openmethane/pull/117))


## openmethane v0.5.3 (2024-11-21)

### 🐛 Bug Fixes

- Fix release images failing docker push because they have no valid tags ([#109](https://github.com/openmethane/openmethane/pull/109))


## openmethane v0.5.2 (2024-11-21)

### 🐛 Bug Fixes

- Fix docker build to only push stable image tags when container tests pass.

### 🎉 Improvements

- Combine bump and release workflows into a simplified release process.
- Update container tagging strategy for latest and stable tags ([#103](https://github.com/openmethane/openmethane/pull/103)).

### 🔧 Trivial/Internal Changes

- Small changes to GHA workflows to bring them inline with improvements made in other repos.


## openmethane v0.5.1 (2024-11-19)

### 🐛 Bug Fixes

- Update ADS API URLs from ads-beta to new production domain ads.atmosphere.copernicus.eu in CI/CD.


## openmethane v0.5.0 (2024-11-19)

### ⚠️ Breaking Changes

- `fetch_tropomi_data` now fails if any network requests fail.
  This is more robust than the previous behavior, which would silently ignore any failed requests leading
  to an incomplete or missing observational dataset. ([#89](https://github.com/openmethane/openmethane/pull/89))

### 🆕 Features

- Add retry behaviour when fetching tropomi data
- Add `CHK_PATH` environment variable for defining the location of checkpoint files in CMAQ. ([#89](https://github.com/openmethane/openmethane/pull/89))

### 🎉 Improvements

- Enhanced the verbosity of the minimiser to provide more information about the minimisation process. ([#84](https://github.com/openmethane/openmethane/pull/84))
- Be more specific about the expected MCIP filename when running cmaq_preprocess ([#91](https://github.com/openmethane/openmethane/pull/91))
- Add option to not recalculate the initial/boundary conditions during the CMAQ preprocessing step. ([#93](https://github.com/openmethane/openmethane/pull/93))
- Automatically clean up the directory specified via the `CHK_PATH` environment variable when running via docker.
  This `CHK_PATH` directory is a scratch directory that is used to store temporary files. ([#98](https://github.com/openmethane/openmethane/pull/98))

### 🐛 Bug Fixes

- Correct issue with multi-day monthly bias correction ([#83](https://github.com/openmethane/openmethane/pull/83))
- Correct an error in the calculation of the chi-squared value on each cost-function evaluation. ([#84](https://github.com/openmethane/openmethane/pull/84))
- The checkpoint directory is automatically created which running the model ([#94](https://github.com/openmethane/openmethane/pull/94))
- Handle archiving log streams that are no longer available ([#97](https://github.com/openmethane/openmethane/pull/97))


## openmethane v0.4.1 (2024-09-23)

### 🆕 Features

- Adds configuration for running the `aust-nsw` domain on Gadi
  using the results from an existing daily run. ([#79](https://github.com/openmethane/openmethane/pull/79))

### 🎉 Improvements

- add calculation of posterior emissions for front end ([#71](https://github.com/openmethane/openmethane/pull/71))


## openmethane v0.4.0 (2024-09-23)

### ⚠️ Breaking Changes

- Move `scripts/cmaq_preprocess/upload-domains.py` from Bash to Python ([#48](https://github.com/openmethane/openmethane/pull/48))

### 🆕 Features

- Add archive script to copy the results fo the daily and monthly AWS workflows to S3

  This script is used to archive the daily and monthly outputs to AWS S3, in the case of both a successful
  run and a failure. The failed runs will use a prefix of `/failed/$DOMAIN_NAME/$EXECUTION_ID`,
  while the daily and monthly results are stored in `/results/$DOMAIN_NAME/daily/$YEAR/$MONTH/$DAY` and
  `/results/$DOMAIN_NAME/monthly/$YEAR/$MONTH`, respectively.

  These data can then be fetched from S3 and used for any local analysis or postmortems. ([#47](https://github.com/openmethane/openmethane/pull/47))
- Add script which loads previous results of daily runs for the monthly run. ([#52](https://github.com/openmethane/openmethane/pull/52))
- Move `scripts/archive.py` from Bash to Python, add more error handling, make it runnable when started from
  EventBridge. ([#53](https://github.com/openmethane/openmethane/pull/53))
- Support loading observations from multiple input files using a glob.

  Adds new environment parameter, `TEMPLATE_DIR`, to set the directory containing the CMAQ template files
  and `OBS_FILE_GLOB` to enable override the path of the input observation file/s. ([#55](https://github.com/openmethane/openmethane/pull/55))

### 🎉 Improvements

- Removed a duplicate global entry for the start/end date of a simulation
  and unified how parameters are named throughout `fourdvar`. ([#54](https://github.com/openmethane/openmethane/pull/54))
- Load previous MCIP data when loading from the archive.
- Added support for using fourdvar date identifiers in the CMAQ preprocessing directories.
- Removed an ununsed `diurnal` parameter from `fourdvar`. ([#57](https://github.com/openmethane/openmethane/pull/57))
- Log chi squared and bias values during the cost function execution ([#59](https://github.com/openmethane/openmethane/pull/59))
- Don't clean up data for failed runs to make runs easily restartable ([#60](https://github.com/openmethane/openmethane/pull/60))
- Added bias correction step for CAMS data.

  Fixes shock caused by discontinuity between CAMS free-running model
  and TROPOMI data. 
  the bias_correct_cams script should be included in the monthly
  workflow. It probably isn't necessary for the daily workflow provided
  we use local enhancement as our alerts algorithm. ([#63](https://github.com/openmethane/openmethane/pull/63))
- Added CMAQ gradient test

  This addes a test for the CMAQ adjoint using a simple cost function of
  the sum of squares of model concentrations. the test uses the same
  logic as test_grad_finite_diff but is limited to the steps between
  model input and model output, i.e tests a shorter loop. Provided the
  run_model and run_adjoint are numerical no-ops this *should* be a
  direct test of the cmaq adjoint. ([#67](https://github.com/openmethane/openmethane/pull/67))
- Print logs to stdout when CMAQ fails. ([#68](https://github.com/openmethane/openmethane/pull/68))
- Added destriping function for TROPOMI data ([#72](https://github.com/openmethane/openmethane/pull/72))

### 🐛 Bug Fixes

- Update the prior file location for the docker target ([#46](https://github.com/openmethane/openmethane/pull/46))
- Update `scripts/load_from_archive.py` to use an inclusive end date
  which is a convention used throughout this project. ([#56](https://github.com/openmethane/openmethane/pull/56))

### 📚 Improved Documentation

- Updated the diagrams for the `daily` workflow and added the `monthly` workflow. ([#58](https://github.com/openmethane/openmethane/pull/58))

### 🔧 Trivial/Internal Changes

- [#64](https://github.com/openmethane/openmethane/pull/64), [#66](https://github.com/openmethane/openmethane/pull/66), [#68](https://github.com/openmethane/openmethane/pull/68), [#69](https://github.com/openmethane/openmethane/pull/69), [#73](https://github.com/openmethane/openmethane/pull/73), [#74](https://github.com/openmethane/openmethane/pull/74)


# ## openmethane v0.3.1 (2024-08-07)

No significant changes.


# ## openmethane v0.3.0 (2024-08-07)

### ⚠️ Breaking Changes

- Merge `sat_data` and `obs_preprocess` script directories. ([#33](https://github.com/openmethane/openmethane/pull/33))
- Moves to use a common set of environment variables throughout the repository. 
  This removes the cmaq_preprocess json files in preference to a .env file. 
  The `TARGET` environment variable is used to load the appropriate environment variable still.

  `setup_for_cmaq` now processes a single domain at a time which simplifies the whole process. 
  Running nested domains would likely require other changes throughout the codebase. 
  We now have a clean slate to add that feature if it was needed. ([#42](https://github.com/openmethane/openmethane/pull/42))
- Migrates to use the `wrf` directory for the WRF outputs and domains. ([#45](https://github.com/openmethane/openmethane/pull/45))

### 🆕 Features

- Move prior domain generation to this repository from openmethane-prior.

  Adds scripts to upload the prior domains to the CloudFlare R2 bucket (requires credentials).
  The domains are uploaded with the naming convention of domains/{name}/{version}/prior_domain_{name}_{version}.d01.nc.
  These files can then be retrieved by `openmethane-prior` in the same fashion as the input data. ([#31](https://github.com/openmethane/openmethane/pull/31))
- Adds a shell script for runnning tropomi ([#39](https://github.com/openmethane/openmethane/pull/39))
- Adds towncrier to manage the changelog of the project.

  This is a tool that helps automate the process of updating the changelog.
  See the documentation for adding changelogs in `changes/README.md`.
  The changelog is updated by running `towncrier` which is done automatically on tagged releases.

  This PR also adds a GitHub action to automate the process of updating the changelog on tagged releases
  and for bumping new releases. ([#44](https://github.com/openmethane/openmethane/pull/44))

### 🎉 Improvements

- Remove unused cmaq preprocessing configuration values.

  Namely:

  * templateDir
  * sufadj
  * nhoursPerRun
  * printFreqHours
  * mechCMAQ
  * prepareRunScripts
  * add_qsnow
  * forceUpdateMcip
  * forceUpdateICandBC
  * forceUpdateRunScipts
  * doCompress
  * compressScript
  * cctmExec
  * scripts.cctmRun
  * scripts.cmaqRun

  This also removes the CMAQ run scripts as they were also unused in this particular application and required a bunch of extra configuration.

  The forceUpdateXXX parameters were combined into a single forceUpdate flag.

  ([#29](https://github.com/openmethane/openmethane/pull/29))
- Add a parameter to specify the value of BTRIM,
  which is used to remove cells at the edge of the meteorology grid.

  For the full domain `5` is the default, 
  but for the 10x10 test grid this would leave no remaining cells so a value of 1 is used. ([#32](https://github.com/openmethane/openmethane/pull/32))
- Refactor to use a common function for running subprocesses.

  This improves the logging of subprocesses and allows for easier debugging of issues. ([#41](https://github.com/openmethane/openmethane/pull/41))
- Support the use of environment variables instead of command line arguments
  in `create_prior_domain.py`.

  Improved the flexibility of the upload domains script. ([#45](https://github.com/openmethane/openmethane/pull/45))


## openmethane 0.2.0 (2024-07-09)

### ⚠️ Breaking Changes

- Moves setup_for_cmaq script into the openmethane repo. 

  This aligns better with the other CMAQ preprocessing steps
  which are in this repo and are tightly coupled to the output from running setup_for_cmaq. ([#22](https://github.com/openmethane/openmethane/pull/22))

- Refactor the scripts that are in the repository into the scripts directory. ([#11](https://github.com/openmethane/openmethane/pull/11), [#15](https://github.com/openmethane/openmethane/pull/15))

### 🐛 Bug Fixes

- Removed the hand-rolled logging implementation in preference for the standard logger.
  ([#6](https://github.com/openmethane/openmethane/pull/6))

### 🎉 Improvements

- Verify and document the new approach to running OpenMethane on GADI.
  
  See `docs/nci.md` for more information about the required steps. ([#28](https://github.com/openmethane/openmethane/pull/28))

- Add an end-to-end test for running OpenMethane (`scripts/run-all.sh`).
  ([#25](https://github.com/openmethane/openmethane/pull/25))

- Images that are built and pass the testsuite are pushed to ECR for use by the AWS workflow.
  ([#21](https://github.com/openmethane/openmethane/pull/21))


- Dockerize the project and run via CI

  ([#10](https://github.com/openmethane/openmethane/pull/10), [#18](https://github.com/openmethane/openmethane/pull/18))

- Use the `TARGET` environment to specify the configuration used.

  Adds the concept of targets, defined using the `TARGET` env variable and the .env.${TARGET}` file.
  The parameters that can be stored in this file are located in `docs/parameters.md`.
  ([#7](https://github.com/openmethane/openmethane/pull/7))

- Add tests to capture/track the state of the fourdvar parameters

  ([#5](https://github.com/openmethane/openmethane/pull/10), [#18](https://github.com/openmethane/openmethane/pull/5))

## openmethane 0.1.0 (2024-08-01)

Initial state of the OpenMethane repository.