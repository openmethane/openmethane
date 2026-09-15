# Model-top drift diagnostics

The scripts behind
[#248](https://github.com/openmethane/openmethane/issues/248): the forward
model's simulated columns climb about +0.2 ppb per day through a monthly run,
and the climb is almost entirely above 220 hPa.

Like everything under `src/analysis`, these are diagnostics rather than pipeline
code. They read archived run output on the host; none of them run inside the
container or touch a live run.

## What each one answers

| | |
| --- | --- |
| `extract.py <month>` | Builds the per-sounding cache everything else reads. Streams a monthly run's `observed.pickle` against its `simulobs_first_guess.pic.gz` and keeps the whole column operator per sounding — averaging kernel, retrieval prior profile, per-retrieval-layer model coverage, per-CMAQ-layer weights — with qa, albedo, aerosol and precision. About 500 MB a month. **Run this first.** |
| `analyse.py <month>` | How far the model has drifted from the CAMS field driving it, day by day; how the residual splits between a whole-domain day effect and a spatial pattern; which retrieval properties the residual tracks, tested inside 200 km blocks on a single day; and whether the model's excess grows with distance into the domain. |
| `accumulation.py` | The same drift measured without a surrogate, by differencing the monthly run against the daily runs — single-day forward passes from the same mornings' CAMS. Day 1 is a built-in control: both runs start from the same field, so it has to come out near zero. |
| `drift_profile.py [--sampled]` | Where in the column the drift sits, from the model's own daily state. `--sampled` weights each grid cell by how many soundings it holds, which is the figure quoted in the issue; the default is a flat domain mean. |

## Pointing them at data

Two environment variables, both required by the scripts that need them:

- `OM_MONTHLY_ROOT` — the downloaded monthly runs, one directory per month
  (`extract.py`, `analyse.py`)
- `OM_SANDBOX` — the downloaded run archives for one domain
  (`accumulation.py`, `drift_profile.py`)

`OM_CACHE` overrides where the per-sounding cache is written; it defaults to
`~/.cache/openmethane`.

```shell
export OM_SANDBOX=/path/to/aust10km
export OM_MONTHLY_ROOT=$OM_SANDBOX/monthly/2024

python src/analysis/model_top_drift/extract.py 06
python src/analysis/model_top_drift/analyse.py 06
python src/analysis/model_top_drift/drift_profile.py --sampled
python src/analysis/model_top_drift/accumulation.py
```

## Where the data comes from

The numbers in #248 are from June and January 2024 on `aust10km`. Under
`s3://om-dev-results`:

| Needed by | Path |
| --- | --- |
| `extract.py`, `analyse.py` | `archive/2026-09-14/aust10km/monthly/2024/{01,06}/` |
| `drift_profile.py` (ICON) | the same prefix, `…/aust10km/daily/2024/06/<dd>/cmaq/…` |
| `accumulation.py` | `archive/2026-09-09/aust10km/daily/2024/06/<dd>/simulobs.pic.gz` |
| `drift_profile.py` (CGRID) | `tests/b46a78d2-f23f-4515-a54a-d69b57ae0aec/run-cmaq/output/CGRID.*.nc` |

That last one is the #244 baseline arm — a forward-only June run with emissions
held at the prior, whose bias correction is byte-identical to the production
monthly run's, and which archived the model state the production run discards.

Laid out locally as `$OM_SANDBOX/{monthly,daily,experiment-244/baseline}`; the
scripts say which directory they wanted if one is missing.

`drift_profile.py` hard-codes the June 2024 window, the `aust10km` file names and
the bias correction that run applied. Generalising it is worth doing the first
time a second month is looked at, and not before.
