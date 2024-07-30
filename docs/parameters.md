# Parameters

The following environment variables are configurable:

| Variable       | Type              | Description                                 | Default                                    |
|----------------|-------------------|---------------------------------------------|--------------------------------------------|
| TARGET         | str               | Defines the target environment              | nci                                        |
| DOMAIN_NAME    | str               | Defines the target domain                   | aust10km                                   |
| DOMAIN_VERSION | str               | Version of the target domain                | v1                                         |
| START_DATE     | date (YYYY-MM-DD) | Start date of the run                       | 2022-07-01                                 |
| END_DATE       | date (YYYY-MM-DD) | End date of the run                         | 2022-07-30                                 |
| STORE_PATH     | str               | Full path to the branch-specific data       |                                            |
| EXPERIMENT     | str               | Name of the experiment being run            | 202207_test                                |
| PRIOR_PATH     | str               | Path to the concentration prior file        | N/A                                        |
| MET_DIR        | str               | Path to the root MCIP directory             | N/A                                        |
| ICON_FILE      | str               | Path to ICON file generated in setup-wrf    | N/A                                        |
| BCON_FILE      | str               | Path to BCON file generated in setup-wrf    | N/A                                        |
| EMIS_FILE      | str               | Path to emissions files                     | {CMAQ_BASE}/emissions/emis.<YYYY-MM-DD>.nc |
| FORCE_FILE     | str               | Path to the template forcing file           | {CMAQ_BASE}/force/ADJ_FORCE.<YYYYMMDD>.nc  |
| ADJOINT_FWD    | str               | Path to forward adjoint executable          | N/A                                        |
| ADJOINT_BWD    | str               | Path to backward adjoint executable         | N/A                                        |
| NUM_PROC_COLS  | int               | Number of processors to use for the columns | 1                                          |
| NUM_PROC_ROW   | int               | Number of processors to use for the rows    | 1                                          |


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
 TODO
 Used to fetch CAMS data during the cmaq_preprocess step