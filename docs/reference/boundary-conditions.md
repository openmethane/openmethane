# Boundary conditions in the inversion

The methane flowing into the domain is set by the lateral boundary condition
(BCON), built from CAMS. Errors in it change the modelled columns everywhere
downwind, and an inversion that could only adjust emissions would push those
errors into the emissions. So the inversion also solves for corrections to the
boundary condition. These are nuisance variables: they are there to stop a
wrong inflow from contaminating the emission estimates, not to be reported.

## What is solved for

Each boundary unknown is an **offset in ppm added to the BCON field** that
CMAQ reads. The staged BCON (`BCON_FILE`, after the CAMS bias correction) is
the prior, so every offset's prior value is 0.

Each offset covers one *region* of the boundary, a set of perimeter cells and
layers, for one *control time step*. For each day of the run, the inversion
writes `{CMAQ_BASE}/bcon/BCON.<YYYYMMDD>.nc`: the staged BCON plus the
offsets. The forward and backward runs both read this file. The staged BCON
is never modified.

The gradient comes from `ADJ_LGRID_BC`, written by `ADJOINT_BWD`. It is the
sensitivity of the cost function to each BCON record, layer and perimeter cell,
in `CF/ppmV` ([CMAQ-Adjoint#33](https://github.com/openmethane/CMAQ-Adjoint/pull/33)).
Summing it over the cells and records of each region and step gives the
gradient for each offset. That sum is exactly the adjoint of adding the offset,
so the gradient is exact.

CMAQ interpolates linearly in time between BCON records. An offset that changes
between two control steps therefore ramps over one BCON interval rather than
jumping.

## Resolution

Errors in the CAMS boundary come from the weather, so the default resolution
follows synoptic scales:

| Axis | Default | Setting |
| --- | --- | --- |
| Along the boundary | segments of about 1000 km (about 100 cells at 10 km) | `BCON_SEGMENT_KM` |
| In time | steps of about 5 days | `BCON_STEP_DAYS` |
| In the vertical | 4 bands holding roughly equal air mass | `BCON_NBANDS` |

Equal-mass bands mean a 1 ppm offset in any band changes the column on inflow
by roughly the same amount. One uncertainty in ppm then means roughly the same
column uncertainty in every band. Band edges are placed at the layer interfaces
nearest the cumulative-mass quantiles of the model column, using the layer
thicknesses in `VGLVLS`.

Segments are cut along each edge (south, east, north, west), so no region
crosses a corner. Regions are numbered by edge, then segment along the edge,
then band from the surface up.

### Lengths that don't divide exactly

The perimeter and the run rarely divide into whole segments or steps.
`BCON_REMAINDER` chooses how the leftover is handled:

| Rule | Behaviour | 31 days in 5-day steps | 351 cells in 100-cell segments |
| --- | --- | --- | --- |
| `spread` (default) | The nearest whole number of pieces, sized as equally as possible | 5,5,5,5,5,6 | 87,88,88,88 |
| `end` | Full-length pieces plus one shorter piece at the end | 5,5,5,5,5,5,1 | 100,100,100,51 |

`spread` avoids short pieces, such as a 1-day step. A short piece has little
information from the observations, so its offset mostly stays at the prior.
Use `end` when step boundaries must fall on fixed dates. With `end`,
`make_bcon_map.py --min-fraction 0.5` merges a leftover shorter than half a
piece into the previous one.

A run shorter than a step gets one step covering the whole run.

## Uncertainty

`BCON_UNC` is the prior 1-sigma uncertainty of every offset, in ppm. The
default is 0.02 ppm (20 ppb), of the order of the CAMS background error.
Posterior offsets much larger than this suggest the uncertainty is too small.
Prior errors are uncorrelated between regions and steps.

## Bounds

The BCON CMAQ reads, staged BCON plus offset, must not go negative. Each
offset is added to every cell and record in its region and step, so this
reduces to one lower bound per offset: minus the smallest staged BCON value
it is added to, over every day of the run. The bound is applied whatever
`ALLOW_NEGATIVE_EMISSIONS` says, since that setting is about emissions. A
negative concentration is never physical.

The bound only stops CMAQ receiving negative input. It is the uncertainty that
keeps the offsets near CAMS. At the end of the inversion, the log reports how
many offsets finished on their bound. Many offsets on the bound suggest that
regions span too wide a range of concentrations.

## The boundary map file

The regions, steps and uncertainty are held in a netCDF map file. If
`BCON_MAP_FILE` is unset, `make_prior.py` builds one from the `BCON_*`
settings and saves it next to the prior as `bcon_map.nc`. To build one by hand,
for example to inspect it or edit it before making the prior:

```shell
python scripts/cmaq_preprocess/make_bcon_map.py --output bcon_map.nc \
    --segment-km 1000 --step-days 5 --nbands 4 --remainder spread --unc 0.02
```

The script prints the segment lengths along each edge and the step lengths.
Its other options are `--layer-bands 1,9,17,25` (explicit 1-based start
layers, overriding `--nbands`), `--wrap` (cut the perimeter as one loop,
across corners), and `--bcon-file`, `--start-date` and `--end-date`
(defaulting to `BCON_FILE`, `START_DATE` and `END_DATE`).

| Variable | Dimensions | Meaning |
| --- | --- | --- |
| `BCON_REGION` | `LAY, PERIM` | Region of each BCON cell, -1 for none (the four corners, which CMAQ never reads) |
| `STEP_START`, `STEP_END` | `STEP` | Start and end of each control step |
| `BCON_UNC` | `STEP, REGION` | Prior 1-sigma uncertainty of each offset, ppm |
| `REGION_EDGE` | `REGION` | 0 to 3 for S, E, N, W, -1 with `--wrap` |
| `REGION_SEGMENT`, `REGION_BAND` | `REGION` | Segment along the edge and vertical band |
| `REGION_NCELLS` | `REGION` | Number of perimeter cells |
| `REGION_PERIM_FIRST`, `REGION_PERIM_LAST` | `REGION` | First and last perimeter cell |
| `REGION_LAY_START`, `REGION_LAY_END` | `REGION` | First and last layer, 1-based |
| `REGION_LON`, `REGION_LAT` | `REGION` | Mean position of the region's cells, for plotting |

Only `BCON_REGION`, the step boundaries and `BCON_UNC` are used by the
inversion. The file can be edited, for example to raise `BCON_UNC` on one
edge or to redraw regions, and set as `BCON_MAP_FILE`. It is checked when the
prior is made:

- every cell except the corners is in a region;
- region numbers are contiguous;
- the steps are contiguous and cover exactly `START_DATE` to `END_DATE`;
- the shapes match the BCON file.

A map built for one period cannot be used for another.

The perimeter is laid out as in the I/O API `BNDARY3` format with `NTHIK = 1`:
south, east, north, west. Each side includes one corner: south and east at
their ends, north and west at their starts.

The pipeline writes one BCON file per day, and each is time-independent
(`TSTEP = 0`): a single record that holds for that whole day. Each day's record
belongs to the control step that contains the day, so with these files every
step must start and end at midnight, and `BCON_STEP_DAYS` must be a whole number
of days. A hand-edited map is checked for this when the prior is made.
