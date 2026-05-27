# Open Methane

Scripts for running the adjoint of the CMAQ model for methane emissions estimation

## Getting Started

### Requirements

The recommended way to run Open Methane is using
[docker](https://www.docker.com/), version 23 or later.

For development or running Open Methane locally, you will need:
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Running locally

The Open Methane prior can be installed from source into a virtual environment
with:

```bash
uv sync
```

### Docker

The recommended way to run Open Methane, is using the
[published Docker images](https://github.com/openmethane/openmethane/pkgs/container/openmethane).

If you need to make changes to the source code, you will need to build the
docker image locally.

> [!WARNING]
> Building the Open Methane docker image is currently not possible without
> access to the CMAQ-Adjoint repository. If this affects you, please create
> an issue or contact the team at inquiries@openmethane.org.

The docker container containing CMAQ, the adjoint model and the python
dependencies can be built locally. The required CMAQ-Adjoint docker image is
built via the
[openmethane/CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint)
repository and is hosted as a private image at
[ghcr.io/openmethane/cmaq](https://ghcr.io/openmethane/cmaq-adjoint).

Since the CMAQ-Adjoint image is not public, you will need to
[authenticate with the GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).
before building the openmethane image.

Once you have logged into the GitHub Container Registry, you can build the docker image with:

```shell
make build
```

## Configuration

The configuration is defined in `fourdvar.params` and the modules within that package.
The configuration is defined at import time.
A bulk of parameters are static, but some are dynamic and can be set via environment variables.

Some sensitive environment parameters are required to be set in a `.env` file.
These environment variables aren't checked into the repository for security reasons.
A useful starting point for this `.env` file is the `.env.example` file.

See `docs/parameters.md` for the full list of parameters that can be configured via environment variables.

### Targets

`fourdvar` can be run in different target environments.
These environments typically require different configuration,
particularly regarding the paths to the data and the CMAQ adjunct.

The target environment is defined by the `TARGET` environment variable (default=`nci`).
The value of `TARGET` is used to load a `.env.${TARGET}` file.
This `.env` file contains the target specific configuration values.

A `docker-test` target has been provided which uses locally tracked versions
of the required input data from the `openmethane-prior` and `setup-wrf` repositories.
This target is useful for testing and development.

## First Run

To run your first test case you will need to:



1: Run the cmaq preprocessing script (`scripts/cmaq_preprocess/run-cmaq-preprocess.sh`) to generate the
	necessary input files for the adjoint model. This script will run the following scripts in order:
 - `scripts/cmaq_preprocess/download_cams_input.py`
	Downloads the CAMS data for the specified date range and region
 - `scripts/cmaq_preprocess/setup_for_cmaq.py`
	Runs MCIP, ICON and BCON to generate the input date files for the CMAQ adjoint
 - `scripts/cmaq_preprocess/make_emis_template.py`
	Create the emission template file from the prior estimate
 - `scripts/cmaq_preprocess/make_template.py`
	Creates template files needed to for py4dvar to generate input files,
	Assumes that all the input files defined in cmaq_config (MET, emis, icon, etc) already exist
 - `scripts/cmaq_preprocess/make_prior.py`
	creates the prior estimate of the fluxes (and initial conditions if input_defn.inc_icon is True)
	includes modifiable parameters at the start of the file with descriptions.

The last three scripts can also be run with 
```bash
make prepare-templates
```

2: fetch the TropOMI data:
 - `scripts/obs_preprocess/fetch_tropomi.py -c config/obs_preprocess/config.{grid}.json -s {start_date} -e {end_date} {output_dir}`
	Downloads the TropOMI data for the specified date range and region.
	Requires a EarthData login. See the script for more details about how to set this up.
 
3: go to `scripts/obs_preprocess` and run one of:
 - `scripts/obs_preprocess/tropomi_methane_preprocess.py --source data/tropomi/*`
	process the downloaded TropOMI data into a format that can be used by `fourdvar`.

4: go to `tests/integration/fourdvar` and run:
 - `test_cost_verbose.py`
	runs the cost function logic with a random perturbation in the prior.
 - `test_grad_verbose.py`
	runs the gradient function logic with a random perturbation in the prior.

5: run the main code via `runscript.py`

## Running locally

For local testing and development, we recommend that the docker container is used.

The docker container assumes that the [openmethane-prior](https://github.com/openmethane/openmethane-prior) 
and [setup-wrf](https://github.com/openmethane/setup-wrf) repositories have been cloned locally 
(as `../openmethane-prior` and `../setup-wrf` respectively).
There are artifacts from these repos that are required to be run before running the adjoint model.

The docker container can be built and run with:

```shell
make start
```

This will drop you into a shell in the docker container.
From here you can run the scripts in the order above,
or use the following script to run the scripts in the correct order:

```shell
bash scripts/run-all.sh
```
### Download all domain data from the Cloudflare

The `scripts/upload-domains.sh` script checks if the local directory domain is 
synchronised with the target directory domain. If the local is not up to date
it is neccessary to download all domain data from the Cloudflare bucket with:

```bash
make sync-domains-from-cf
```

### PyCharm

Pycharm provides some support for using a 
[remote interpreter](https://www.jetbrains.com/help/pycharm/using-docker-as-a-remote-interpreter.html) 
in a docker container.
This feature is only available for PyCharm Professional.

The volumes may need to be adjusted to match the local paths for the openmethane-prior and setup-wrf repositories
as described above.
This will create a new docker container when running the scripts or tests.

This can be a bit flakey in PyCharm. 
Similar functionality can be achieved with VSCode in a likely more stable manner.

