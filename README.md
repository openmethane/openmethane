# OpenMethane

Scripts for running the adjoint of the CMAQ model for methane emissions estimation

## Getting Started

To get started, you will need to make sure that [poetry](https://python-poetry.org/docs/) is installed.
The Open Methane can be installed from source into a virtual environment with:

```bash
make virtual-environment
```

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
