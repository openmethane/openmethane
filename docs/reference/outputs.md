# Outputs

The Open Methane workflows produce a small number of key outputs, which are
published in the public Open Methane Data Store. All are NetCDF files following
[CF conventions](https://cfconventions.org/), on the same grid as the domain.

Results are written under the run's archive directory, inside `STORE_PATH`.

## Output layout

Each fourdvar run writes to its own directory, `archive/<EXPERIMENT>-<YYYYMMDD>-<HHMMSS>`
(UTC time the run started, e.g. `archive/openmethane-20261006-031542`), and
`archive/<EXPERIMENT>-latest` is a relative symlink to the most recent run. Use
the `-latest` path when you want "the last run", and the timestamped path when
you want a specific one. Earlier runs are never moved, renamed or deleted.

- The link means *latest started*, not *latest successful*. If a run fails or is
  terminated, the link still points at it, and the previous good run is found by
  its timestamp.
- Tools that follow symlinks will copy the latest run twice. `aws s3 sync` and
  `cp -r` on `archive/` store the data under both the timestamped name and
  `-latest`. Exclude `*-latest`, or upload the timestamped directory
  (`readlink archive/<EXPERIMENT>-latest`).
- Two runs starting in the same second with the same `EXPERIMENT` is an error.

## Emissions

Produced by the monthly workflow, at the end of the inversion.

### `posterior-emissions.nc`

The primary result. The inversion solves for per-cell *multipliers* on the prior;
this file converts those into absolute emissions by multiplying through by the
prior, and averages over the run period. Most consumers want this file.

Key variables, all dimensioned `(time, vertical, y, x)`:

| Variable | Units | Description |
| --- | --- | --- |
| `ch4` | kg/m2/s | **The posterior estimate.** Methane flux estimated from observations. `standard_name` is `surface_upward_mass_flux_of_methane`. |
| `prior_ch4` | kg/m2/s | The prior estimate, averaged over the same period, for comparison. |
| `prior_ch4_sector_*` | kg/m2/s | The prior broken down by sector (livestock, fugitives, wetlands, fires, …), averaged over the period. Sectoral information comes from the prior only — the inversion constrains the total in each cell, not its attribution between sectors. |

Also included: `lat`, `lon`, `x_bounds`, `y_bounds`, `time_bounds`, `land_mask`,
`cell_name`, and a grid mapping variable carrying the projection.

`time` has a single value, the start of the period, with `time_bounds` giving the
full period covered. Comparisons between `ch4` and `prior_ch4` are therefore
period averages, not time series.

Global attributes record `domain_name`, `domain_version`, `domain_slug`, grid
spacing (`DX`, `DY`, `XCELL`, `YCELL`), and the `openmethane_version` and
`openmethane_prior_version` that produced the file.

> [!NOTE]
> A posterior close to the prior in a given cell means one of two things: the
> observations agreed with the prior, or there were no usable observations over
> that cell. These look identical in this file. Check observational coverage for
> the period before interpreting an unchanged cell as confirmation.

### `posterior-multipliers.nc`

The raw inversion result: the multiplier applied to the prior in each cell.
Useful for inspecting what the inversion actually did, since it separates the
correction from the prior's magnitude. `posterior-emissions.nc` is derived from
this.

If a run completed the inversion but failed during post-processing, the emissions
file can be regenerated from this without re-running the model:

```shell
python scripts/manual_postproc.py -f path/to/posterior-multipliers.nc
```

### `iter{NNNN}.ncf`

One file per successful optimiser iteration, archived by
`user_driver.callback_func`. These let you see how the solution evolved, and are
what `restart_script.py` resumes from.

## Alerts

Methane alerts are produced for each calendar day, and represent grid cells
in which the observed concentration of methane is significantly different than
the simulated concentration.

Alerts are independent of the inversion: they compare observations against the
*prior* simulation from the daily workflow, so they surface anomalies without
waiting for a monthly inversion to run.

Produced by `scripts/alerts/create_alerts.py` as `alerts.nc` by default, which
includes:

### `alerts`

A boolean field with a `1` value for any cells in which a methane anomaly was
detected. A `NaN` value represents a cell where not enough data was available
to achieve a result.

"Not enough data" is controlled by `ALERTS_COUNT_THRESHOLD`, the minimum number
of observations in a cell (default 30). On small domains or short periods this
often needs lowering, or every cell returns `NaN`.

### `obs_enhancement`

The difference, in ppb, between nearby observations (the "near field") and far
away observations (the "far field"). The distances which determine inclusion in
the near and far fields are available in the `alerts_near_threshold` and
`alerts_far_threshold` global attributes.

Comparing near field against far field, rather than against an absolute value,
means a genuinely localised source stands out while a domain-wide offset — from
model bias or from the boundary conditions — does not.

### `alerts-baseline.nc`

Not an alert product, but a prerequisite for one. Produced by
`scripts/alerts/alerts_baseline.py` from a set of completed daily runs, it
records how large the near-versus-far-field difference normally is in each cell,
which is what makes "significantly different" meaningful. `create_alerts.py`
reads it via `ALERTS_BASELINE_FILE`.

One baseline covers a whole domain, so `scripts/docker-alerts-baseline.sh`
writes it to the root of `DATA_ROOT` as
`alerts-baseline.${DOMAIN_NAME}-${DOMAIN_VERSION}.nc` rather than into a dated
run directory. Build it before creating alerts — see
[Quickstart](../guides/quickstart.md#5-create-alerts-optional).

## Intermediate outputs

Not published, but useful when debugging a run.

| File | Stage | Contents |
| --- | --- | --- |
| `tropomi/<YYYY-MM-DD>/*.nc` | daily | The raw TROPOMI granules as downloaded, whole rather than cropped. Reused if the fetch is rerun. |
| `simulobs.pic.gz` | daily | Simulated observations — what the satellite should have seen given the prior. Compared against the processed observations to produce alerts. |
| `input/test_obs.pic.gz` | daily | The processed TROPOMI observations, in `fourdvar`'s format. Matched by `OBS_FILE_GLOB`. |
| MCIP output in `MET_DIR` | daily | Meteorology on the CMAQ grid. Reused by the monthly workflow rather than regenerated. |
| CMAQ templates in `CTM_DIR` | preprocessing | Concentration, forcing and sensitivity templates. |

The `.pic.gz` files are gzipped Python pickles, readable via the corresponding
`datadef` class:

```python
import openmethane.fourdvar.datadef as d
obs = d.ObservationData.from_file("input/test_obs.pic.gz")
```
