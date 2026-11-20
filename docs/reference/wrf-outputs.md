# WRF outputs

The `wrf` command runs the WRF weather model and publishes its output for MCIP,
in CMAQ preprocessing, to read. This page is the contract between the two: what
the WRF step promises, and so what MCIP may rely on. Changing anything here
needs both sides changed together.

Until WRF runs from Open Methane in production
([#316](https://github.com/openmethane/openmethane/issues/316)), setup-wrf writes the
same layout.

## Where the output goes

Everything is under `${STORE_PATH}/wrf/${DOMAIN_NAME}/`, which is `WRF_DIR` and
`GEO_DIR` in CMAQ preprocessing.

| Path | What it holds |
| --- | --- |
| `<YYYYMMDD>00/` | One folder per day of output, named for its first hour |
| `<YYYYMMDD>00/WRFOUT_d01_<YYYY-MM-DD>T<HHMM>Z.nc` | One hour of meteorology for one domain. See below |
| `<YYYYMMDD>00/namelist.wps`, `namelist.input` | The namelists WPS, real.exe and wrf.exe ran with |
| `<YYYYMMDD>00/logs/` | Each program's log |
| `<YYYYMMDD>00/real-rsl/` | real.exe's per-rank logs |
| `<YYYYMMDD>00/rsl.out.*`, `rsl.error.*` | wrf.exe's per-rank logs |
| `geo_em.d01.nc` | The domain's static geography, as geogrid made it. MCIP reads it as `TERRAIN_FILE` |
| `metem/met_em.d01.<YYYY-MM-DD_HH:MM:SS>.nc` | metgrid's output, every 6 hours. Reused by a later run of the same day |

`d01` is WRF's number for the domain in a run. Every run has one domain today,
so it is always `d01`.

## The averaged files

A complete day has **25** files per domain: one for each hour from 00Z on the
day to 00Z on the next day, inclusive.

| Files | Contents |
| --- | --- |
| 00Z to 23Z | Each holds one time step: the mean of the twelve 5-minute frames starting at the labelled time. For 13Z, the mean of 13:00, 13:05, … 13:55 |
| 00Z on the next day | One frame, so its values are instantaneous, not a mean |

The variables are WRF's history output, with the additions and removals in
`src/openmethane/wrf/model_config/add_remove_var.txt`. Each file is netCDF-4;
`float32` variables are compressed with zlib and no others are. `Times` holds
the labelled time, the start of the averaging period.

The day's WRF run starts 12 hours earlier, at 12Z the day before, so the model
has spun up by 00Z. Nothing from the spin-up is published.

## When a day is complete

A day is complete when all 25 averaged files exist for every domain, and no raw
`wrfout_*` file is left beside them, which would mean averaging didn't finish.
`wrf run` exits straight away, without running anything, if every day it was
asked for is complete, unless `FORCE_WRF=true` or `--force` is given.

## After a failure

If any program fails, the WRF step publishes only the logs and the `metem/`
files, and no averaged output, so an incomplete day is never mistaken for a
complete one. A retry reuses the published `metem/` files, and the FNL
analyses in `FNL_CACHE_PATH`. Run outside the image, the scratch folder is
left in place, and a retry also reuses real.exe's output there. In the image,
the entrypoint empties `CHK_PATH` when the command ends.

## Compared with setup-wrf

The values in every averaged file and `met_em` file are identical to
setup-wrf 0.9.2's for the same day: `scripts/wrf/compare_wrf_runs.py` checks
this in CI for au-test. setup-wrf also published its generated shell scripts
(`main.sh`, `run.sh`, `cleanup.sh` and others) and a broken link to
`geo_em.d01.nc` in each day's folder. The WRF step doesn't, and nothing reads
them.
