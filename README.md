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


1: go to cmaq_preprocess and run (in listed order):
 - make_template.py
	creates template files needed to for py4dvar to generate input files,
	assumes that all the input files defined in cmaq_config (MET, emis, icon, etc) already exist
 - make_prior.py
	creates the prior estimate of the fluxes (and initial conditions if input_defn.inc_icon is True)
	includes modifiable parameters at the start of the file with descriptions.

2: go to obs_preprocess and run one of:
 - sample_point_preprocess.py
	creates a test set of instant, point source observations, with easy to edit values.
 - sample_column_preprocess.py
	creates a test single vertical column observation, with easy to edit values.

3: go to tests and run:
 - test_cost_verbose.py
	runs the cost function logic with a random perturbation in the prior.
 - test_grad_verbose.py
	runs the gradient function logic with a random perturbation in the prior.

4: run the main code via runscript.py