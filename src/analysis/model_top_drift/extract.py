"""Build a compact per-observation table from an archived monthly run.

Run this first; everything else in this directory reads the cache it writes.

    python3 extract.py 06          # writes ~/.cache/openmethane/misfit_06.npz
    python3 extract.py 01

`OM_MONTHLY_ROOT` points at the downloaded monthly runs, one directory per
month; each month's data is read from `<month>/archive/openmethane`. Two files
are streamed in parallel:

  observed.pickle            the observations, with `value` the retrieved column
  simulobs_first_guess.pic.gz  the same records with `value` replaced by the
                             column simulated from the prior emissions

Every field of the column operator is carried on both files, so the cache keeps
the full per-sounding operator -- averaging kernel, retrieval prior profile,
per-retrieval-layer model coverage and per-CMAQ-layer weights. That is what
makes it possible to ask *where in the column* a misfit lives without running
the model again.

Records are paired by position and the (time, lat, lon) identity is checked on
every record, so a mismatch is an error rather than a silent mispairing.
"""

import gzip
import os
import pathlib
import pickle
import sys

import numpy as np


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
    "sza_proxy",
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
        table.add(
            day=int(str(coord[0])[-2:]),
            step=int(coord[1]),
            row=int(coord[-3]),
            col=int(coord[-2]),
            lat=float(s["latitude_center"]),
            lon=float(s["longitude_center"]),
            obs=float(o["value"]),
            sim=float(s["value"]),
            unc=float(s["uncertainty"]),
            qa=float(s["qa_value"]),
            albedo=float(s["surface_albedo_SWIR"]),
            aod=float(s["aerosol_aod_SWIR"]),
            precision=float(s["ch4_column_precision"]),
            offset=float(o["offset_term"]),
            sza_proxy=0.0,
            avker=np.asarray(s["obs_kernel"], np.float32),
            prior=np.asarray(s["prior_profile"], np.float32),
            cov=np.asarray(s["model_coverage"], np.float32),
            vis=np.asarray(s["model_vis"], np.float32),
        )
        if table.n % 250_000 == 0:
            print(f"{table.n:,}", flush=True)

    data = table.finish()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"misfit_{month}.npz"
    np.savez(out, **data)
    print(f"wrote {out} ({table.n:,} observations)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "06")
