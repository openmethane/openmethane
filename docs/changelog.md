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

## openmethane v0.8.1 (2025-02-11)

No significant changes.


## openmethane v0.8.0 (2025-02-11)

### 🆕 Features

- Add methane alerts baseline and detection ([#131](https://github.com/openmethane/openmethane/pulls/131))


## openmethane v0.7.1 (2025-02-02)

### 🐛 Bug Fixes

- Fix bug in cmaq_preprocess when mcip folder is loaded from archive without wrf folder ([#130](https://github.com/openmethane/openmethane/pulls/130))


## openmethane v0.7.0 (2025-01-29)

### 🎉 Improvements

- Add "daily" sync type to sync a single daily folder during daily reprocessing ([#120](https://github.com/openmethane/openmethane/pulls/120))
- Improving bias correction ([#129](https://github.com/openmethane/openmethane/pulls/129))


## openmethane v0.6.6 (2025-01-15)

### 🎉 Improvements

- More updates to debug output and logging when running cmaq ([#124](https://github.com/openmethane/openmethane/pulls/124))


## openmethane v0.6.5 (2025-01-13)

### 🎉 Improvements

- Collect more debug output and logging in cmaq_preprocess ([#123](https://github.com/openmethane/openmethane/pulls/123))


## openmethane v0.6.4 (2025-01-13)

### 🐛 Bug Fixes

- Revert bwd wipeout change in cmaq_preprocess ([#122](https://github.com/openmethane/openmethane/pulls/122))


## openmethane v0.6.3 (2025-01-08)

No significant changes.


## openmethane v0.6.2 (2025-01-08)

### 🐛 Bug Fixes

- Fix OPENMETHANE_VERSION being incorrectly populated in container images ([#119](https://github.com/openmethane/openmethane/pulls/119))


## openmethane v0.6.1 (2025-01-08)

### 🐛 Bug Fixes

- Fix GitHub Actions script to support dash shell syntax ([#118](https://github.com/openmethane/openmethane/pulls/118))


## openmethane v0.6.0 (2025-01-08)

### 🎉 Improvements

- Make OPENMETHANE_VERSION environment variable available inside the container ([#108](https://github.com/openmethane/openmethane/pulls/108))
- Set top of model domain to top pressure level. Removes impact of
  unmodelled top of atmosphere on observation operator. Resolves #111. ([#112](https://github.com/openmethane/openmethane/pulls/112))
- Add scripts for running dockerised workflows locally ([#113](https://github.com/openmethane/openmethane/pulls/113))
- Add post-processing integration test ([#115](https://github.com/openmethane/openmethane/pulls/115))
- Adding regional bias correction ([#116](https://github.com/openmethane/openmethane/pulls/116))
- Improve monthly results format to adopt more of CF Conventions and make the file plottable in panoply ([#117](https://github.com/openmethane/openmethane/pulls/117))


## openmethane v0.5.3 (2024-11-21)

### 🐛 Bug Fixes

- Fix release images failing docker push because they have no valid tags ([#109](https://github.com/openmethane/openmethane/pulls/109))


## openmethane v0.5.2 (2024-11-21)

### 🐛 Bug Fixes

- Fix docker build to only push stable image tags when container tests pass.

### 🎉 Improvements

- Combine bump and release workflows into a simplified release process.
- Update container tagging strategy for latest and stable tags ([#103](https://github.com/openmethane/openmethane/pulls/103)).

### 🔧 Trivial/Internal Changes

- Small changes to GHA workflows to bring them inline with improvements made in other repos.


## openmethane v0.5.1 (2024-11-19)

### 🐛 Bug Fixes

- Update ADS API URLs from ads-beta to new production domain ads.atmosphere.copernicus.eu in CI/CD.


## openmethane v0.5.0 (2024-11-19)

### ⚠️ Breaking Changes

- `fetch_tropomi_data` now fails if any network requests fail.
  This is more robust than the previous behavior, which would silently ignore any failed requests leading
  to an incomplete or missing observational dataset. ([#89](https://github.com/openmethane/openmethane/pulls/89))

### 🆕 Features

- Add retry behaviour when fetching tropomi data
- Add `CHK_PATH` environment variable for defining the location of checkpoint files in CMAQ. ([#89](https://github.com/openmethane/openmethane/pulls/89))

### 🎉 Improvements

- Enhanced the verbosity of the minimiser to provide more information about the minimisation process. ([#84](https://github.com/openmethane/openmethane/pulls/84))
- Be more specific about the expected MCIP filename when running cmaq_preprocess ([#91](https://github.com/openmethane/openmethane/pulls/91))
- Add option to not recalculate the initial/boundary conditions during the CMAQ preprocessing step. ([#93](https://github.com/openmethane/openmethane/pulls/93))
- Automatically clean up the directory specified via the `CHK_PATH` environment variable when running via docker.
  This `CHK_PATH` directory is a scratch directory that is used to store temporary files. ([#98](https://github.com/openmethane/openmethane/pulls/98))

### 🐛 Bug Fixes

- Correct issue with multi-day monthly bias correction ([#83](https://github.com/openmethane/openmethane/pulls/83))
- Correct an error in the calculation of the chi-squared value on each cost-function evaluation. ([#84](https://github.com/openmethane/openmethane/pulls/84))
- The checkpoint directory is automatically created which running the model ([#94](https://github.com/openmethane/openmethane/pulls/94))
- Handle archiving log streams that are no longer available ([#97](https://github.com/openmethane/openmethane/pulls/97))


## openmethane v0.4.1 (2024-09-23)

### 🆕 Features

- Adds configuration for running the `aust-nsw` domain on Gadi
  using the results from an existing daily run. ([#79](https://github.com/openmethane/openmethane/pulls/79))

### 🎉 Improvements

- add calculation of posterior emissions for front end ([#71](https://github.com/openmethane/openmethane/pulls/71))


## openmethane v0.4.0 (2024-09-23)

### ⚠️ Breaking Changes

- Move `scripts/cmaq_preprocess/upload-domains.py` from Bash to Python ([#48](https://github.com/openmethane/openmethane/pulls/48))

### 🆕 Features

- Add archive script to copy the results fo the daily and monthly AWS workflows to S3

  This script is used to archive the daily and monthly outputs to AWS S3, in the case of both a successful
  run and a failure. The failed runs will use a prefix of `/failed/$DOMAIN_NAME/$EXECUTION_ID`,
  while the daily and monthly results are stored in `/results/$DOMAIN_NAME/daily/$YEAR/$MONTH/$DAY` and
  `/results/$DOMAIN_NAME/monthly/$YEAR/$MONTH`, respectively.

  These data can then be fetched from S3 and used for any local analysis or postmortems. ([#47](https://github.com/openmethane/openmethane/pulls/47))
- Add script which loads previous results of daily runs for the monthly run. ([#52](https://github.com/openmethane/openmethane/pulls/52))
- Move `scripts/archive.py` from Bash to Python, add more error handling, make it runnable when started from
  EventBridge. ([#53](https://github.com/openmethane/openmethane/pulls/53))
- Support loading observations from multiple input files using a glob.

  Adds new environment parameter, `TEMPLATE_DIR`, to set the directory containing the CMAQ template files
  and `OBS_FILE_GLOB` to enable override the path of the input observation file/s. ([#55](https://github.com/openmethane/openmethane/pulls/55))

### 🎉 Improvements

- Removed a duplicate global entry for the start/end date of a simulation
  and unified how parameters are named throughout `fourdvar`. ([#54](https://github.com/openmethane/openmethane/pulls/54))
- Load previous MCIP data when loading from the archive.
- Added support for using fourdvar date identifiers in the CMAQ preprocessing directories.
- Removed an ununsed `diurnal` parameter from `fourdvar`. ([#57](https://github.com/openmethane/openmethane/pulls/57))
- Log chi squared and bias values during the cost function execution ([#59](https://github.com/openmethane/openmethane/pulls/59))
- Don't clean up data for failed runs to make runs easily restartable ([#60](https://github.com/openmethane/openmethane/pulls/60))
- Added bias correction step for CAMS data.

  Fixes shock caused by discontinuity between CAMS free-running model
  and TROPOMI data. 
  the bias_correct_cams script should be included in the monthly
  workflow. It probably isn't necessary for the daily workflow provided
  we use local enhancement as our alerts algorithm. ([#63](https://github.com/openmethane/openmethane/pulls/63))
- Added CMAQ gradient test

  This addes a test for the CMAQ adjoint using a simple cost function of
  the sum of squares of model concentrations. the test uses the same
  logic as test_grad_finite_diff but is limited to the steps between
  model input and model output, i.e tests a shorter loop. Provided the
  run_model and run_adjoint are numerical no-ops this *should* be a
  direct test of the cmaq adjoint. ([#67](https://github.com/openmethane/openmethane/pulls/67))
- Print logs to stdout when CMAQ fails. ([#68](https://github.com/openmethane/openmethane/pulls/68))
- Added destriping function for TROPOMI data ([#72](https://github.com/openmethane/openmethane/pulls/72))

### 🐛 Bug Fixes

- Update the prior file location for the docker target ([#46](https://github.com/openmethane/openmethane/pulls/46))
- Update `scripts/load_from_archive.py` to use an inclusive end date
  which is a convention used throughout this project. ([#56](https://github.com/openmethane/openmethane/pulls/56))

### 📚 Improved Documentation

- Updated the diagrams for the `daily` workflow and added the `monthly` workflow. ([#58](https://github.com/openmethane/openmethane/pulls/58))

### 🔧 Trivial/Internal Changes

- [#64](https://github.com/openmethane/openmethane/pulls/64), [#66](https://github.com/openmethane/openmethane/pulls/66), [#68](https://github.com/openmethane/openmethane/pulls/68), [#69](https://github.com/openmethane/openmethane/pulls/69), [#73](https://github.com/openmethane/openmethane/pulls/73), [#74](https://github.com/openmethane/openmethane/pulls/74)


# ## openmethane v0.3.1 (2024-08-07)

No significant changes.


# ## openmethane v0.3.0 (2024-08-07)

### ⚠️ Breaking Changes

- Merge `sat_data` and `obs_preprocess` script directories. ([#33](https://github.com/openmethane/openmethane/pulls/33))
- Moves to use a common set of environment variables throughout the repository. 
  This removes the cmaq_preprocess json files in preference to a .env file. 
  The `TARGET` environment variable is used to load the appropriate environment variable still.

  `setup_for_cmaq` now processes a single domain at a time which simplifies the whole process. 
  Running nested domains would likely require other changes throughout the codebase. 
  We now have a clean slate to add that feature if it was needed. ([#42](https://github.com/openmethane/openmethane/pulls/42))
- Migrates to use the `wrf` directory for the WRF outputs and domains. ([#45](https://github.com/openmethane/openmethane/pulls/45))

### 🆕 Features

- Move prior domain generation to this repository from openmethane-prior.

  Adds scripts to upload the prior domains to the CloudFlare R2 bucket (requires credentials).
  The domains are uploaded with the naming convention of domains/{name}/{version}/prior_domain_{name}_{version}.d01.nc.
  These files can then be retrieved by `openmethane-prior` in the same fashion as the input data. ([#31](https://github.com/openmethane/openmethane/pulls/31))
- Adds a shell script for runnning tropomi ([#39](https://github.com/openmethane/openmethane/pulls/39))
- Adds towncrier to manage the changelog of the project.

  This is a tool that helps automate the process of updating the changelog.
  See the documentation for adding changelogs in `changes/README.md`.
  The changelog is updated by running `towncrier` which is done automatically on tagged releases.

  This PR also adds a GitHub action to automate the process of updating the changelog on tagged releases
  and for bumping new releases. ([#44](https://github.com/openmethane/openmethane/pulls/44))

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

  ([#29](https://github.com/openmethane/openmethane/pulls/29))
- Add a parameter to specify the value of BTRIM,
  which is used to remove cells at the edge of the meteorology grid.

  For the full domain `5` is the default, 
  but for the 10x10 test grid this would leave no remaining cells so a value of 1 is used. ([#32](https://github.com/openmethane/openmethane/pulls/32))
- Refactor to use a common function for running subprocesses.

  This improves the logging of subprocesses and allows for easier debugging of issues. ([#41](https://github.com/openmethane/openmethane/pulls/41))
- Support the use of environment variables instead of command line arguments
  in `create_prior_domain.py`.

  Improved the flexibility of the upload domains script. ([#45](https://github.com/openmethane/openmethane/pulls/45))


## openmethane 0.2.0 (2024-07-09)

### ⚠️ Breaking Changes

- Moves setup_for_cmaq script into the openmethane repo. 

  This aligns better with the other CMAQ preprocessing steps
  which are in this repo and are tightly coupled to the output from running setup_for_cmaq. ([#22](https://github.com/openmethane/openmethane/pulls/22))

- Refactor the scripts that are in the repository into the scripts directory. ([#11](https://github.com/openmethane/openmethane/pulls/11), [#15](https://github.com/openmethane/openmethane/pulls/15))

### 🐛 Bug Fixes

- Removed the hand-rolled logging implementation in preference for the standard logger.
  ([#6](https://github.com/openmethane/openmethane/pulls/6))

### 🎉 Improvements

- Verify and document the new approach to running OpenMethane on GADI.
  
  See `docs/nci.md` for more information about the required steps. ([#28](https://github.com/openmethane/openmethane/pulls/28))

- Add an end-to-end test for running OpenMethane (`scripts/run-all.sh`).
  ([#25](https://github.com/openmethane/openmethane/pulls/25))

- Images that are built and pass the testsuite are pushed to ECR for use by the AWS workflow.
  ([#21](https://github.com/openmethane/openmethane/pulls/21))


- Dockerize the project and run via CI

  ([#10](https://github.com/openmethane/openmethane/pulls/10), [#18](https://github.com/openmethane/openmethane/pulls/18))

- Use the `TARGET` environment to specify the configuration used.

  Adds the concept of targets, defined using the `TARGET` env variable and the .env.${TARGET}` file.
  The parameters that can be stored in this file are located in `docs/parameters.md`.
  ([#7](https://github.com/openmethane/openmethane/pulls/7))

- Add tests to capture/track the state of the fourdvar parameters

  ([#5](https://github.com/openmethane/openmethane/pulls/10), [#18](https://github.com/openmethane/openmethane/pulls/5))

## openmethane 0.1.0 (2024-08-01)

Initial state of the OpenMethane repository.