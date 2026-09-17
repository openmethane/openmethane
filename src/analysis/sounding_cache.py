"""Build a compact per-sounding table from an archived monthly run.

    python3 src/analysis/sounding_cache.py 06   # ~/.cache/openmethane/soundings_06.npz
    python3 src/analysis/sounding_cache.py 01

A monthly run's observations are millions of pickled records carrying the whole
column operator each, which is minutes of streaming to read and far too much to
hold in memory. This flattens a month into one `.npz` of parallel arrays, so
that anything asking a question of the residuals reads it in a second or two
rather than re-streaming the run.

`OM_MONTHLY_ROOT` points at the downloaded monthly runs, one directory per
month; each month's data is read from `<month>/archive/openmethane`. Two files
are streamed in parallel:

  observed.pickle            the observations, with `value` the retrieved column
  simulobs_first_guess.pic.gz  the same records with `value` replaced by the
                             column simulated from the prior emissions

Records are paired by position and the (time, lat, lon) identity is checked on
every record, so a mismatch is an error rather than a silent mispairing.

What each sounding keeps:

  lat lon day step row col     where and when, and the grid cell it fell in
  obs sim unc                  retrieved column, simulated column, uncertainty
  qa albedo aod precision      the retrieval's own quality and scene properties
  offset                       the operator's additive term
  sza across_km along_km       geometry, reconstructed by `sounding_geometry`
  avker prior cov              the averaging kernel, retrieval prior profile and
                               per-retrieval-layer model coverage
  vis                          per-CMAQ-layer weights

Keeping the whole operator rather than a summary is what makes it possible to
ask *where in the column* a residual lives without running the model again. It
costs about 500 MB a month.

`OM_CACHE` overrides where the cache is written; it defaults to
`~/.cache/openmethane`.
"""

import gzip
import os
import pathlib
import pickle
import sys

import numpy as np

from analysis.sounding_geometry import footprint, solar_zenith


def _required_dir(variable, what):
    """Resolve a directory the caller has to point at, or say so clearly."""
    value = os.environ.get(variable)
    if not value:
        raise SystemExit(
            f"set {variable} to {what}. See README.md in this directory for the "
            "archive paths these are downloaded from."
        )
    path = pathlib.Path(value)
    if not path.is_dir():
        raise SystemExit(f"{variable}={value} is not a directory")
    return path


CACHE_DIR = pathlib.Path(os.environ.get("OM_CACHE", pathlib.Path.home() / ".cache/openmethane"))

N_SAT = 12
N_MOD = 32
CHUNK = 200_000

SCALARS = (
    "lat",
    "lon",
    "obs",
    "sim",
    "unc",
    "qa",
    "albedo",
    "aod",
    "precision",
    "offset",
    "sza",
    "across_km",
    "along_km",
)
INTS = ("day", "step", "row", "col")


def stream(path):
    with gzip.open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f, encoding="latin1")  # noqa: S301
            except EOFError:
                return


class Table:
    """Grows in preallocated blocks; cheaper than a list of 1.5M small arrays."""

    def __init__(self):
        self.blocks = []
        self._new_block()
        self.n = 0

    def _new_block(self):
        self.cur = {name: np.empty(CHUNK, np.float32) for name in SCALARS}
        self.cur.update({name: np.empty(CHUNK, np.int32) for name in INTS})
        self.cur["avker"] = np.empty((CHUNK, N_SAT), np.float32)
        self.cur["prior"] = np.empty((CHUNK, N_SAT), np.float32)
        self.cur["cov"] = np.empty((CHUNK, N_SAT), np.float32)
        self.cur["vis"] = np.empty((CHUNK, N_MOD), np.float32)
        self.i = 0

    def add(self, **kwargs):
        for name, value in kwargs.items():
            self.cur[name][self.i] = value
        self.i += 1
        self.n += 1
        if self.i == CHUNK:
            self.blocks.append({k: v[: self.i] for k, v in self.cur.items()})
            self._new_block()

    def finish(self):
        if self.i:
            self.blocks.append({k: v[: self.i] for k, v in self.cur.items()})
        keys = self.blocks[0].keys()
        return {k: np.concatenate([b[k] for b in self.blocks]) for k in keys}


def identity(record):
    return (
        record["time"],
        round(float(record["latitude_center"]), 6),
        round(float(record["longitude_center"]), 6),
    )


def main(month):
    root = _required_dir("OM_MONTHLY_ROOT", "the archived monthly runs, one directory per month")
    archive = root / month / "archive" / "openmethane"
    observed = archive / "observed.pickle"
    simulated = archive / "simulobs_first_guess.pic.gz"
    for path in (observed, simulated):
        if not path.exists():
            sys.exit(f"missing {path}")

    obs_stream = stream(observed)
    sim_stream = stream(simulated)
    next(obs_stream)
    next(sim_stream)

    table = Table()
    for i, (o, s) in enumerate(zip(obs_stream, sim_stream)):
        if identity(o) != identity(s):
            raise ValueError(f"record {i}: observed and simulated files disagree on identity")
        coord = s["lite_coord"]
        latitude, longitude = float(s["latitude_center"]), float(s["longitude_center"])
        sza = solar_zenith(s["time"], latitude, longitude)
        across, along = footprint(
            s["latitude_corners"], s["longitude_corners"], latitude, longitude
        )
        table.add(
            day=int(str(coord[0])[-2:]),
            step=int(coord[1]),
            row=int(coord[-3]),
            col=int(coord[-2]),
            lat=latitude,
            lon=longitude,
            obs=float(o["value"]),
            sim=float(s["value"]),
            unc=float(s["uncertainty"]),
            qa=float(s["qa_value"]),
            albedo=float(s["surface_albedo_SWIR"]),
            aod=float(s["aerosol_aod_SWIR"]),
            precision=float(s["ch4_column_precision"]),
            offset=float(o["offset_term"]),
            sza=sza,
            across_km=across,
            along_km=along,
            avker=np.asarray(s["obs_kernel"], np.float32),
            prior=np.asarray(s["prior_profile"], np.float32),
            cov=np.asarray(s["model_coverage"], np.float32),
            vis=np.asarray(s["model_vis"], np.float32),
        )
        if table.n % 250_000 == 0:
            print(f"{table.n:,}", flush=True)

    data = table.finish()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"soundings_{month}.npz"
    np.savez(out, **data)
    print(f"wrote {out} ({table.n:,} observations)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "06")
