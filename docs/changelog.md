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