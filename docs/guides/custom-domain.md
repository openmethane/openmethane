# Creating a custom domain

A domain defines the area Open Methane will model, the grid it is divided into,
and the map projection that grid sits on. A domain is identified by
`DOMAIN_NAME` and `DOMAIN_VERSION`, and the same pair is used by this
repository and the prior.

Check whether an [existing domain](running-a-domain.md#1-choose-or-create-a-domain)
already covers your area before creating one. Existing domains are already
validated against WRF, MCIP and the prior, and building a new one is the most
involved part of setting up a run.

## Default domain: aust10km

Open Methane was designed to estimate methane emissions over all of Australia,
so the default domain, `aust10km`, covers the entire Australian land mass in
10km x 10km grid cells.

Its WRF geometry ships with this repository, in
`src/openmethane/wrf/domains/aust10km/v1.yaml`, and its files are fetched
automatically from our data store when a run uses the following settings:

```dotenv
DOMAIN_NAME=aust10km
DOMAIN_VERSION=v1
```

## Creating a custom domain

If you want to estimate emissions over a smaller area or with a higher
resolution (smaller grid cells), you will need to create your own domain of
interest. Domains must be compatible with WRF and MCIP open source tools, so
initial configuration happens through them.

Open Methane works best with a domain that shares the same projection as
`aust10km`, so the easiest way to get started is to create a copy of
`aust10km`.

A domain needs three files:

| File | Made by | Read by |
| --- | --- | --- |
| `src/openmethane/wrf/domains/{DOMAIN_NAME}/{DOMAIN_VERSION}.yaml` | You | The `wrf` command, for WRF's namelists |
| `geo_em.d01.nc` | WRF's geogrid | WPS, and MCIP |
| `domain.{DOMAIN_NAME}.nc` | openmethane-prior's `create_prior_domain.py` | The prior, and this repository |

> [!NOTE]
> Nothing in this repository runs geogrid yet, so for now a new domain's
> `geo_em.d01.nc` is made with [setup-wrf](https://github.com/openmethane/setup-wrf),
> where WRF used to run. The domain creation tool
> ([#298](https://github.com/openmethane/openmethane/issues/298)) will replace
> steps 2 to 4.

1. Copy `src/openmethane/wrf/domains/aust10km/v1.yaml` to
   `src/openmethane/wrf/domains/{DOMAIN_NAME}/v1.yaml`, and update its settings
   to your area of interest (see below). Each is a `namelist.wps` setting with
   `wrf_` in front.
2. Check out the [setup-wrf repo](https://github.com/openmethane/setup-wrf),
   and create a folder in `setup-wrf/domains` named after your domain.
3. Copy `namelist.wps`, `namelist.wrf` and `add_remove_var.txt` from
   `domains/aust10km` into it, and give `namelist.wps` the same settings as your
   YAML file.
4. Run setup-wrf's `scripts/run-wrf.sh` for your `DOMAIN_NAME` and any
   `START_DATE` with data available. It runs geogrid, since your domain isn't
   published, and leaves `wrf/{DOMAIN_NAME}/geo_em.d01.nc` in its data
   directory.
5. Build the `openmethane` image from your checkout, which now holds your YAML
   file, with `make build`, and run the WRF step and CMAQ preprocessing for one
   day with it (see [Using your domain](#using-your-domain)).
6. Locate `mcip/{START_DATE}/d01/GRIDCRO2D_{DOMAIN_NAME}_v1` in that day's data
   directory.
7. Check out the [openmethane-prior repo](https://github.com/openmethane/openmethane-prior)
  - See README.md for installation instructions / pre-requisites
8. Run `scripts/create_prior_domain.py`, supplying all required settings and
   paths to `geo_em.d01.nc` and `GRIDCRO2D`.
9. The new domain should be created as `domain.{DOMAIN_NAME}.nc` in the folder
   specified as `--output-folder`.

### Domain area and settings

The location and shape of your domain are
[`namelist.wps` settings](https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/wps.html#wps-namelist-variables),
written in the YAML file with `wrf_` in front of each name. The examples below
are in `namelist.wps` form.

Key settings are:
- projection
- grid cell size in x and y dimensions, in meters
- number of grid cells in x and y dimensions
- reference lon/lat
  - this is optional, by default the grid is centered on the projection center

#### Projection

In the following example (from the `aust10km` domain) we set up a Lambert
conformal conic projection with a center point in Australia.

The `ref_lat`/`ref_lon` coordinates represent the location which corresponds
to the `ref_x`/`ref_y` grid index coordinates. In this case `ref_x`/`ref_y` are
the center of the grid which is 467 x 443 cells.

```
 map_proj  =  'lambert',
 truelat1  = -15.,
 truelat2  = -40.,
 stand_lon = 133.302,
 ref_lat   = -27.644,
 ref_lon   = 133.302,
 ref_x     = 233.5,
 ref_y     = 221.5,
```

#### Grid

The `aust10km` grid has grid cells 10,000m x 10,000m, and is `467` cells across
and `443` cells tall.

```
 e_we = 467,
 e_sn = 443,
 dx   = 10000,
 dy   = 10000,
```

Note: when the domain is used to run MCIP, cells around the domains edge will be
removed to be used as boundary conditions. The number of cells in the boundary
is controlled using the `BTRIM` (boundary trim) environment variable.

In `aust10km`, boundary trim is set to `5`, which will be removed on both sides
of the domain. MCIP will also remove a single cell on either side as "boundary
thickness" (`NTHIK`) and one final cell when converting from staggered grid to
grid center coordinates.

The [CMAQ/MCIP documentation](https://github.com/USEPA/CMAQ/blob/17e5ca0f2dcbc0aecfeab11108732c4cebbd1cee/PREP/mcip/README.md?plain=1#L87)
describes this reduction of the domain as:

```
reduce the input meteorology domain by 2*BTRIM + 2*NTHIK + 1
```

The `BTRIM` value of `5` ends up reducing the grid size by `13` in both
dimensions, so keep this in mind when specifying your grid size to WRF. Our
final grid dimensions for `aust10km` are `454` x `430`.

> [!WARNING]
> On a small domain, the default trim can consume the entire grid. The `au-test`
> domain is only 10 x 10 cells, so it sets `BOUNDARY_TRIM=1`. Set
> `BOUNDARY_TRIM` to suit your grid size, not to the `aust10km` default.

## Using your domain

Once the domain file exists, the pipeline needs to be pointed at it:

- Set `DOMAIN_NAME` and `DOMAIN_VERSION` to match the names you used.
- Set `DOMAIN_FILE` to the path of the `domain.{DOMAIN_NAME}.nc` file produced by
  `create_prior_domain.py`. The workflow scripts expect it inside `STORE_PATH`.
- Set `BOUNDARY_TRIM` as discussed above.
- Run an image built from a checkout that holds your domain's YAML file, with
  `BUILD_LOCAL_DOCKER=true` or `OPENMETHANE_IMAGE=openmethane` after
  `make build`. The published image only knows the published domains.
- Put your `geo_em.d01.nc` at `${STORE_PATH}/wrf/${DOMAIN_NAME}/geo_em.d01.nc`.
  The `wrf` command uses a file it finds there, and otherwise downloads it from
  the data store, where a custom domain isn't. The end-to-end scripts give each
  day its own `STORE_PATH`, so for them this is
  `${DATA_ROOT}/daily/${DOMAIN_NAME}/${DOMAIN_VERSION}/${START_DATE}/wrf/${DOMAIN_NAME}/`,
  for every day.

Domain files for existing domains are served from the public data store at
`https://openmethane.s3.amazonaws.com/domains/{DOMAIN_NAME}/{DOMAIN_VERSION}/domain.{DOMAIN_NAME}.nc`,
which is where the end-to-end scripts fetch them from. A custom domain has to be
placed in the expected location manually prior to running workflows.

Publishing a domain there, so that it is served to everyone rather than kept
locally, is a maintainer step done by hand. Both `geo_em.d01.nc` and the
domain file from `create_prior_domain.py` belong under the domain's prefix, and
the YAML file is added to this repository in a pull request:

```shell
aws s3 sync data/domains/${DOMAIN_NAME}/${DOMAIN_VERSION} \
  s3://openmethane/domains/${DOMAIN_NAME}/${DOMAIN_VERSION}
```

This needs write access to the `openmethane` bucket in the production account,
and an `aws` CLI on `PATH` -- it is not a project dependency, so install it
separately.

Before committing to a long run, do a single day on the new domain and confirm
the MCIP output has the grid dimensions you expect. Grid geometry mistakes are
much cheaper to find at that point than after a month of daily runs.
