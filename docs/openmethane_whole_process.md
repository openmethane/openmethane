## openmethane process

1. **openmethane-prior** generates a first approximation for the locally resolved methane emissions for a given
domain. The repository is matched with downloadable input data so that it will run out of the box. In the example 
files provided, the methane emissions of various sectors in Australia, such as livestock, electricity or industry, 
are added. The output of this repository is a file with the estimated emissions for the specified domain.
2. The **setup_wrf** repository generates the scripts for day's WRF run. The configuration 
describes where the various input files are located, where the output files should be stored, and how the WRF model should be run.
3. 