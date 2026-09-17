# purpose

This directory contains scripts and functions used for analysing
openmethane results and inputs. these have not been rigorously tested
and are included with even less warranty than openmethane. 

# Inventory

- analyse_iters.py: functions to read input/output from openmethane
  and generate diagnostics like the local enhancement
- aerosol_bias/: diagnostics for the aerosol dependence in #249 -- whether the
  observed column's dependence on retrieved aerosol scales with the length of
  the light path. See the README in that directory.
- model_top_drift/extract.py: builds the per-sounding cache the aerosol_bias
  diagnostics read, from an archived monthly run. The rest of that directory,
  the #248 diagnostics it was written for, arrives with #250.
