# Plan: the initial condition as an additive offset

Stacked on PR #285 (`feat/bcon-unknowns`). Branch `feat/icon-offset`, PR based
on `feat/bcon-unknowns` so the two can be tested together and retargeted to
`main` once #285 merges.

## Goal

Make the initial condition (ICON) a working, active unknown of the
inversion, as an **additive offset in ppm** on the ICON CMAQ reads on the first
day, the same way #285 treats the boundary condition:

- prior offset 0 (the bias-corrected CAMS ICON is the prior);
- prior 1-sigma uncertainty `ICON_UNC`, by default 0.05 ppm (50 ppb);
- bounded below so that ICON + offset never goes negative, using the
  smallest-value approach the boundary offsets use, not a fixed methane bound,
  so fourdvar stays usable for other species.

## Background: what the code does now

`input_defn.inc_icon` is hard-coded `False`. With it switched on, the code
would treat ICON as a **domain-wide multiplier** per species (`ICON-SCALE`,
prior 1.0, uncertainty 0.05), but that path has never run and would not work:

- `template_defn.icon` (`templates/record/icon_record.nc`) is never written by
  anything. `prepare_model`, `map_sense`, `from_file` and
  `ModelInputData.create_new` all read it, so turning the flag on fails
  straight away.
- The `icon` record in `cmaq_io_files.py` has `actual = cmaq_config.icon_file`,
  the **staged** ICON, with its `<YYYY-MM-DD>` tag not replaced. Writing it
  would overwrite the base ICON (or create a file with a literal tag in its
  name). #285 solved the same problem for BCON by giving CMAQ its own run copy
  (`bcon_run_file`).
- `map_sense` computes `Σ ADJ_LGRID[t=0] · ICON`, the gradient with respect to
  a multiplier.

Things that already work and are kept:

- The vector layout: per species, `icon` (1 value), then `emis`, then `bcon`
  (`condition.py`, `uncondition.py`, `get_bounds`).
- The gradient source. `ADJ_LGRID` (`conc_sense_file`) for the first day is in
  time order with record 0 at 00:00 of the start date. I checked this on the
  e2e artifacts of run 40625516246: 25 hourly records, the first at
  `2022341:000000`, which is the last one the backward run writes. Record 0 is
  ∂J/∂C at the initial time, in CF/ppm, on the full 3-D grid (32 layers on the
  test domain, the same as ICON).
- `PhysicalAdjointData.icon_units = "CF/ppm"`.

## Design

### The control variable

One scalar offset `x_icon[spc]` per species, in ppm, added to every cell,
layer and record of the staged ICON:

```
ICON_run[spc] = ICON_staged[spc] + x_icon[spc]
```

This keeps the current layout (one icon unknown per species), so `condition`,
`uncondition` and the vector length do not change. A spatially or vertically
resolved ICON offset (for example the equal-mass bands of `bcon_map`) would be
a natural follow-up, but is out of scope here (see Open questions).

### Gradient

The adjoint of adding a constant to every cell is a sum:

```
∂J/∂x_icon[spc] = Σ_{lay,row,col} ADJ_LGRID[spc][t=0, lay, row, col]     (CF/ppm)
```

This replaces `Σ ADJ_LGRID[t=0] · ICON` in `map_sense`.

**Correction found by the gradient check.** `ADJ_LGRID` at t=0 does not
include the adjoint forcing on CONC record 0 of the first day, which *is* the
initial condition. The gradient is

```
∂J/∂x_icon[spc] = Σ ADJ_LGRID[spc][0] + Σ ADJ_FORCE_day1[spc][0]
```

`map_sense` reads the first day's forcing file (`AdjointForcingData`,
`force.<YYYYMMDD>`), which `wipeout_bwd` leaves in place. In an inversion this
term is zero: `obs_preprocess.model_space.get_step` matches an observation at
or before a day's start to the previous day's last record, and `next_step`
wraps to record 1, so no observation weights record 0. It is kept so the
gradient is exact for any forcing, including the check below.

### Units, prior and uncertainty

- Offset in ppm, the units of the CH4 field in ICON (about 1.8 ppm on the test
  domain).
- Prior 0. `ICON_UNC` (env, ppm, default `0.05`) replaces the hard-coded
  `icon_unc = [5 * 10e-3]` in `make_prior.py`.
- Preconditioning is unchanged: `condition` divides by `icon_unc`, and
  `uncondition` multiplies by it.

### Bound

L-BFGS-B bound on the scaled unknown:

```
lower[spc] = -min(ICON_staged[spc]) / icon_unc[spc]        upper = None
```

The minimum is over every record, layer and cell of the staged ICON for the
start date. As with BCON, the bound is always applied, whatever
`ALLOW_NEGATIVE_EMISSIONS` says. For CH4 it is roughly −1.8 ppm (the test domain's ICON
averages about 1.8 ppm), which in practice is never reached, but it is correct for any species with no
methane-specific constant. `minim` already logs how many boundary offsets end
on their bound; extend the log line to say whether each ICON offset did.

### Run copy of ICON

As with BCON, CMAQ reads a run copy and the staged file is never modified:

- `cmaq_config.icon_run_file = <cmaq_base>/icon/ICON.nc` (no date tag, since
  only the first day reads it).
- `cmaq_handle.run_fwd_single(is_first=True)` points `INIT_*_1` at
  `icon_run_file` instead of `icon_file`.
- The `icon` record in `cmaq_io_files.py` becomes `actual = icon_run_file` and
  `template = dt.replace_date(icon_file, start_date)`. The template is the
  staged ICON, so `template_defn.icon` and `icon_record.nc` are deleted.
- The record is present **whether or not `inc_icon` is on**. With it off,
  `prepare_model` writes the staged ICON unchanged (offset 0). There is then a
  single code path to CMAQ, the same as for BCON, and a later change to
  `INC_ICON` can't leave CMAQ reading a stale run copy.

### Configuration

- `INC_ICON` (env bool) replaces the hard-coded `inc_icon = False`.
  Recommended default: `true` (see Open questions).
- `ICON_UNC` (env float, ppm), default `0.05`.

### Prior file format

The `icon` group changes from `ICON-SCALE`/`ICON-UNC` over an `SPC` dimension to
per-species scalars, matching the `emis` and `bcon` groups:

```
group icon:  units = "ppm" (PhysicalData) | "CF/ppm" (PhysicalAdjointData)
  CH4      ()   offset
  CH4_UNC  ()   uncertainty
```

`from_file` checks the group's `units` against `cls.icon_units`, the same way
`check_bcon_units` does for `bcon` (generalise that helper to take the group
name). When `INC_ICON` is on and the prior has no `icon` group, it fails with a
clear message: "regenerate the prior with make_prior.py, or set
INC_ICON=false". No existing prior has an `icon` group, since the flag was
never on, so nothing old needs converting.

## Files and wiring

1. **`params/input_defn.py`**: `inc_icon = env.bool("INC_ICON", True)`,
   `icon_unc = env.float("ICON_UNC", 0.05)`.
2. **`params/cmaq_config.py`**: add `icon_run_file`.
   **`params/template_defn.py`**: remove `icon`.
3. **`util/cmaq_io_files.py`**: make the `icon` record unconditional, with the
   run-file/staged-template paths above.
4. **`util/cmaq_handle.py`**: `INIT_*_1` reads `icon_run_file` on the first
   day.
5. **New `util/icon_offset.py`** (small, next to `bcon_offset.py`):
   `base_icon_file()` (staged ICON for the start date) and
   `offset_lower_bound(spc)`.
6. **`transfunc/prepare_model.py`**: always build `model_input_args["icon"]`
   as `{spc: base + (physical.icon[spc] if inc_icon else 0)}`, and ensure the
   `icon/` directory exists. Drop the `icon_scale` block.
7. **`transfunc/map_sense.py`**: the icon gradient becomes the sum of
   `ADJ_LGRID[spc][0]`. Drop the read of `template_defn.icon`. Keep the shape
   check, against the staged ICON.
8. **`datadef/abstract/_physical_abstract_data.py`**: the new `icon` group
   layout in `archive`/`from_file`, the units check, and the NLAYS check
   against the staged ICON instead of `template_defn.icon`.
   `physical_data.py` and `physical_adjoint_data.py` already have the right
   `icon_units`. Update the comment `# icon_dict: {var-name: scaling_value}`.
9. **`datadef/model_input_data.py`**: `get_vector` and
   `load_from_vector_template` already skip non-`emis` records, so nothing
   changes. The icon run file is staged from its template like BCON (added in
   92da731).
10. **`user_driver.py`**: `get_bounds` uses `icon_offset.offset_lower_bound`
    for the icon slot, instead of `(None, None)`. Report ICON offsets on their
    bound in `minim`. The `inc_icon is turned off` warning stays, for when the
    user disables it.
11. **`scripts/cmaq_preprocess/make_prior.py`**: write the new `icon` group
    with offset 0 and `ICON_UNC`. Remove `icon_scale` and the hard-coded
    `icon_unc`.
12. **`scripts/cmaq_preprocess/make_template.py`**: copy the staged ICON to
    `icon_run_file` next to the BCON copy, and remove the stale "ICON emis file
    doesn't need to be copied" comment.
13. **`cmaq_preprocess/bias.py`**: `calculate_mean_obs` runs
    `PhysicalData → ModelInputData`, so it will now also write the ICON run
    copy. Check that it reads the bias-corrected staged ICON and that a zero
    offset leaves it unchanged. `correct_icon_bcon` keeps modifying only the
    staged files.
14. **Tests that set up CMAQ runs by hand** (`test_create_chk.py::run_fwd_day`
    and anything else calling `run_fwd_single(is_first=True)`): copy the staged
    ICON to `icon_run_file`, as they already do for BCON.

## Tests

- **Unit, `get_bounds`**: the icon slot's lower bound is
  `-min(staged ICON)/icon_unc` on a synthetic ICON with a known minimum, for
  two species with different minima (this guards the other-species case).
- **Unit, prepare/map_sense adjoint pair**: on synthetic files,
  `⟨P(x), y⟩ = ⟨x, Pᵀ(y)⟩` where P adds `x` to ICON and Pᵀ sums
  `ADJ_LGRID[0]`.
- **Unit, archive round trip**: an `icon` group with units; `PhysicalAdjointData`
  writes `CF/ppm` and is rejected as a prior; a prior with no `icon` group and
  `INC_ICON=true` fails with the "regenerate" message.
- **Unit, `condition`/`uncondition`**: `test_uncondition.py` already
  parametrises on `inc_icon`. Run it with the flag both on and off.
- **Unit, `test_params.py`**: regenerate the parameter fixtures for
  `INC_ICON`/`ICON_UNC` (`make test-regen`, then review the diff).
- **Gradient check through CMAQ** (Docker, test domain, cmaq-adjoint 2.1.0), the
  same procedure that validated `ADJ_LGRID_BC` in #285: J = Σ w·CONC, perturb
  `x_icon` by ±δ, and compare the central difference with the adjoint. Expect
  agreement to well under 1%. Record the result in this file.

  **Result (2026-10-28).** One day (2022-12-07), w ~ U(0, 1) on every CONC
  record, layer and cell (seed 42), force = w:

  | | dJ/dx |
  | --- | --- |
  | Σ ADJ_LGRID[0] alone | 4173.70 |
  | Σ ADJ_LGRID[0] + Σ ADJ_FORCE[0] | 5770.89 |
  | central difference, δ = 0.1 | 5773.69 (+4.9e-4) |
  | central difference, δ = 0.01 | 5767.34 (−6.2e-4) |
  | central difference, δ = 0.001 | 5772.19 (+2.3e-4) |

  The gap with `ADJ_LGRID` alone, 1597, equals Σ w[0] = 1597.2. With the
  forcing term the agreement is better than 0.1%, with no trend in δ (the
  model is linear in the offset; the scatter is float32 CONC round-off).

  Share of Σ ADJ_LGRID[0] by layer: about two thirds in layers 1–12, under
  1% in each of layers 22–27, and 14% in the top four layers (29–32). So the
  domain-wide sum is not dominated by the stratosphere on this test, but the
  top layers carry a noticeable share.

  On later days CONC record 0 duplicates the previous day's last record, and
  ADJOINT_BWD presumably leaves out its forcing there too. That loses nothing,
  because the observation operator never weights record 0 of any day (see
  Gradient above).
- **e2e** (CI): with `INC_ICON=true` the e2e run exercises the full path
  (template → prior → fourdvar) with no extra setup.

## Docs and changelog

- `docs/reference/parameters.md`: `INC_ICON`, `ICON_UNC`.
- `docs/reference/outputs.md`: the `icon` group of the prior and
  posterior files (offset in ppm) and of `gradient_iterNNNN.ncf` (CF/ppm).
- `docs/reference/cmaq-preprocess.md:127`: "initial conditions if
  `input_defn.inc_icon` is set" → `INC_ICON`.
- `docs/reference/boundary-conditions.md`: a short section, or a sibling page,
  on the ICON offset and how it interacts with the BCON offsets and the bias
  correction.
- Changelog for the new PR, one file per change:
  - `breaking`: the initial condition is now solved for by default, as an
    additive offset with prior 0 and `ICON_UNC`, bounded so ICON stays
    non-negative; priors need regenerating; posterior emissions change. Say
    what the user must change (`INC_ICON=false` restores the old behaviour).
  - `feature`: the `INC_ICON` and `ICON_UNC` settings.

## Order of work

1. Plumbing with no behaviour change: `icon_run_file`, the unconditional
   `icon` record, the `cmaq_handle` switch and `make_template` staging, with
   `inc_icon` still `False`. Full test suite and e2e green.
2. Offset maths: `prepare_model`, `map_sense`, `icon_offset.py`, `get_bounds`,
   with unit tests.
3. Prior format: `make_prior`, `archive`/`from_file`, units check.
4. `INC_ICON`/`ICON_UNC` env settings and default; regenerate fixtures.
5. Gradient check in Docker; record the result here.
6. Docs and changelog; `make changelog-draft`.

## Things to watch

- **Identifiability.** A uniform ICON shift raises every column by roughly the
  same XCH4 on day 1 and decays as air leaves the domain over a few days. In
  that window it is hard to tell apart from the first BCON step's offsets and
  from a uniform emission change. The prior uncertainties and the
  observations' timing do the separating. Watch the posterior correlation
  (or, more cheaply, whether the ICON and early-BCON offsets move in opposite
  directions in the iterations).
- **Interaction with the bias correction.** `correct_icon_bcon` already
  shifts ICON and BCON by the satellite-minus-model bias before the
  inversion. The ICON offset then corrects what is left over, so 50 ppb is a
  generous prior. With the bias correction off, it does a larger share of the
  work.
- **Monthly runs.** ICON only affects the first days of a month, so in a
  monthly run its offset is constrained by those days' observations only. A
  daily run gives the ICON offset a much larger share of the signal.
- **One unknown per species.** The CMAQ-Adjoint gradient check will show
  whether the domain-wide sum is dominated by a few layers (for example the
  stratosphere, which the column sees but transport barely touches in a day).
  If it is, the vertical-band follow-up is more urgent.

## Open questions

- **Default `INC_ICON`.** Recommended: `true`. It adds one unknown per species
  at no measurable cost, and it is the point of the change. The alternative is
  `false` for this PR, enabled once the posterior has been reviewed on a real
  month.
- **Default `ICON_UNC`.** 50 ppb as suggested. That is larger than the
  20 ppb BCON default; a reasonable choice given the bias correction, but
  worth revisiting once posterior offsets are seen.
- **Spatial or vertical structure.** One scalar per species now. Reuse
  `bcon_map.equal_mass_bands` for a few vertical bands later?
- **Fixed −500 bound.** Not used: the smallest-value bound costs one read of
  one file and works for any species.
