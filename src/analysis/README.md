# purpose

This directory contains scripts and functions used for analysing
openmethane results and inputs. these have not been rigorously tested
and are included with even less warranty than openmethane. 

# Inventory

- analyse_iters.py: functions to read input/output from openmethane
  and generate diagnostics like the local enhancement
- model_top_drift/: diagnostics for the column drift in #248 -- how far a
  monthly run has moved from the CAMS field driving it, and where in the
  column it has moved. See the README in that directory.
