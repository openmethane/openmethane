# OpenMethane

Scripts for running the adjoint of the CMAQ model for methane emissions estimation

## Getting Started

To get started, you will need to make sure that [poetry](https://python-poetry.org/docs/) is installed.
The Open Methane can be installed from source into a virtual environment with:

```bash
make virtual-environment
```

NOTE: The CMAQ-adj model and the benchmark data are not included in the GitHub repository. 
You will need to obtain these from another source.

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

## First Run

To run your first test case you will need to:


1: Run the following scripts (in listed order):
 - `scripts/cmaq_preprocess/make_emis_template.py`
	Create the emission template file from the prior estimate
 - `scripts/cmaq_preprocess/make_template.py`
	Creates template files needed to for py4dvar to generate input files,
	Assumes that all the input files defined in cmaq_config (MET, emis, icon, etc) already exist
 - `scripts/cmaq_preprocess/make_prior.py`
	creates the prior estimate of the fluxes (and initial conditions if input_defn.inc_icon is True)
	includes modifiable parameters at the start of the file with descriptions.

2: fetch the TropOMI data:
 - `scripts/sat_data/fetch.py -c scripts/sat_data/config.{grid}.json -s {start_date} -e {end_date} {output_dir}`
	Downloads the TropOMI data for the specified date range and region.
	Requires a EarthData login. See the script for more details about how to set this up.
 
3: go to `scripts/obs_preprocess` and run one of:
 - `scripts/obs_preprocess/tropomi_methane_preprocess.py`
	process the downloaded TropOMI data into a format that can be used by `fourdvar`.

4: go to tests and run:
 - `test_cost_verbose.py`
	runs the cost function logic with a random perturbation in the prior.
 - test_grad_verbose.py`
	runs the gradient function logic with a random perturbation in the prior.

5: run the main code via `runscript.py`

## Running locally

For local testing and development, we recommend that the docker container is used.


The docker container assumes that the openmethane-prior and setup_wrf repositories have been cloned
locally (as `../openmethane-prior` and `../setup_wrf` respectively).
There are artifacts from these repos that are required to be run before running the adjoint model.

TODO: Document what steps are required

The docker container can be built and run with:

```shell
	make run
```

This will drop you into a shell in the docker container.
From here you can run the scripts in the order above,
or use the following make commands to run the scripts in the correct order:

```shell
	make prepare-templates
```

### PyCharm

Pycharm provides some support for using a 
[remote interpreter](https://www.jetbrains.com/help/pycharm/using-docker-as-a-remote-interpreter.html) 
in a docker container.
This feature is only available for PyCharm Professional.

The volumes may need to be adjusted to match the local paths for the openmethane-prior and setup_wrf repositories
as described above.
This will create a new docker container when running the scripts or tests.

This can be a bit flakey in PyCharm. 
Similar functionality can be achieved with VSCode in a likely more stable manner.

