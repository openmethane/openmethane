# Parameters

The following environment variables are configurable:

| Variable           | Type  | Description                                                         | Default                                    |
|--------------------|-------|---------------------------------------------------------------------|--------------------------------------------|
| DOMAIN_NAME        | str   | Defines the target domain                                           | aust10km                                   |
| DOMAIN_VERSION     | str   | Version of the target domain                                        | v1                                         |
| DOMAIN_MCIP_SUFFIX | str   | Suffix for the generated MCIP files                                 | ${DOMAIN_NAME}_${DOMAIN_VERSION}           |
| START_DATE         | date  | Start date of the run                                               | 2022-07-01                                 |
| END_DATE           | date  | End date of the run (inclusive)                                     | 2022-07-30                                 |
| STORE_PATH         | str   | Full path to the branch-specific data.                              | N/A                                        |          
| EXPERIMENT         | str   | Name of the experiment being run                                    | 202207_test                                |
| TEMPLATE_DIR       | str   | Path to the CMAQ template directory                                 | {STORE_PATH}/templates                    |
| CMAQ_SOURCE_DIR    | str   | Path to the root of the CMAQ source directory                       | N/A                                        |
| MCIP_SOURCE_DIR    | str   | Path to the root MCIP source directory                              | N/A                                        |
| MET_DIR            | path  | Output directory for the MCIP data                                  | N/A                                        |
| CTM_DIR            | path  | Output directory for the CMAQ template files                        | N/A                                        |
| WRF_DIR            | path  | Output directory for the WRF outputs (from setup-wrf)               | N/A                                        |
| GEO_DIR            | path  | Directory containing the `geo_em.d??.nc` file (from setup-wrf)      | N/A                                        |
| CHK_PATH            | path  | Directory to store CMAQ checkpoint files                            | {CMAQ_BASE}/chkpnt                         |
| OBS_FILE_GLOB      | str   | Glob string to match the observation files relative to {STORE_PATH} | "input/test_obs.pic.gz"                    |
| PRIOR_FILE         | path  | Path to the concentration prior file                                | N/A                                        |
| CAMS_FILE          | path  | Path to the CAMS CH4 emissions file                                 | N/A                                        |
| ICON_FILE          | path  | Path to ICON template file                                          | N/A                                        |
| BCON_FILE          | path  | Path to BCON template file                                          | N/A                                        |
| EMIS_FILE          | path  | Path to emissions files                                             | {CMAQ_BASE}/emissions/emis.<YYYY-MM-DD>.nc |
| FORCE_FILE         | path  | Path to the template forcing file                                   | {CMAQ_BASE}/force/ADJ_FORCE.<YYYYMMDD>.nc  |
| ADJOINT_FWD        | path  | Path to forward adjoint executable                                  | N/A                                        |
| ADJOINT_BWD        | path  | Path to backward adjoint executable                                 | N/A                                        |
| NUM_PROC_COLS      | int   | Number of processors to use for the columns                         | 1                                          |
| NUM_PROC_ROW       | int   | Number of processors to use for the rows                            | 1                                          |
| MAX_ITERATIONS     | int   | Maximum successful iterations performed by fourdvar                 | 20                                         |


For values with a default of N/A an exception will be raised if
the environment variable is not defined.

`{CMAQ_BASE}` represents the directory that contains the CMAQ output (`$STORE_PATH/run-cmaq`).


## EarthData Login

The `scripts/obs_preprocess/fetch_tropomi.py` script requires an EarthData login to download the TropOMI data
with permission to access the GES DISC data archive.
A tutorial for creating an account and accepting the licence agreements is available
[here](https://disc.gsfc.nasa.gov/earthdata-login).

Once you have a login, 
the `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables can added to the `.env` file.
These will be used by the `fetch_tropomi.py` script to authenticate with the GES DISC data archive.

## CAMS Login
Used to fetch CAMS data during the cmaq_preprocess step.
 
This requires a CAMS account, which can be created at the ECMWF [Atmosphere Data Store](https://ads.atmosphere.copernicus.eu/).
