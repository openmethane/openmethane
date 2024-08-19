# The open methane workflow

## Repositories

1. **openmethane-prior** generates a first approximation for the locally resolved methane emissions for a given
domain. The repository is matched with downloadable input data so that it will run out of the box. In the example 
files provided, the methane emissions of various sectors in Australia, such as livestock, electricity or industry, 
are added. The output of this repository is a file with the estimated emissions for the specified domain.
2. The **setup_wrf** repository generates the scripts for the day's WRF run. The configuration 
describes where the various input files are located, where the output files should be stored, and how the WRF model should be run.
3. The **openmethane** repository processes the output from WRF into a format that CMAQ requires 
and runs the adjoint of the CMAQ model for methane emissions estimation
4. **om-infra** describes the AWS resources required to run the daily and monthly workflows.
## Daily workflow 

The daily workflow is described in the `om-infra` repository using Terraform, which runs 
various containerised tasks using Docker images.

The daily workflow requires three Docker images that are based on
the three repositories described above. The images are loaded from 
the AWS Elastic Container Registry (ECR). 

The `preprocess` step runs the following three AWS batch job in parallel:
* `wrf-run` runs `scripts/run-wrf.sh` in setup-wrf
* `prior-generate` runs `scripts/run.sh` in openmethane-prior
* `obs_preprocess-fetch_tropomi` pulls satellite data of methane emissions for the respective day.

The following jobs are then carried out in sequence:

* `cmaq_preprocess-run` generates the required input files for CMAQ from the prior and WRF outputs.
* `obs_preprocess-process_tropomi` generates an observation dataset from the tropomi input.
* `fourdvar-daily` generates a set of simulated observation - what the satellite 
should have seen.
* There is an error handler that directs to the `Notify Error` state in case of any error.





<img src="stepfunctions_graph.svg">

## Monthly workflow
