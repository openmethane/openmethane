# purpose

This directory contains scripts and functions used for analysing
openmethane results and inputs. these have not been rigorously tested
and are included with even less warranty than openmethane. 

# Inventory

- analyse_iters.py: functions to read input/output from openmethane
  and generate diagnostics like the local enhancement
- sounding_cache.py: flattens an archived monthly run's observations into one
  `.npz` of per-sounding arrays, keeping the whole column operator, so that
  questions about the residuals can be asked without re-streaming the run
- sounding_geometry.py: reconstructs the solar and viewing zenith angles that
  the observation files drop, from each sounding's timestamp and pixel corners
- aerosol_bias/: diagnostics for the aerosol dependence in #249 -- whether the
  observed column's dependence on retrieved aerosol scales with the length of
  the light path. See the README in that directory.
