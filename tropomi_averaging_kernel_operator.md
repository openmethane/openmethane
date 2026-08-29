# Bringing the TROPOMI observation operator into line with the column-averaging-kernel formulation

**Status:** implemented on branch `obsop-update`.
**Reference implementation:** [`hannahnesser/TROPOMI_inversion/python/TROPOMI_operator.py`](https://github.com/hannahnesser/TROPOMI_inversion/blob/main/python/TROPOMI_operator.py)
(functions `GC_to_sat_levels` and `apply_avker`).

The operator itself lives in `src/openmethane/obs_preprocess/column_operator.py`,
which carries the equations below in its module docstring. §4 records what
changed in each file and §5 what the change does to the numbers.

## 1. Why this is needed

The transform `ModelOutputData -> ObsData`
(`src/openmethane/fourdvar/transfunc/obs_operator.py`) computes each simulated
observation as a linear functional of the CMAQ concentration field, using the
`weight_grid` dictionary attached to each observation. The weights are built at
preprocessing time in
`src/openmethane/obs_preprocess/obsESA_defn.py::ObsSRON.add_visibility`.

The scaffolding around that code (`ref_profile`, `alpha_scale`, and the
commented-out lines in `obs_operator.py`) was written for a **scaled-profile**
retrieval, in which the retrieved state is a single scalar multiplying a fixed
a-priori shape. The operational TROPOMI CH4 product is not that: it is a
profile-scaling *optimal-estimation* retrieval reported as a column-averaged dry-air
mole fraction, with a **column averaging kernel** `A` and an explicit a-priori
profile. Simulating it requires

* mapping the model profile onto the retrieval's own vertical grid,
* weighting by the retrieval's pressure weights (not the model's),
* applying the averaging kernel, and
* adding the a-priori contribution `(1 - A) x_a`, which is **independent of the
  model state**.

## 2. What the code did before this change

Two things are worth separating, because they are often conflated:

**(a) The scaled-profile machinery is dead code.** In `obs_operator.py` the
`ref_profile` dot-product and the `alpha_scale` normalisation are commented out;
`ObservationData.ref_profile` and `ObservationData.alpha_scale` are never
populated (`observation_data.py:265-270`, `observation_data.py:326-327`), and the
class attributes are only ever checked for being non-`None` so a warning can be
emitted. `ObsSRON` still *computes and stores* `ref_profile` and `alpha_scale`
(`obsESA_defn.py:112-140`) and still lists `alpha_scale` in `required`, but nothing
downstream reads them.

**(b) What is actually evaluated** is therefore

```
y_hat_i  =  1e3 * sum_over_coords( weight_grid[i][coord] * conc[coord] )
```

with, from `add_visibility`,

```
model_vis[l] = pw_cmaq[l]                       # CMAQ pressure weight, l = CMAQ layer
weight_grid[(date, step, l, row, col, spc)] = model_vis[l] * geom[l, row, col] / sum_rowcol(geom[l, ., .])
```

where `geom` is the ray-traced light-path overlap from `map_location`, normalised
to sum to 1 within each CMAQ layer, and `pw_cmaq` comes from
`ModelSpace.get_pressure_weight`, i.e. the CMAQ layer pressure thicknesses divided
by the CMAQ column thickness (`model_space.py:230-235`).

In equations, the operator currently in force is

```
y_hat = sum_l pw_cmaq[l] * x_model[l]
```

That is a *pressure-weighted mean of the model column between the CMAQ surface and
the CMAQ model top* — equivalent to assuming

1. `A_j = 1` at every retrieval level (the averaging kernel is read from file into
   `obs_kernel` and stored, but never applied),
2. no a-priori contribution (`(1 - A) x_a = 0`),
3. no vertical regridding: the CMAQ pressure grid stands in for the retrieval
   grid, so the retrieval's own pressure weights and surface pressure are ignored,
4. the column above the CMAQ model top (VGTOP = 5000 Pa in the current domain,
   ~5% of the air mass) simply does not exist; the weights are renormalised over
   the model column instead.

Assumption 1 is not catastrophic for TROPOMI (its CH4 column kernels are near
unity through much of the troposphere) but it is wrong exactly where the inversion
is most sensitive: `A` departs most from 1 in the lowest layers over dark
surfaces, high aerosol load, and high solar zenith angle — i.e. over the
observations that carry the surface-emission signal. Assumptions 3 and 4 are
systematic and of order tens of ppb (see §6.2).

Supporting facts confirmed against the test data
(`tests/test-data/tropomi/2022-12-07*/S5P_OFFL_L2__CH4____*.SUB.nc4`):

* `/PRODUCT` has `layer = 12`, `level = 13`.
* Vertical ordering is **top-of-atmosphere first**: `altitude_levels[0] ~ 65 km`,
  `altitude_levels[12] ~ 0 m`. `layer` and `level` both carry `positive = "down"`.
  The `pressure_levels` array built in
  `scripts/obs_preprocess/tropomi_methane_preprocess.py:243-245` as
  `np.arange(n_levels) * pressure_interval` is therefore in the *right order*
  (0 Pa at TOA, increasing to the surface) — it just pins the surface to
  `12 * pressure_interval` instead of the reported `surface_pressure`
  (99752.05 Pa vs 12 x 8311.837 = 99742.04 Pa for the first valid sounding: a
  ~10 Pa float32 rounding difference, harmless, but we should use the reported
  value).
* `surface_pressure` (Pa) and `dry_air_subcolumns` (mol m-2) are both present in
  `/PRODUCT/SUPPORT_DATA/INPUT_DATA` and are currently unused.
* `column_averaging_kernel` (dimensionless, 12 layers) is read as `obs_kernel` and
  carried through to the saved observation, but never used.
* Because the pressure grid is equidistant in pressure, the retrieval pressure
  weights are exactly uniform: `pw_j = 1/12` for every layer.

## 3. The target formulation

Following `apply_avker` and `GC_to_sat_levels`:

```
y_hat = sum_j pw_j [ x_a,j + A_j ( x_m,j - x_a,j ) ]                    (1)
x_m,j = sum_i M_ji x_i                                                  (2)
```

with

| symbol | meaning | grid |
| --- | --- | --- |
| `j = 0..J-1` | retrieval layer (J = 12), TOA first | TROPOMI |
| `i = 0..I-1` | CMAQ layer (I = 32), surface first | CMAQ |
| `p_j` | retrieval level pressures, `p_0 = 0`, `p_J = surface_pressure` | TROPOMI |
| `dp_j = p_{j+1} - p_j` | layer thickness (= `pressure_interval`) | TROPOMI |
| `pw_j = dp_j / (p_J - p_0)` | pressure weight, sums to 1 | TROPOMI |
| `A_j` | `column_averaging_kernel` | TROPOMI |
| `x_a,j` | prior dry-air mole fraction, ppb: `1e9 * methane_profile_apriori / dry_air_subcolumns` | TROPOMI |
| `P_i` | CMAQ level pressures from `ModelSpace.get_pressure_bounds`, `P_0 = PRSFC` down to `P_I = VGTOP` | CMAQ |
| `M_ji` | pressure-overlap regridding matrix, rows sum to 1 | mixed |

Nesser builds `M` from the pressure-thickness overlap of the two grids
(`GC_to_sat_levels`):

```
O_ji = max( 0, min(p_{j+1}, P_i) - max(p_j, P_{i+1}) )                  (3)
M_ji = O_ji / sum_i O_ji
```

### 3.1 Recasting into fourdvar's `weight_grid` + offset form

Substituting (2) into (1) and separating the terms that depend on the model state:

```
y_hat = sum_i w_i x_i  +  c                                             (4)

w_i = sum_j pw_j A_j M_ji                                               (5)
c   = sum_j pw_j (1 - A_j) x_a,j                                        (6)
```

This is the key structural point: **the operator is still affine in the model
state, so `weight_grid` survives unchanged in structure — only its values change —
and a new per-observation constant `c` is required.** Everything downstream
(the adjoint forcing, the residual, the error weighting) keeps working, because
`d y_hat / d x_i = w_i` and the constant drops out of the gradient entirely.

Sanity checks on (4)-(6):

* `A_j = 1` for all `j` and full model coverage ⇒ `c = 0`, `sum_i w_i = sum_j pw_j = 1`.
* Constant model profile `x_i = X` ⇒ `y_hat = sum_j pw_j [x_a,j + A_j (X - x_a,j)]`,
  which is exactly `apply_avker` applied to a constant profile.
* `w_i` may be **negative** where `A_j < 0`. Nothing in the pipeline assumes
  positive weights, but see §4.5.

### 3.2 Partial vertical coverage (the CMAQ model top)

CMAQ's top is at VGTOP = 5000 Pa, whereas the retrieval grid runs to 0 Pa. Roughly
the top 5% of the air mass is outside the model. Because the retrieval grid is
equidistant in pressure with only 12 layers (`dp ~ 8300 Pa`), the whole gap falls
inside the *single topmost retrieval layer*, which comes out about 39% covered;
every other layer is fully covered.

Generalise (2) with an explicit fill for the uncovered fraction of each retrieval
layer:

```
f_j    = ( sum_i O_ji ) / dp_j                     # covered fraction, 0..1
x_m,j  = sum_i (O_ji / dp_j) x_i  +  (1 - f_j) x_fill,j                 (7)
```

which gives the clean, normalisation-free form

```
w_i = ( 1 / (p_J - p_0) ) * sum_j A_j O_ji         (+ the fill term below) (8)
c   = sum_j pw_j [ (1 - A_j) x_a,j  +  A_j (1 - f_j) x_fill,j ]         (9)
```

(using `pw_j / dp_j = 1 / (p_J - p_0)`).

**What is implemented (`fill="prior_offset"`, the default).** CMAQ is assumed to
get the vertical *structure* right up to its top, and the retrieval prior to get
the structure but not the magnitude right above it. The prior is therefore
shifted by the constant that makes it continuous with the CMAQ profile at the
model top:

```
x_fill,j = u_j + ( x_top - a_top )                                     (10)
```

where

* `u_j` is the prior averaged over the uncovered part of retrieval layer `j`,
* `x_top` is the topmost CMAQ layer, and
* `a_top` is the prior averaged over that same topmost CMAQ layer.

Comparing the model layer mean against the prior averaged over the *same*
pressure range keeps like with like; it reduces to evaluating both at the model
top edge as the layer thickness goes to zero.

Crucially `x_fill` still depends on the model state, and linearly, through
`x_top`. The operator therefore remains affine and (4) still holds, with

```
w_{I-1} += sum_j pw_j A_j (1 - f_j)
c        = sum_j pw_j [ (1 - A_j) x_a,j + A_j (1 - f_j) ( u_j - a_top ) ]  (11)
```

The topmost CMAQ layer now carries the whole uncovered column in addition to the
part it actually spans, and the constant left in `c` is exactly the *shape* of
the prior above the model top measured relative to its value at the model top —
the magnitude has been handed to the model.

Computing `u_j` and `a_top` needs the prior on a finer grid than the retrieval
reports it on, since the gap is a fraction of one retrieval layer. The prior
layer means are reconstructed as a piecewise-linear profile through the layer
mid-pressures, held constant beyond the outermost knots (the same convention the
preprocessor already used when it interpolated the prior onto CMAQ levels), and
integrated exactly over the interval required. Note this reconstruction is not
mass-conserving: the reconstructed profile's layer averages do not exactly
reproduce the reported layer means. Given the retrieval's 12-layer resolution
that is a second-order concern, but it is the obvious thing to improve if the
fill term ever turns out to matter more than it does now.

**The alternatives, both implemented and tested but not used by default:**

* `fill="prior"`: `x_fill,j = u_j`. Trust the retrieval prior above the model top
  and make no claim about air the model does not simulate. Then `c` collapses to
  `sum_j pw_j [ (1 - A_j) x_a,j + A_j (1 - f_j) u_j ]` and the model weights carry
  no fill term at all.
* `fill="model_top"`: `x_fill,j = x_top`. Extend the topmost model layer to the
  top of the atmosphere. This is what the reference implementation does (its
  `idx_top` adjustment), and it is exactly (10) with the prior's shape term
  dropped. It is a poor default for CMAQ, whose top layer sits in the lower
  stratosphere where methane is still falling steeply: it ignores that fall-off
  and biases the simulated column high.

A further refinement, not implemented: take the fill profile from the CAMS data
used to build the CMAQ boundary conditions (`download_cams_input.py` /
`bcon.run`) rather than from the retrieval prior. That would be the most
self-consistent choice, since it is the same climatology the model column is
nudged towards, but it requires plumbing CAMS into the observation preprocessor.

### 3.3 Surface-pressure mismatch

The CMAQ surface pressure (`PRSFC` from METCRO2D) and the retrieval's
`surface_pressure` disagree because of terrain and analysis differences. Handle it
by clipping the CMAQ level pressures into the retrieval's range before forming
(3), and by pinning the model's bottom edge to the retrieval surface:

```
P_0    <- p_J                                      # always: model bottom = retrieval surface
P_i    <- clip(P_i, p_0, p_J)   for i >= 1
```

The first line reproduces Nesser's `idx_bottom` adjustment. The clip drops any
CMAQ layer that falls entirely below the retrieval surface (zero thickness, zero
weight) and leaves the model-top gap intact so it is picked up by `f_j` in §3.2.
Note this makes the retrieval pressure grid — not the model's — the definition of
"the column", which is the correct choice: `A_j` and `pw_j` are only meaningful on
that grid.

## 4. The changes, file by file

### 4.1 `src/openmethane/obs_preprocess/column_operator.py` (new)

The vertical operator, as pure functions of numpy arrays with no dependency on
CMAQ, netCDF or the fourdvar parameter machinery, so that it can be tested
directly against the reference implementation.

* `pressure_overlap(sat_edge, model_edge)` — equation (3).
* `build_column_operator(sat_edge, avker, prior, model_edge, fill=...)` — returns
  a `ColumnOperator` with `weights` (per CMAQ layer, surface first), `offset`
  (ppb), and the `pressure_weight`, `coverage` and `overlap` diagnostics.
* `FILL_PRIOR_OFFSET` / `FILL_PRIOR` / `FILL_MODEL_TOP` — the three fill
  strategies of §3.2.

The module docstring carries the equations, the vertical ordering conventions
(retrieval quantities top first and ascending in pressure, model quantities
surface first and descending) and the reasoning behind the default fill.

Input is validated: the two grids must be monotone in the expected directions,
the kernel and prior must have one value per retrieval layer, and the model's
coverage of the retrieval column must come out contiguous.

### 4.2 `scripts/obs_preprocess/tropomi_methane_preprocess.py`

* Reads `surface_pressure` and `dry_air_subcolumns` from
  `/PRODUCT/SUPPORT_DATA/INPUT_DATA` and passes them through to `ObsSRON`.
* Builds the retrieval level pressures down from the reported `surface_pressure`
  rather than as `n_layer * pressure_interval`, preserving the top-first ordering
  and clamping at zero. This only moves the grid by ~10 Pa, but it anchors it on
  the same surface pressure the retrieval's own pressure weights used.
* **Fixes a latent bug:** `methane_profile_apriori` was reshaped with
  `temp.reshape(temp.size, -1)`, which produces an `(n_sounding * n_layer, 1)`
  array rather than `(n_sounding, n_layer)`, so `ch4_profile_apriori[i, :]` was
  returning a single element of the flattened array — the wrong sounding *and*
  the wrong layer. It fed only `ref_profile`, which nothing downstream read, so
  it never surfaced. Now reshaped as `(-1, temp.shape[-1])`, matching what the
  averaging kernel already did.
* Stamps `obs_operator_version` into the domain metadata.

The hard-coded 20 ppb observation uncertainty is **left exactly as it was**. It
is unrelated to the averaging kernel and changing the error model in the same
change as the operator would make the effect of either impossible to see. It is
still worth revisiting: see §6.1.

### 4.3 `src/openmethane/obs_preprocess/obsESA_defn.py`

* `required` is now `("value", "uncertainty", "weight_grid", "offset_term")`;
  `alpha_scale` is gone, and the `default` override that suppressed
  `offset_term` has been removed so `ObsGeneral`'s default applies again.
* `_convert_ppm` is replaced by `prior_profile()`, which divides
  `methane_profile_apriori` by the retrieval's own `dry_air_subcolumns`. The old
  hydrostatic conversion `dp * 1000 / (g * M_air)` ignored water vapour and was
  wrong by up to ~2% in a moist boundary layer.
* `add_visibility` now calls `build_column_operator` and spreads each layer's
  weight over the ray-traced cells in that layer, exactly as before — the key
  structure of `weight_grid` is untouched, only the values change. A layer the
  light path misses now yields zero weights rather than a `ZeroDivisionError`.
* Stored per observation:

  | key | contents |
  | --- | --- |
  | `weight_grid` | as before, built from the new operator weights |
  | `offset_term` | scalar `c`, ppb |
  | `obs_kernel` | `A_j` (kept) |
  | `prior_profile` | `x_a,j` in ppb on the retrieval grid (replaces `ref_profile`) |
  | `sat_pressure_weight` | `pw_j` (new) |
  | `model_coverage` | `f_j` (new — quantifies the model-top gap) |
  | `model_vis` | `w_i` (kept, meaning changed) |
  | `alpha_scale`, `ref_profile`, `model_pweight` | removed |

### 4.4 `src/openmethane/fourdvar/datadef/observation_data.py`

* `alpha_scale` and `ref_profile` class attributes removed; `offset_term` added,
  populated in `from_file`, written by `archive`, and length-checked in
  `assert_params`.
* `OBS_OPERATOR_VERSION = 2` defines the file format. `from_file` pops
  `obs_operator_version` from the domain (so it is not compared against the
  concentration file in `check_grid`) and warns loudly, naming the file, when it
  reads anything older.
* Legacy files still load, with `offset_term` defaulting to 0.0. Refusing them
  outright was tempting, but `tests/test-data/obs/test_obs_2022-12-08.pic.gz`
  cannot be regenerated — there is no TROPOMI or MCIP test data for that day —
  and the same is true of any observation file a user has already produced. The
  warning says plainly that simulated observations made from such a file will be
  wrong.

### 4.5 `src/openmethane/fourdvar/transfunc/obs_operator.py`

`val_list` is initialised from `ObservationData.offset_term` instead of zeros, so
the offset is added once per observation rather than once per date, and the dead
`ref_profile` / `alpha_scale` comments are gone. Nothing else changes.

### 4.6 `src/openmethane/fourdvar/transfunc/calc_forcing.py`

**No functional change**, and a comment recording why: the operator is affine,
`dy/dconc` is still the `weight_grid`, and a constant offset contributes nothing
to the adjoint. This is the main reason the change is cheap.

### 4.7 Peripheral

* `ModelSpace.get_pressure_weight` and `ModelSpace.pressure_interp` are no longer
  used by the operator (`get_pressure_bounds` still is). They are left in place
  rather than removed in the same change.
* `extra_scripts/cost_function.py` still refers to `ob["ref_profile"]` with the
  scaled-profile dot product. It is a one-off scratch script with hard-coded NCI
  paths that was already inconsistent with the live operator, so it has been left
  alone; it will need updating or deleting if anyone wants to use it again.
* `docs/tropomi.md` gained a short section pointing at the operator; a
  `breaking` changelog entry describes the file-format change.

## 5. Testing and what the change does to the numbers

### 5.1 Tests

`tests/unit/obs_preprocess/test_column_operator.py` (12 tests, all passing)
covers the operator directly:

* **Agreement with the reference implementation.** `GC_to_sat_levels` and
  `apply_avker` are transcribed verbatim into the test file and run on random
  kernels, priors and profiles over 20 draws, in two configurations: a model that
  spans the whole retrieval column (where filling is irrelevant), and the real
  CMAQ grid under `fill="model_top"` (which is what the reference does at the
  model top). Both agree to a relative tolerance of 1e-10.
* Overlap conservation: no retrieval or model layer is over-counted, and the
  overlap totals the shared column.
* `A = 1` with full coverage gives a zero offset, weights summing to one, and
  uniform pressure weights on the equidistant retrieval grid.
* A constant model column reduces to `apply_avker` on a constant profile.
* Partial coverage is reported, and only the topmost retrieval layer is affected.
* The `prior_offset` fill is continuous with the model top (with a locally flat
  prior it coincides with `model_top`), carries the prior's gradient (it sits
  below `model_top` and above `prior` for a methane-like prior), and moves with
  the topmost CMAQ layer by exactly its own weight plus the uncovered weight.
* Surface-pressure mismatch in either direction leaves no gap at the bottom.
* Malformed input is rejected.

`tests/unit/fourdvar/datadef/test_observation_data.py` gained a check that the
stored weights and offset really describe the column operator across all 165
observations in the regenerated fixture, and a check that a legacy file warns and
falls back to a zero offset.

Fixtures regenerated: `tests/test-data/obs/test_obs_2022-12-07.pic.gz` and the
`tests/integration/obs_preprocess/test_tropomi_methane_preprocess/*.yml`
regressions. `tests/test-data/obs/test_obs_2022-12-08.pic.gz` is deliberately
left in the old format, as §4.4 explains.

Everything in `make test` passes except `test_setup_for_cmaq`, which fails on
this checkout for want of WRF input data and is unrelated.

### 5.2 What it does to the numbers

Measured over the 165 observations in the regenerated 2022-12-07 fixture:

| quantity | value |
| --- | --- |
| `offset_term` | -13.4 ppb mean, range -14.4 to -12.7 |
| sum of the weights | 1.0000 for every sounding |
| coverage of the topmost retrieval layer | 0.39 mean (0.38 to 0.40) |
| simulated column for a uniform 1850 ppb model | 1836.6 ppb mean |

Two things are worth drawing out.

**The weights sum to one, and that is a real check.** `sum_i w_i = sum_j pw_j A_j`
under the `prior_offset` fill, so the weights summing to one says the retrieval's
column kernels have a pressure-weighted mean of one — which is how TROPOMI
normalises them. Getting this for free is good evidence the kernel is being read
on the right grid and in the right vertical order.

**The offset is not small.** It decomposes, for a typical sounding, into about
-11.3 ppb from the `(1 - A) x_a` term (dominated by the topmost retrieval layer,
where `A ~ 0.69` and the prior is stratospheric at ~1420 ppb against ~1860 ppb
below) and about -2.4 ppb from the prior's shape above the model top. Both were
previously zero. A uniform 1850 ppb model column that used to simulate as exactly
1850 ppb now simulates as ~1837 ppb: a systematic shift of the same order as the
20 ppb uncertainty assumed for every observation.

## 6. Consequences and things to watch

### 6.1 Physical/statistical

* Sensitivity to the model shrinks wherever `A < 1`, and the gradient is
  redistributed vertically. Boundary-layer-heavy soundings over dark surfaces will
  now carry less weight relative to well-lit ones — which is the point.
* The mean model-minus-observation bias will move, because the `(1 - A) x_a` term
  and the treatment of the above-model-top column both enter the simulated
  value. The measured shift is about -13 ppb (§5.2). Re-examine the constant
  20 ppb uncertainty (§4.2) and the destriping in light of the new residual
  statistics.
* The topmost CMAQ layer now carries the whole uncovered column on top of the
  part it spans — roughly 0.05 of the total weight rather than 0.01. Emission
  perturbations barely reach that layer, so in practice this makes the simulated
  column a little more sensitive to the boundary and initial conditions and
  correspondingly less to emissions. That is the honest consequence of the
  assumption in §3.2, not a side effect to be tuned away.

### 6.2 Known inconsistencies retained (document, do not silently fix)

* The observed value is `methane_mixing_ratio_bias_corrected`, further modified by
  `destripe_smoothing`, while `A` and `x_a` describe the *uncorrected* retrieval.
  Nesser makes the same choice (`xch4_corrected`), so this is consistent with the
  reference, but it is an approximation.
* CMAQ concentrations are treated as dry-air mole fractions (ppmV) matching
  TROPOMI's dry-air column mixing ratio; `convFac = 1e3` converts ppm to ppb and
  is unchanged.
* Above VGTOP the simulated column follows the retrieval prior's shape with the
  model's magnitude (§3.2). This is a choice, not a fact; `model_coverage` is
  stored on every observation so its size can be quantified, and the two
  alternative strategies are one argument away.
* The piecewise-linear reconstruction of the prior used to average it over
  sub-layer pressure ranges is not mass-conserving (§3.2).

### 6.3 Implementation placement

The weights and the offset are computed **at preprocessing time**, as before. This is
exact rather than approximate, because the CMAQ meteorology (and hence `PRSFC`,
the layer pressures, and therefore `M`) is prescribed and identical at every
iteration of the optimisation. The only quantity that varies across iterations is
the concentration field, and the operator is linear in it. Computing the weights
at runtime inside `obs_operator` would buy nothing and would cost a
METCRO2D read per iteration.

One consequence worth stating: `get_pressure_bounds` is evaluated at the
*surface-layer sample coordinate* of each sounding
(`coord = next(c for c in proportion if c[2] == 0)`), so a sounding whose light
path crosses several columns uses one column's pressure profile for the vertical
regridding. That approximation exists today and is unchanged; it is small compared
with the errors being removed here.

## 7. Follow-ups not done here

1. The observation uncertainty is still a hard-coded 20 ppb (§4.2). Revisit it
   against the new residual statistics, and consider making it configurable with
   `methane_mixing_ratio_precision` plus a representativeness term.
2. `extra_scripts/cost_function.py` needs updating or deleting (§4.7).
3. Consider a mass-conserving reconstruction of the prior, or a CAMS-based fill,
   if the fill term ever proves to matter more than the ~2 ppb it does now
   (§3.2).
4. Run the inversion end to end and record how the cost function and posterior
   move; the numbers in §5.2 are the forward operator only.
