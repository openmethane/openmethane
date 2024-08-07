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