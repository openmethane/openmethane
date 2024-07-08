# Running on NCI

We have maintained support for running OpenMethane
on the National Computational Infrastructure (NCI) Gadi supercomputer.
The following instructions are for running OpenMethane on NCI.

There are a few structural differences between how services run on NCI and docker.
Where possible these differences result in differences in configuration (filepaths etc),
but one key difference is how NCI manages environments.
For Docker, all the required dependencies are bundled into the docker container,
but for NCI, the dependencies are managed by the user

## Getting Started

The project can be cloned from github to the NCI filesystem using:

```shell
git clone git@github.com:openmethane/openmethane.git
```

The configuration includes some references to the location of where the code has been cloned.

### Installing Poetry and Virtual environment

This project uses [Poetry](https://python-poetry.org/docs/) for managing the python dependencies.
On NCI, poetry needs to be installed using the [manual method](https://python-poetry.org/docs/#installing-manually)
in a user accessible location.
The NCI run scripts assume that Poetry is installed in the user's home directory (`~/poetry`),
but this could modified to support a shared location if needed.

```shell
# Use Python 3.11 to generate a venv where Poetry is installed
module load python3/3.11.7

export VENV_PATH=~/poetry
python3 -m venv $VENV_PATH
$VENV_PATH/bin/pip install -U pip setuptools
$VENV_PATH/bin/pip install poetry

# Opt for virtualenvs to be created in the project directory
poetry config virtualenvs.in-project true
```

To make sure that Poetry is available in the user's path, 
`$HOME/poetry/bin` has to be added to the user's path.

Once you have poetry installed and the repository cloned, you can install the dependencies using:

```shell
make virtual-environment
```

This will run `poetry install` and create a virtual environment in the project directory (`.venv`).
This command should be run after checking out a new branch to install any new dependencies.

The environment setup can be done by sourcing the `load_p4d_modules.sh` script.
The `load_p4d_modules.sh` scipt loads the modules used to build CMAQ,
adds Poetry to the user's shell if it hasn't already been and activates the project virtual environment.
This will also prepend the terminal prompt with `(openmethane-py3.11) ` if the virtual environment is active.

This is generally called during a job submission script, but can be run manually
`. load_p4d_modules.sh` if any local development is being performed.

### Additional required files

A `.env` file based on `.env.example` should be created in the `openmethane` directory.
The `TARGET` environment variable should be set to `nci` instead of `docker`.
Some additional EarthData credentials are required.

The WRF geometry files are required to run the OpenMethane pipeline.
These can be fetched using `make fetch-domains`,
which will download the `aust-test` and `aust10km` domains from [setup-wrf](https://github.com/openmethane/setup-wrf)
to `data/domains`.

## Running the test domain

To test the end to end functionality of the OpenMethane pipeline on NCI,
a simple run-all script has been provided (`scripts/submit-run-all.sh`).
This script runs the OpenMethane pipeline on a small test domain (~10x10 grid cells over a mine in NSW).

This should only take a few minutes to run and writes output to `/scratch/q90/pjr563/openmethane-test/data`
using some WRF output that has been checked into the repository.

```
bash scripts/submit-run-all.sh
```