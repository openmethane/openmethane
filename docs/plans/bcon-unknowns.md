# Plan: boundary-condition offsets as 4D-Var unknowns

Branch: `feat/bcon-unknowns`. Tracks openmethane/openmethane#272, and goes
further than it: #272 keeps the fixed 8-region layout, this plan makes the
spatial and temporal resolution user-configurable. Depends on
openmethane/CMAQ-Adjoint#33 (`ADJ_LGRID_BC`).

## Goal

Replace the boundary *flux* unknowns with boundary *concentration offsets*:

- The control vector's `bcon` term becomes an additive offset, in ppm, on the
  BCON field that CMAQ reads (`BNDY_GASC_1`). The BCON built from CAMS (after
  the #254 bias correction) is the prior, so the prior offset is **0**.
- Remove the current approach of injecting the `bcon` term as emissions into
  every layer of the ring of edge cells.
- The user sets the offset's spatial resolution (along the perimeter and in
  the vertical), its temporal resolution, and its prior uncertainty.
- The gradient comes from `ADJ_LGRID_BC`, the sensitivity of the cost to each
  BCON record, layer and perimeter cell.

## Background: what the code does now

| place | current behaviour |
|---|---|
| `transfunc/prepare_model.py` | Expands `PhysicalData.bcon[spc]` (`nstep_bcon × 8`: SL, SH, EL, EH, NL, NH, WL, WH, split at `bcon_up_lay`) onto the edge cells of the emission array, converted from ppm/s to mol/s with `get_unit_convert_bcon`. Asserts `bcon_region == 8`. |
| `transfunc/map_sense.py` | Sums the emission sensitivity over the same edge cells to get the `bcon` gradient. |
| `datadef/abstract/_physical_abstract_data.py` | Holds `bcon_region`, `tsec_bcon`, `nstep_bcon`, `bcon_up_lay`, `bcon_unc`; archives/reads a `bcon` group with dims `TSTEP × BCON` and attrs `UP_LAY`, `TSEC`. |
| `transfunc/condition.py`, `uncondition.py` | Treat `bcon` as a flat block of `nstep_bcon × bcon_region` per species, scaled by `bcon_unc`. No change of shape needed beyond the region count. |
| `user_driver.py::minim` | Bounds: emissions ≥ 0, `bcon` unbounded, assumes `bcon` is the tail of the vector. |
| `scripts/cmaq_preprocess/make_prior.py` | Hard-codes `bcon_up_lay = 15`, `bcon_regions = 8`, `bcon_tsec = "single"`, `bcon_unc = 1e-9` ppm/s. |
| `util/cmaq_handle.py` | `BNDY_*` all point at `cmaq_config.bcon_file` (`BCON_FILE`, per day in `docker`, a single time-independent profile in `docker-test`). |
| `Dockerfile` | `cmaq-adjoint:2.0.1`, which has no `ADJ_LGRID_BC`. |

## Design

### The control variable

For each species, `PhysicalData.bcon[spc]` stays a 2-D array
`(nstep_bcon, nregion_bcon)` in **ppm**, so `condition`, `uncondition`, the
archive layout and the optimiser see the same shape class as today.

What changes is the meaning of both axes. Neither is assumed to be uniform:
regions need not be the same size and time steps need not be the same
length, because a resolution of choice (e.g. 100 cells, 5 days) will rarely
divide the perimeter or the run exactly. Both mappings are explicit and
stored with the prior, in a **boundary map file** (see "The boundary map
file" below):

- `BCON_REGION[LAY, PERIM]`: the region index (0 … `nregion_bcon − 1`) for
  each layer and perimeter cell of the BCON file, or −1 for cells in no
  region (the four corners, which advection never reads). Regions may have
  any number of cells.
- `STEP_START[nstep_bcon]`, `STEP_END[nstep_bcon]`: the start and end of each
  control time step (contiguous, covering the run). Steps may have any
  length, e.g. six 5-day steps and one 1-day step for a 31-day month.

The mapping from BCON records to control steps is computed from the record
times and these step boundaries. Storing the maps, rather than rebuilding
them from parameters in several places, means `prepare_model`, `map_sense`
and the bound calculation cannot disagree about them, and a user can
hand-craft any layout (for example, splitting an edge where it crosses the
coast). This replaces the single `TSEC` attribute and the `tsec_bcon`
parameter.

### The operator E and its adjoint

Write the offset expansion as a linear operator E: control → BCON-shaped
field `(TSTEP_bcon, LAY, PERIM)` for one day's BCON file.

- **Forward (`prepare_model`):** for each BCON record `r` of day `d`, find its
  control step `k(r)`; then `BCON_d[r, l, p] = BCON_base[r, l, p] +
  x[k(r), region[l, p]]` (0 where region = −1).
- **Adjoint (`map_sense`):** `g[k, j] += Σ ADJ_LGRID_BC_d[r, l, p]` over all
  `r` with `k(r) = k` and `(l, p)` with `region[l, p] = j`, summed over days.

The offset is constant within a control step on the BCON *records*. CMAQ
interpolates linearly between records, so near a control-step boundary the
offset the model sees ramps over one BCON interval. That is fine: E is
applied and differentiated on records, which is exactly what
`ADJ_LGRID_BC` is the sensitivity to, so the gradient is exact for the
operator as implemented.

**Shared records between days.** With per-day BCON files each day's file has
its own 00:00 and 24:00 records, and the 24:00 record of day *d* and the 00:00
record of day *d+1* are the same instant in different files. Each per-day
file gets its own E, and its sensitivity is mapped back with its own Eᵀ, so
the pair stays consistent; the record time decides `k(r)` (rule: a record at
time *t* belongs to the control step containing *t*, with the run's final
instant belonging to the last step).

**Time-independent BCON** (`TSTEP = 0`, as in `docker-test`'s
`template_bcon_profile_CH4only_d01.nc`): a single record applies to the whole
run, so only `nstep_bcon = 1` is meaningful. Validate this in
`make_prior`/`from_file` and raise a clear error otherwise.

### Units and uncertainty

- `PhysicalData.bcon`: ppm (the BCON file is ppmV).
- `ADJ_LGRID_BC`: CF/ppmV, so `PhysicalAdjointData.bcon` is CF/ppm with no
  conversion. Delete both `get_unit_convert_bcon` functions.
- `bcon_unc`: 1-σ uncertainty in ppm, per element of the `bcon` array. Prior
  errors stay uncorrelated (diagonal B), as now; correlation between regions
  or time steps is a possible follow-up (it would go into `condition`/
  `uncondition` as a square-root covariance, not into E).
- A prior file with the old ppm/s `bcon` group must be rejected: add a
  `units = "ppm"` attribute to the `bcon` group and check it in `from_file`.

### Bounds on the offset

The boundary concentration CMAQ reads must not go negative:
`BCON_base[r, l, p] + x[k, j] ≥ 0` for every record `r` in step `k` and every
cell `(l, p)` in region `j`, on every day. Because `x[k, j]` is one number
added to all of those cells, the constraint collapses to a simple lower bound
on each offset:

    x[k, j] ≥ −m[k, j],   m[k, j] = min BCON_base[r, l, p] over r ∈ k, region[l, p] = j, all days

L-BFGS-B works on the preconditioned unknowns `u = x / σ` (`σ = bcon_unc`),
so the bound passed to the minimiser is `u[k, j] ≥ −m[k, j] / σ[k, j]`, with
no upper bound. Since `m > 0`, the prior (`u = 0`) is strictly feasible.

- Compute `m` once, from the same staged (bias-corrected) base BCON files that
  `prepare_model` adds to, with a helper `offset_lower_bound(...)` in
  `bcon_map.py` that reuses the region map and record-to-step mapping, so it
  applies exactly the same E. Cells with region −1 are excluded.
- The bound applies **always**, also when `allow_negative_emissions` is true:
  that flag is about emissions, whereas a negative concentration is
  unphysical regardless. So `minim` always passes bounds; with negative
  emissions allowed the emission entries get `(None, None)`.
- The bound is on the *total* concentration, so it does not stop the offset
  pulling the boundary well below CAMS. That is the job of `BCON_UNC`; the
  bound only stops CMAQ receiving negative input.

### Choosing the resolution

The offsets correct errors in the CAMS boundary, and those errors are set by
weather systems. So the defaults follow synoptic scales:

- **Along the boundary: ~1000 km segments**, i.e. ~100 cells at 10 km.
- **In time: ~5-day steps.**
- **In the vertical: 4 bands holding roughly equal air mass.** Each band
  then has roughly equal weight in the column integral, so a 1 ppm offset in
  any band changes XCH4 on inflow by roughly the same amount, and one
  `BCON_UNC` in ppm means roughly the same column uncertainty in every band.

For a 31-day month on a perimeter of a few thousand cells this gives
O(30) segments × 4 bands × 7 steps ≈ 1000 unknowns, small next to the
emission unknowns.

### Lengths that don't divide exactly

Neither the perimeter nor the run will usually divide into whole segments or
steps. The helper offers two rules, chosen with `--remainder`:

- **`end`**: full-length pieces plus one shorter piece at the end, e.g. 31
  days → 5,5,5,5,5,5,1; an edge of 351 cells → 100,100,100,51.
- **`spread`**: the nearest whole number of pieces (rounding half up), sized
  as equally as possible, e.g. 31 days → 5,5,5,5,5,6; 351 cells →
  87,88,88,88.

`spread` is the recommended default: a 1-day step or a 10-cell segment is
weakly constrained by the observations and its offset is mostly prior,
which is harmless but wastes unknowns, and with `end` a remainder that is a
small fraction of the target length can be noisy. `end` is there for when
step boundaries must line up with fixed dates. With `end`, a remainder
below a set fraction of the target (`--min-fraction`, default 0, i.e. keep
every remainder) is merged into the previous piece.

**Decided:** `spread` is the default.

Rules for each axis:

- **Time.** Step boundaries are snapped to day boundaries when the step
  length is a whole number of days (always true for the defaults), and must
  otherwise fall on BCON record times. Records are assigned to steps by time
  as described above. Steps are computed over the run from `START_DATE` to
  `END_DATE`.
- **Along the boundary.** Segments are cut per edge, S, E, N, W, so a region
  never wraps a corner (edges usually see different inflow regimes). Segment
  length is given in km and converted to cells with `XCELL`/`YCELL`. An option
  `--wrap` cuts the whole perimeter continuously instead, for anyone who wants
  segments to cross corners.
- **In the vertical.** Band edges are chosen from the layer mass profile so
  each band holds as close to 1/N of the model column mass as layer
  boundaries allow, i.e. band edges at the layer interfaces nearest to the
  cumulative-mass quantiles. Use the layers' Δσ from `VGLVLS` (proportional
  to mass for CMAQ's σ-p coordinate; above `VGTOP` is outside the model and
  not counted). `--layer-bands 1,9,17,25` overrides this with explicit band
  start layers.

### The boundary map file

A new script, `scripts/cmaq_preprocess/make_bcon_map.py`, writes the map file
from the domain's BCON file (for `NROWS`, `NCOLS`, `NLAYS`, `VGLVLS`,
`XCELL`, `YCELL`) and the run dates:

```
make_bcon_map.py --bcon-file BCON.nc --start 2024-10-01 --end 2024-10-31 \
    --segment-km 1000 --step-days 5 --nbands 4 --remainder spread \
    --unc 0.02 --output bcon_map.nc
```

It writes a netCDF file with:

| variable | dims | meaning |
|---|---|---|
| `BCON_REGION` | `LAY, PERIM` | region index per cell, −1 for corners |
| `STEP_START`, `STEP_END` | `STEP` | step boundaries (CF time units) |
| `BCON_UNC` | `STEP, REGION` | prior 1-σ in ppm |
| `REGION_EDGE` | `REGION` | 0–3 for S, E, N, W (−1 with `--wrap`) |
| `REGION_PERIM_FIRST`, `REGION_PERIM_LAST` | `REGION` | first and last perimeter cell |
| `REGION_SEGMENT`, `REGION_BAND`, `REGION_NCELLS` | `REGION` | segment, band, number of perimeter cells |
| `REGION_LAY_START`, `REGION_LAY_END` | `REGION` | layer range |
| `REGION_LON`, `REGION_LAT` | `REGION` | segment midpoint, for plots |

plus attributes recording the arguments used. The descriptive variables are
there for plotting and reading results; only `BCON_REGION`, the step
boundaries and `BCON_UNC` are used by the inversion. A user can edit the
file (e.g. raise `BCON_UNC` on one edge, or redraw regions) and the
inversion takes it as given, after checking that it is consistent: every
non-corner cell is in exactly one region, region indices are contiguous,
steps are contiguous and cover the run, and the shapes match the BCON file.

Regions are numbered edge-major in the I/O API perimeter order (S, E, N, W),
then segment along the edge, then vertical band from the surface up. The
perimeter layout for `NTHIK = 1` is S: `NCOLS+1` cells, E: `NROWS+1`, N:
`NCOLS+1`, W: `NROWS+1`, each edge including one corner; corner cells get −1.

### User configuration

`make_prior.py` currently hard-codes everything. It now reads the map file:

| variable | meaning | default |
|---|---|---|
| `BCON_MAP_FILE` | Path to the boundary map file. If unset, `make_prior.py` calls the map builder with the defaults below and writes the map next to the prior. | unset |
| `BCON_SEGMENT_KM` | Target segment length along the boundary | `1000` |
| `BCON_STEP_DAYS` | Target control step length in days | `5` |
| `BCON_NBANDS` | Number of equal-mass vertical bands | `4` |
| `BCON_REMAINDER` | `spread` or `end` | `spread` |
| `BCON_UNC` | Prior 1-σ offset uncertainty in ppm, all regions | `0.02` (20 ppb) |

All are documented in `docs/reference/parameters.md`. The old 8-region,
single-step layout can still be built (`--segment-km` larger than any edge,
`--step-days` ≥ run length, `--layer-bands 1,16`), e.g. to compare with
#272.

### Files and wiring

1. **Image.** Bump `Dockerfile` to the CMAQ-Adjoint release containing #33.
2. **`params/cmaq_config.py`.** Add `bcon_sense_file`
   (`BC.LGRID.bwd_CH4only.<YYYYMMDD>.nc` in the run's output dir), and a
   per-day `bcon_run_file` that the forward and backward runs read
   (e.g. `BCON.<YYYYMMDD>.nc` in the run dir, never in the staged CTM dir).
3. **`util/cmaq_handle.py`.** `BNDY_GASC_1`/`BNDY_*` → `bcon_run_file` for
   that day (both fwd and bwd, since the backward run replays advection);
   set `ADJ_LGRID_BC` → `bcon_sense_file` in the bwd env.
4. **`util/cmaq_io_files.py`.** Add `ModelInputData["bcon.<YYYYMMDD>"]`
   (template: the day's base BCON, `cmaq_config.bcon_file`) and
   `SensitivityData["bcon.<YYYYMMDD>"]` (template: a new
   `template_defn.sense_bcon`, made in `make_template.py` by copying the
   base BCON header). Check `SensitivityData.get_vector` and
   `create_from_ModelInputData` only select `emis.*` keys (they do now).
5. **`params/template_defn.py`, `scripts/cmaq_preprocess/make_template.py`.**
   Produce `sense_bcon`. `ModelInputData` must write the BCON copies; check
   that `ModelInputData.create_new` handles a non-emission file key with the
   same "add to template" convention, or add an explicit path.
6. **`datadef/abstract/_physical_abstract_data.py`.** Replace `bcon_up_lay`
   with `bcon_region_map` (the `LAY × PERIM` array) and `tsec_bcon` with
   `bcon_step_start`/`bcon_step_end`; keep `bcon_region` as the region count,
   `nstep_bcon`, `bcon_unc`. Archive/read the map and step boundaries in the
   `bcon` group (same variable names as the map file), plus `units`. Validate
   them against the BCON file's `NLAYS`, `NROWS`, `NCOLS` and the run dates.
   The archived posterior then carries everything needed to plot it.
7. **New module `src/openmethane/bcon_map.py`** (shared by the map script and
   fourdvar) holding pure functions:
   - `split_length(n, target, remainder, min_fraction)` → piece lengths, used
     for both segments and steps;
   - `equal_mass_bands(vglvls, nbands)` → band start layers;
   - `build_region_map(...)`, `build_steps(...)`, `validate_map(...)`;
   - `record_steps(record_times, step_start, step_end)` → `k(r)`;
   - `expand(x, region_map, rec_step)` (E),
     `collapse(field, region_map, rec_step, nregion, nstep)` (Eᵀ) and
     `offset_lower_bound(...)`.
   No I/O, so they can be unit-tested directly.
7a. **New script `scripts/cmaq_preprocess/make_bcon_map.py`**: a thin CLI
   over the functions above that reads the BCON header and writes the map
   file. Add it to `docs/reference/scripts.md`.
8. **`transfunc/prepare_model.py`.** Delete the ring-flux block and
   `get_unit_convert_bcon`. Emission handling is unchanged. For each day,
   read the base BCON, add `expand(...)`, and pass it as
   `model_input_args["bcon.<YYYYMMDD>"]`.
9. **`transfunc/map_sense.py`.** Delete the emission-sensitivity slicing for
   `bcon` and `get_unit_convert_bcon`. For each day, read
   `ADJ_LGRID_BC` and accumulate `collapse(...)` into `bcon_dict`.
10. **`user_driver.py::minim`.** Build the bounds from the vector layout
    (`condition` order: icon?, emis, bcon per species), not by assuming
    `bcon` is the tail. The boundary condition is a concentration, so the
    *total* BCON, base + offset, must stay ≥ 0 (see "Bounds on the offset"
    below). The offset itself may be negative, down to minus the smallest
    base concentration it is added to.
11. **`scripts/cmaq_preprocess/make_prior.py`.** Read `BCON_MAP_FILE`, or
    build the map with the `BCON_*` defaults if it is unset; validate it; copy
    the map, step boundaries and `BCON_UNC` into the prior's `bcon` group in
    ppm, with prior offsets 0.
12. **`cmaq_preprocess/bias.py`.** `calculate_mean_obs` runs
    `PhysicalData → ModelInputData`, so it will now write BCON copies. Check
    that it uses the base BCON as written by `correct_icon_bcon`, and that the
    zero offset leaves it unchanged. `correct_icon_bcon` keeps modifying only
    the staged base file.
13. **Callers that read `bcon`:** `src/analysis/analyse_iters.py`,
    `tests/unit/fourdvar/transfunc/test_uncondition.py`,
    `tests/integration/cmaq_preprocess/test_run_prior.py`. Update for the new
    shape/attrs.
14. **Archive / outputs.** The posterior offset appears in
    `posterior-multipliers.nc`'s `bcon` group. Optionally also write the
    posterior offset expanded onto the BCON grid for one day, as a diagnostic.
    Archive `ADJ_LGRID_BC` with the other sensitivities.

## Tests

- **E/Eᵀ dot-product test** (unit, pure numpy): `⟨E x, y⟩ = ⟨x, Eᵀ y⟩` for
  random `x`, `y`, several layouts (1 × 1 band, 8 regions, 3 segments per edge
  × 3 bands, a hand-made map) and time layouts (single, daily, per-record,
  time-independent BCON).
- **Splitting:** `split_length` for both rules, e.g. 31 days by 5 →
  `end` 5,5,5,5,5,5,1 and `spread` 5,5,5,5,5,6; exact division gives equal
  pieces under both rules; pieces always sum to the total; a remainder below
  `min_fraction` is merged; a target longer than the total gives one piece.
- **Equal-mass bands:** on a synthetic `VGLVLS`, each band's mass is within
  one layer's mass of 1/N of the column; on the real test-domain levels, 4
  bands are printed in the test output for a sanity check.
- **Region map test:** perimeter indices match CMAQ's S, E, N, W order, corners
  are −1, every non-corner cell is in exactly one region, regions never cross
  a corner unless `--wrap`, and the old-layout options reproduce today's 8
  regions cell for cell (compare against the old `prepare_model` slicing
  applied to a test array).
- **Map validation:** a map with a gap, an overlap, a non-contiguous region
  index, steps that don't cover the run, or the wrong shape is rejected.
- **Record-to-step mapping:** 24:00 / 00:00 duplicates across days, uneven
  steps (a 1-day step after 5-day ones), run end on a step boundary,
  `TSTEP = 0` BCON with `nstep_bcon > 1` rejected.
- **Map script:** `make_bcon_map.py` on the test-domain BCON produces a file
  that `make_prior.py` accepts (regression fixture).
- **Offset bounds:** `offset_lower_bound` gives `−min` of the base over each
  region and step on a synthetic BCON with known minima (including a minimum
  on a 24:00 record and on a day other than the first); `minim`'s bounds
  vector lines up with `condition`'s layout for emis + bcon, with and without
  `allow_negative_emissions`; at the bound, `prepare_model`'s BCON has a
  minimum of exactly 0 and nowhere below.
- **Prior file:** round trip `PhysicalData.archive` → `from_file`; old-units
  file rejected.
- **Gradient check** (Docker, test domain): perturb one region's offset by δ,
  run forward, compare ΔJ with `g · δ` for a couple of δ (expect the same
  convergence with δ as CMAQ-Adjoint#33's finite-difference check).
- **Zero offset is a no-op:** the forward model with the prior gives the same
  concentrations as today's model with `bcon_unc` frozen (bit-identical
  `CONC` when the per-day BCON copy equals the base).
- `make test-regen`; review the fixture diffs.

## Docs and changelog

- `docs/reference/parameters.md`: the new `BCON_*` variables, and that the
  boundary uncertainty is now in ppm.
- `docs/reference/outputs.md`: the `bcon` group's new meaning and
  `BCON_REGION`; the archived `ADJ_LGRID_BC`.
- `docs/reference/scripts.md`: the new `make_bcon_map.py`, and
  `make_prior.py`'s use of the map file.
- A guide section (`docs/guides/`) on choosing the boundary resolution: the
  synoptic-scale defaults, the two remainder rules, and how to edit a map
  file by hand.
- A short explanation in the methodology docs of the offset, E and Eᵀ, and
  the linear-in-time ramp at control-step boundaries.
- `changelog/<PR>.breaking.md`: previously the boundary term was a flux added
  to edge cells in ppm/s with 8 fixed regions; now it is a ppm offset on BCON
  with configurable regions/time steps; old prior files are rejected and must
  be regenerated with `make_prior.py`. Note: posterior emissions differ.
- Separate `feature` fragment for the configurable resolution.

## Order of work

1. Bump the image; wire `ADJ_LGRID_BC` and the per-day BCON run file through
   `cmaq_config`, `cmaq_handle`, `cmaq_io_files` with a zero offset. Check
   the fwd/bwd runs still match and the sensitivity file appears.
2. `bcon_map.py`: splitting, equal-mass bands, region map, steps,
   validation, record mapping, E/Eᵀ and `offset_lower_bound`, plus their
   unit tests.
3. `make_bcon_map.py` script, then `PhysicalAbstractData` / `make_prior`
   changes and env vars.
4. Switch `prepare_model` and `map_sense`; delete the flux path.
5. `user_driver` bounds (emissions ≥ 0 as now, offsets ≥ −m always),
   `bias.py` check, analysis script.
6. Gradient check and regression fixtures in Docker.
7. Docs, changelog.

## Things to watch

- **The staging trap.** Per-day BCON written by `prepare_model` must live in
  the run directory and never overwrite the staged CAMS BCON, otherwise the
  next iteration's "base" already contains an offset.
- **Disk/IO.** One BCON copy per day per iteration is small (perimeter only),
  so cost is negligible compared with the emission files.
- **Where a uniform bias goes.** A uniform obs bias can now move into the
  boundary; with fine boundary resolution and a loose `BCON_UNC` the boundary
  can absorb signal that should be emissions. The boundary offsets are
  nuisance variables, there to stop a wrong prior inflow contaminating the
  emissions, so no OSSE is planned; instead, check whether the posterior
  offsets come out larger than `BCON_UNC`.
- **Active bounds.** With coarse regions, `m` is set by the single lowest
  cell (often high in the stratosphere, where CH4 is lowest), so the bound
  is loose for the rest of the region. Log how many `bcon` bounds are active
  at the posterior; many active bounds suggest a region spans too wide a
  concentration range.
- **Changing the base.** If the base BCON is regenerated (e.g. new bias
  correction), `m` must be recomputed, so compute it at run start, not in
  `make_prior`.
- **Short runs.** A daily run (`docker` target) is shorter than a 5-day
  step, so it gets one step covering the day; the map must be built for each
  run's own dates, which `make_prior` does when `BCON_MAP_FILE` is unset.
  A map file built for one period is rejected for another.
- **Small pieces near corners.** With `spread` and per-edge cutting, a short
  edge (e.g. 150 cells) gets 1 or 2 segments rather than a 100 + 50 split;
  check the segment lengths the script prints for the production domain.
- **Outflow faces get zero gradient,** so their offsets stay at the prior.
  That is correct, but posterior uncertainty diagnostics should not report
  them as constrained.
- **`ADJ_LGRID_FREQ = SYNC_STEP` vs `OUTPUT_STEP`** does not affect
  `ADJ_LGRID_BC` (it is per BCON record), but confirm.

## Open questions

- **Default `BCON_UNC`.** Decided: 20 ppb, user-settable. CAMS background
  error is of order 10–30 ppb. Revisit if the posterior offsets are routinely
  larger than this.
- **Default resolution.** Settled as ~1000 km × ~5 days × 4 equal-mass
  bands. Still worth checking against `ADJ_LGRID_BC` from one backward run,
  which shows which scales the observations actually constrain.
- **Default remainder rule.** Decided: `spread`; `end` available.
- **Correlated prior errors** between neighbouring segments/time steps:
  in scope here, or a follow-up?
- **ICON.** `inc_icon` remains a scaling factor; should it become an offset
  too for consistency? Out of scope unless wanted.

## Implementation notes (2026-10-28)

Where the plan landed, and where it moved:

- Pure functions are in `src/openmethane/bcon_map.py`; the fourdvar glue
  (record times, grid check, per-day staged files, lower bound) is in
  `src/openmethane/fourdvar/util/bcon_offset.py`.
- `make_prior.py` writes the map it builds to `bcon_map.nc` next to the prior.
- `--min-fraction` only applies to `end` and defaults to 0, so `end` gives
  exactly 5,5,5,5,5,5,1 for 31 days.
- `minim` logs how many boundary offsets finish on their lower bound.
- `Dockerfile` takes `--build-arg CMAQ_ADJOINT_IMAGE=...`; the default stays
  `cmaq-adjoint:2.0.1` until CMAQ-Adjoint#33 is released, and must then be
  bumped, since 2.0.1 does not write `ADJ_LGRID_BC`.
- `tests/test-data/fourdvar/posterior-multipliers.nc` was converted to the new
  `bcon` format (emissions unchanged, zero offsets on the default map), and
  `tests/test-data/templates/sense_bcon_template.nc` added from
  `make_template.py`.

Validation, on the test domain with an image built from CMAQ-Adjoint
`feat/adj-lgrid-bc` (61aed58):

- `make test` in Docker: 352 passed.
- Gradient check through CMAQ, J = Σ w·CONC, 48 regions: adjoint vs central
  differences agree to 0.05–0.2% for the most sensitive regions and 0.2–0.35%
  for a random direction; outflow-face regions have exactly zero gradient and
  zero finite difference; corners of `ADJ_LGRID_BC` are exactly 0; Σ of the
  mapped gradient equals Σ `ADJ_LGRID_BC`.
