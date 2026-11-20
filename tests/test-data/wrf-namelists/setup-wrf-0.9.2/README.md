# setup-wrf's namelists, for parity tests

`namelist.wps` and `namelist.input` as setup-wrf wrote them for the window
keeping 2022-12-07 (12 hours of spin-up from 2022-12-06 12Z, to 2022-12-08 00Z),
for au-test v1 and aust10km v1.

They come from `ghcr.io/openmethane/setup-wrf:0.9.2`
(`sha256:9b0e66ac400b216563b7da3555363db393c21c6e437e544a4644ae36e276c95e`,
commit 5e357ff), the version production runs. It was run with
`config/config.docker.full.json` as `scripts/run-wrf.sh` runs it, up to and
including real.exe. `geog_data_path` is `'TEMPLATE'` because geogrid didn't run.

The level counts in `namelist.input` (34 atmospheric, 4 soil) are read from
the met_em files of FNL 0.25° analyses.

Used by `tests/unit/wrf/test_namelists.py`. Delete them once setup-wrf is
archived (#324).
