
# Domain of interest

Open Methane operates on a domain of interest, which defines the area that
will be modelled, and the size and orientation of grid cells to be modelled.

## Default domain: aust10km

Open Methane was designed to estimate methane emissions over all of Australia,
so the default domain, `aust10km`, covers the entire Australian land mass in
10km x 10km grid cells.

This domain can be fetched automatically from our data store by running the
openmethane-prior with the following .env settings:

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

1. Checkout the [setup-wrf repo](https://github.com/openmethane/setup-wrf)
  - See README.md for installation instructions / pre-requisites
2. Create a new folder in `setup-wrf/domains`, named after your new domain
3. Copy the following files from `domains/aust10km` into your domain:
  - `namelist.wps`
  - `namelist.wrf`
  - `add_remove_var.txt`
4. Update settings in `namelist.wps` to your area of interest (see below)
5. Update any settings in `namelist.wrf` to reflect changes in `namelist.wps`
6. Run `scripts/run-wrf.sh` (see `scripts/docker-e2e-daily.sh` in this repo for
   an example of how to run this using docker).
  - ensure you specify your new domain as `DOMAIN_NAME`
  - use any `START_DATE` as long as there is data available
7. Locate the following files in your data directory:
  - `wrf/{DOMAIN_NAME}/geo_em.d01.nc`
  - `mcip/{START_DATE}/d01/GRIDCRO2D_{DOMAIN_NAME}_v1`
8. Checkout the [openmethane-prior repo](https://github.com/openmethane/openmethane-prior)
  - See README.md for installation instructions / pre-requisites
9. Run `scripts/create_prior_domain.py`, supplying all required settings and
   paths to the two files from step 7.
10. The new domain should be created as `domain.{DOMAIN_NAME}.nc` in the folder
   specified as `--output-folder`.

### Domain area and settings

The location and shape of your domain must be specified using WRF's
["namelist.wps" configuration format](https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/wps.html#wps-namelist-variables).

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
