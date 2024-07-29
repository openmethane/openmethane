# The open methane workflow

## Repositories

1. **openmethane-prior** generates a first approximation for the locally resolved methane emissions for a given
domain. The repository is matched with downloadable input data so that it will run out of the box. In the example 
files provided, the methane emissions of various sectors in Australia, such as livestock, electricity or industry, 
are added. The output of this repository is a file with the estimated emissions for the specified domain.
2. The **setup_wrf** repository generates the scripts for the day's WRF run. The configuration 
describes where the various input files are located, where the output files should be stored, and how the WRF model should be run.
3. The **openmethane** repository runs the adjoint of the CMAQ model for methane emissions estimation. 

## Daily workflow 

The daily workflow is described in the Terraform script `main.tf`, which runs 
various containerised tasks using Docker images.

The daily workflow requires three Docker images that are based on
the three repositories described above. The images are loaded from 
the AWS Elastic Container Registry (ECR). 

The AWS batch jobs `wrf-run`, `prior-generate` and `cmaq_preprocess-fetch_domains`
are run in the parallel `Preprocess.
* `wrf-run` runs `scripts/run-wrf.sh` setup-wrf
* `prior-generate` runs `scripts/run.sh` in openmethane-prior
* `cmaq_preprocess-fetch_domains` runs `make fetch-domains` in `openmethane`

There is an error handler that directs to the `Notify Error` state in case of any error.



<img src="stepfunctions_graph.svg">

## Monthly workflow