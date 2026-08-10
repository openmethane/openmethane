# Parameters

The following environment variables are configurable:

| Variable           | Type | Description                                                        | Default                                    |
|--------------------|------|--------------------------------------------------------------------|--------------------------------------------|
| DOMAIN_NAME        | str  | Defines the target domain                                          | aust10km                                   |
| DOMAIN_VERSION     | str  | Version of the target domain                                       | v1                                         |
| DOMAIN_MCIP_SUFFIX | str  | Suffix for the generated MCIP files                                | ${DOMAIN_NAME}_${DOMAIN_VERSION}           |
| START_DATE         | date | Start date of the run                                              | 2022-07-01                                 |
| END_DATE           | date | End date of the run (inclusive)                                    | 2022-07-30                                 |
| STORE_PATH         | str  | Full path to the branch-specific data.                             | N/A                                        |          
| EXPERIMENT         | str  | Name of the experiment being run                                   | openmethane                                |
| TEMPLATE_DIR       | str  | Path to the CMAQ template directory                                | {STORE_PATH}/templates                     |
| CMAQ_SOURCE_DIR    | str  | Path to the root of the CMAQ source directory                      | N/A                                        |
| MCIP_SOURCE_DIR    | str  | Path to the root MCIP source directory                             | N/A                                        |
| MET_DIR            | path | Output directory for the MCIP data                                 | N/A                                        |
| CTM_DIR            | path | Output directory for the CMAQ template files                       | N/A                                        |
| WRF_DIR            | path | Output directory for the WRF outputs (from setup-wrf)              | N/A                                        |
| GEO_DIR            | path | Directory containing the `geo_em.d??.nc` file (from setup-wrf)     | N/A                                        |
| CHK_PATH           | path | Directory to store CMAQ checkpoint files                           | {CMAQ_BASE}/chkpnt                         |
| OBS_FILE_GLOB      | str  | Glob string to match the observation files relative to {STORE_PATH} | "input/test_obs.pic.gz"                    |
| PRIOR_FILE         | path | Path to the concentration prior file                               | N/A                                        |
| CAMS_FILE          | path | Path to the CAMS CH4 emissions file                                | N/A                                        |
| ICON_FILE          | path | Path to ICON template file                                         | N/A                                        |
| BCON_FILE          | path | Path to BCON template file                                         | N/A                                        |
| EMIS_FILE          | path | Path to emissions files                                            | {CMAQ_BASE}/emissions/emis.<YYYY-MM-DD>.nc |
| FORCE_FILE         | path | Path to the template forcing file                                  | {CMAQ_BASE}/force/ADJ_FORCE.<YYYYMMDD>.nc  |
| ADJOINT_FWD        | path | Path to forward adjoint executable                                 | N/A                                        |
| ADJOINT_BWD        | path | Path to backward adjoint executable                                | N/A                                        |
| NUM_PROC_COLS      | int  | Number of processors to use for the columns                        | 1                                          |
| NUM_PROC_ROW       | int  | Number of processors to use for the rows                           | 1                                          |
| MAX_ITERATIONS     | int  | Maximum successful iterations performed by fourdvar                | 20                                         |
| LOG_LEVEL          | str  | Level of interest for logging. One of INFO, DEBUG, etc             | INFO                                       |
| LOG_FILE           | path | Path to where logs should be written, relative to {STORE_PATH}     | INFO                                       |


For values with a default of N/A an exception will be raised if
the environment variable is not defined.

`{CMAQ_BASE}` represents the directory that contains the CMAQ output (`$STORE_PATH/run-cmaq`).


## TropOMI data

The `scripts/obs_preprocess/fetch_tropomi.py` script finds granules with the
[Copernicus Data Space Ecosystem catalogue](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
and downloads them from the public `meeo-s5p` S3 bucket, which MEEO publish under the
[AWS Open Data Sponsorship Program](https://registry.opendata.aws/sentinel5p/).

Neither service requires credentials, so no environment variables need to be set.
Searching the CDSE catalogue is unauthenticated; only downloading from CDSE
itself would need a login, which is why the granules come from the bucket.
Requests to the bucket are sent unsigned, so any AWS credentials in the
environment are ignored.

The catalogue matches on each granule's swath footprint, so only granules
crossing the bounding box in the config file are downloaded.

Whichever product the catalogue holds for a date is the one fetched. It keeps a
single current product per orbit and deletes superseded ones, recording a
`DeletionCause` of `Reprocessed product`, so it serves reprocessed (`RPRO`)
products where ESA's full mission reprocessing replaced the originals — up to
2022-07-25 — and offline (`OFFL`) products from 2022-07-26 onwards. Nothing needs
to be configured to choose between them.

Near real time (`NRTI`) products are excluded, because they cover the same orbits
in much shorter granules and would put the same observations into the inversion
twice. Since two products for one orbit would do the same, `fetch_tropomi.py`
checks for that and fails rather than assuming the catalogue never returns them.

Products are catalogued from 2018-04-30 and lag acquisition by about 2 to 3 days,
so the most recent days are not yet available.

Granules are downloaded whole, since the bucket offers no server-side subsetting.
`tropomi_methane_preprocess.py` then drops the observations that fall outside the
model grid.

## CAMS Login
Used to fetch CAMS data during the cmaq_preprocess step.
 
This requires a CAMS account, which can be created at the ECMWF [Atmosphere Data Store](https://ads.atmosphere.copernicus.eu/).
