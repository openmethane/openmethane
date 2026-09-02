
# TropOMI data

The `scripts/obs_preprocess/fetch_tropomi.py` script finds granules with the
[Copernicus Data Space Ecosystem catalogue](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
and downloads them from the public `meeo-s5p` S3 bucket, which MEEO publish under the
[AWS Open Data Sponsorship Program](https://registry.opendata.aws/sentinel5p/).

Neither service requires credentials, so no environment variables need to be
set. Searching the CDSE catalogue is unauthenticated, and requests to the
bucket are sent unsigned, so any AWS credentials in the environment are ignored.

The catalogue matches on each granule's swath footprint, so only granules
crossing the bounding box of the `DOMAIN_FILE` domain are downloaded.

Whichever product the catalogue holds for a date is the one fetched. It keeps a
single current product per orbit and deletes superseded ones, recording a
`DeletionCause` of `Reprocessed product`, so it serves reprocessed (`RPRO`)
products where ESA's full mission reprocessing replaced the originals — up to
2022-07-25 — and offline (`OFFL`) products from 2022-07-26 onwards. Nothing needs
to be configured to choose between them.

Near real time (`NRTI`) products are excluded, because they cover the same orbits
in much shorter granules and would put the same observations into the inversion
twice. Since two products for one orbit would do the same, `fetch_tropomi.py`
keeps only one per orbit, preferring the later processor version, and warns when it
has to choose.

Products are catalogued from 2018-04-30 and lag acquisition by about 2 to 3 days,
so the most recent days are not yet available.

Granules are downloaded whole, since the bucket offers no server-side subsetting.
`tropomi_methane_preprocess.py` then drops the observations that fall outside the
model grid, and filters them to `START_DATE` and `END_DATE`.

## The observation operator

`tropomi_methane_preprocess.py` does more than reformat the retrieval: it builds
the observation operator, which fourdvar then applies as a weighted sum over the
CMAQ concentration field plus a constant. The vertical part of that operator —
mapping the model onto the retrieval's pressure levels, applying the column
averaging kernel, and filling the part of the column above the CMAQ model top —
lives in `openmethane.obs_preprocess.column_operator`, which documents the
equations and the conventions. `tropomi_averaging_kernel_operator.md` in the
repository root records why the operator is built this way and what it replaced.
