# Aerosol bias diagnostics

The scripts behind
[#249](https://github.com/openmethane/openmethane/issues/249): the observed
columns in our TropOMI files fall about 290 ppb per unit of retrieved SWIR
aerosol optical depth while the simulated columns do not move. #249 establishes
that the dependence belongs to the retrieval rather than to the model, but
leaves open whether it is the retrieval being wrong or real methane that
happens to anti-correlate with aerosol.

Like everything under `src/analysis`, these are diagnostics rather than pipeline
code. They read archived run output on the host; none of them run inside the
container or touch a live run.

## What each one answers

| | |
| --- | --- |
| `light_path.py <month> [<month>]` | Whether the aerosol dependence scales with the length of the light path. It does. |

## The argument

Aerosol biases a shortwave retrieval by changing how far the sunlight
travelled. How much of the light it diverts depends on the optical depth along
the slant path rather than straight up, so per unit of the *vertical* optical
depth the retrieval reports, the artefact has to grow with the air mass factor.
Methane in the air carries no such dependence: a plume is the same plume
whether it is viewed from directly overhead or from the edge of the swath.

The viewing half of the air mass factor makes the decisive test, because which
detector column saw a sounding has nothing to do with where the sounding is.
Binning by viewing zenith angle therefore varies the light path with the
geography, the land cover and the sources all left alone.

Both zenith angles have to be reconstructed, because the observation files drop
the ones the retrieval reported; `../sounding_geometry.py` does that and says
how accurately.

## Pointing it at data

`light_path.py` reads only the per-sounding cache that `../sounding_cache.py`
writes, so that has to run first:

```shell
export OM_MONTHLY_ROOT=/path/to/aust10km/monthly/2024

python src/analysis/sounding_cache.py 06
python src/analysis/sounding_cache.py 01
python src/analysis/aerosol_bias/light_path.py 06 01
```

`OM_MONTHLY_ROOT` points at the downloaded monthly runs, one directory per
month; each month's data is read from `<month>/archive/openmethane`. The June
and January 2024 `aust10km` runs the numbers come from are under
`s3://om-dev-results/archive/2026-09-14/aust10km/monthly/2024/{01,06}/`.

`OM_CACHE` overrides where the cache is written and read; it defaults to
`~/.cache/openmethane`.
