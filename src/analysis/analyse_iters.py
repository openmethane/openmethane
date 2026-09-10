"""
Read the output of a fourdvar run into plain numpy arrays.

A fourdvar archive directory contains, per iteration:

* ``iter####.ncf`` -- the "unknowns" (physical space) at that iteration, a
  netCDF4 file with an ``emis`` and a ``bcon`` group (see
  ``PhysicalAbstractData.archive``).
* ``obs_lite_iter####.pic.gz`` -- the simulated observations at that
  iteration, an "obs-lite" file (see ``ObservationData.archive``).

and, once per run:

* ``observed.pickle`` -- the observations themselves (full obs file, i.e.
  including ``weight_grid``).
* ``simulobs_first_guess.pic.gz`` -- simulated observations for the first
  guess.
* ``prior-emissions.nc`` -- the prior emissions field the run started from,
  on the model grid.

All of the pickle-format files are gzipped streams of separately pickled
objects (``fourdvar.util.file_handle.save_list``): the first object is a dict
of domain attributes, each subsequent object is a dict describing one
observation. They are read here by streaming so that the (large) full
observation file never has to be held in memory at once.
"""

from __future__ import annotations

import argparse
import gzip
import pathlib
import pickle
from collections.abc import Iterator
from typing import Any

import netCDF4
import numpy as np

DEFAULT_RESULTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "work" / "new-results"

ITER_PATTERN = "iter[0-9]*.ncf"
OBS_LITE_PATTERN = "obs_lite_iter[0-9]*.pic.gz"
OBSERVED_NAME = "observed.pickle"
FIRST_GUESS_NAME = "simulobs_first_guess.pic.gz"
PRIOR_NAME = "prior-emissions.nc"


def iteration_files(results_dir: pathlib.Path | str, pattern: str) -> list[pathlib.Path]:
    """
    Return the files matching `pattern` in `results_dir`, in iteration order.

    The iteration number is zero-padded in the filename, so a plain
    lexicographic sort is already iteration order.
    """
    files = sorted(pathlib.Path(results_dir).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no files matching {pattern} in {results_dir}")
    return files


# --- unknowns (iter####.ncf) ------------------------------------------------


def read_unknown_file(
    filename: pathlib.Path | str,
    group: str = "emis",
    species: str = "CH4",
) -> np.ndarray:
    """
    Read one variable from one iteration file, with length-1 dimensions dropped.

    For the ``emis`` group the stored variable has dimensions
    (TSTEP, LAY, ROW, COL); a single-timestep, single-layer run therefore
    squeezes down to (ROW, COL).
    """
    with netCDF4.Dataset(filename, "r") as nc:
        return np.squeeze(np.asarray(nc[group][species][:]))


def read_unknowns(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    group: str = "emis",
    species: str = "CH4",
    pattern: str = ITER_PATTERN,
) -> np.ndarray:
    """
    Read every iteration's unknowns into a single (n_iters, n_rows, n_cols) array.

    Length-1 dimensions of the stored field are squeezed out, so this only
    returns a 3D array for a run with one emission timestep and one layer;
    otherwise the result keeps whatever dimensions survive the squeeze,
    stacked along a leading iteration axis.
    """
    files = iteration_files(results_dir, pattern)
    fields = [read_unknown_file(f, group=group, species=species) for f in files]

    shapes = {f.shape for f in fields}
    if len(shapes) != 1:
        raise ValueError(f"iteration files disagree on shape: {shapes}")

    return np.stack(fields, axis=0)


# --- observations (pickle format) ------------------------------------------


def stream_pickled_list(filename: pathlib.Path | str) -> Iterator[Any]:
    """
    Yield the objects of a gzipped pickle-stream file one at a time.

    This is the streaming equivalent of
    ``fourdvar.util.file_handle.load_list``, which builds the whole list in
    memory; the full observation file is too large for that to be comfortable.
    """
    with gzip.open(filename, "rb") as f:
        while True:
            try:
                yield pickle.load(f, encoding="latin1")  # noqa: S301
            except EOFError:
                return


def _as_array(values: list[Any]) -> np.ndarray:
    """
    Pack a list of per-observation values into an array of length n_obs.

    Tuples are kept as tuples in an object array; numpy would otherwise
    broadcast them into a second axis and, for a mixed tuple such as
    ``lite_coord``, cast the integers to strings.
    """
    if values and isinstance(values[0], tuple):
        array = np.empty(len(values), dtype=object)
        array[:] = values
        return array
    return np.array(values)


def read_obs_domain(filename: pathlib.Path | str) -> dict[str, Any]:
    """Return the domain attributes stored as the first record of an obs file."""
    return next(stream_pickled_list(filename))


def read_obs_fields(
    filename: pathlib.Path | str,
    fields: tuple[str, ...] = ("value",),
) -> dict[str, np.ndarray]:
    """
    Read the named per-observation fields out of one observation file.

    The first record of the file is the domain description and is skipped.
    Each returned array has length n_obs, in file order (which is the same
    order in every file of a run, so values from different iterations line
    up element by element).
    """
    collected: dict[str, list[Any]] = {name: [] for name in fields}

    for index, record in enumerate(stream_pickled_list(filename)):
        if index == 0:  # domain attributes
            continue
        for name in fields:
            collected[name].append(record[name])

    return {name: _as_array(values) for name, values in collected.items()}


def read_simulated_obs(filename: pathlib.Path | str) -> np.ndarray:
    """Read the simulated observation values from one obs-lite file."""
    return read_obs_fields(filename, fields=("value",))["value"]


def read_simulations(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    pattern: str = OBS_LITE_PATTERN,
) -> np.ndarray:
    """
    Read every iteration's simulated observations into an (n_iters, n_obs) array.
    """
    files = iteration_files(results_dir, pattern)
    simulations = [read_simulated_obs(f) for f in files]

    lengths = {s.size for s in simulations}
    if len(lengths) != 1:
        raise ValueError(f"iterations disagree on the number of observations: {lengths}")

    return np.stack(simulations, axis=0)


def read_observations(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    fields: tuple[str, ...] = ("value", "uncertainty", "lite_coord", "time"),
    name: str = OBSERVED_NAME,
) -> dict[str, np.ndarray]:
    """
    Read the observations themselves from `observed.pickle`.

    Only the requested fields are retained, so the ``weight_grid`` of each
    observation is unpickled and discarded rather than accumulated.
    """
    return read_obs_fields(pathlib.Path(results_dir) / name, fields=fields)


def read_first_guess(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    name: str = FIRST_GUESS_NAME,
) -> np.ndarray:
    """Read the first-guess simulated observations as an (n_obs,) array."""
    return read_simulated_obs(pathlib.Path(results_dir) / name)


# --- prior emissions (prior-emissions.nc) -----------------------------------


def read_prior(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    name: str = PRIOR_NAME,
    variable: str = "ch4_total",
) -> dict[str, np.ndarray]:
    """
    Read the prior emissions field and its grid coordinates.

    The stored flux has dimensions (time, vertical, y, x); squeezing out the
    single vertical level leaves (n_times, n_rows, n_cols), and `lat` and
    `lon` are the (n_rows, n_cols) cell-centre coordinates of that same grid.

    Returns a dict with

    * ``ch4_total`` -- (n_times, n_rows, n_cols) (named after `variable`)
    * ``ch4_total_mean`` -- the time mean, (n_rows, n_cols)
    * ``lat``, ``lon`` -- (n_rows, n_cols)

    The time mean is a plain unweighted mean over axis 0, so a missing value
    anywhere in a cell's time series propagates to that cell.
    """
    with netCDF4.Dataset(pathlib.Path(results_dir) / name, "r") as nc:
        nc.set_auto_mask(False)  # keep the NaN fill value rather than masking
        field = np.squeeze(np.asarray(nc[variable][:]))
        latitude = np.squeeze(np.asarray(nc["lat"][:]))
        longitude = np.squeeze(np.asarray(nc["lon"][:]))

    return {
        variable: field,
        f"{variable}_mean": field.mean(axis=0),
        "lat": latitude,
        "lon": longitude,
    }


# --- selecting observations by location -------------------------------------


def read_obs_locations(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    name: str = OBSERVED_NAME,
) -> dict[str, np.ndarray]:
    """
    Read the centre latitude and longitude of each observation.

    Any of the observation files carries these, and they are in the same
    order in all of them; `observed.pickle` is used by default.
    """
    return read_obs_fields(
        pathlib.Path(results_dir) / name,
        fields=("latitude_center", "longitude_center"),
    )


def indices_within_radius(
    latitude: np.ndarray,
    longitude: np.ndarray,
    point: tuple[float, float],
    radius: float,
) -> np.ndarray:
    """
    Return the indices of the points within `radius` of `point`.

    Distance is Euclidean in latitude-longitude space and `radius` is in
    degrees: this is a cheap selection, not a great-circle distance, so the
    region it picks out is narrower on the ground in longitude than in
    latitude, increasingly so away from the equator. Longitude differences
    are wrapped into [-180, 180) so a point near the dateline still works.

    Parameters
    ----------
    latitude, longitude
        Coordinates of the points to search, in degrees. Any matching shape
        will do; the returned indices index the flattened arrays.
    point
        The (latitude, longitude) centre of the search, in degrees.
    radius
        Search radius, in degrees.

    Returns
    -------
        Integer indices of the points within the radius, in increasing order.
    """
    centre_latitude, centre_longitude = point

    delta_latitude = np.ravel(np.asarray(latitude, dtype=float)) - centre_latitude
    delta_longitude = np.ravel(np.asarray(longitude, dtype=float)) - centre_longitude
    delta_longitude = (delta_longitude + 180.0) % 360.0 - 180.0

    within = delta_latitude**2 + delta_longitude**2 <= radius**2

    return np.flatnonzero(within)


def observations_within_radius(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    point: tuple[float, float] = (0.0, 0.0),
    radius: float = 1.0,
    name: str = OBSERVED_NAME,
) -> np.ndarray:
    """
    Return the indices of the observations within `radius` degrees of `point`.

    The indices are positions along the n_obs axis, so they can be used
    directly on the arrays returned by `read_simulations`, `read_observations`
    and `read_first_guess`.
    """
    locations = read_obs_locations(results_dir, name=name)

    return indices_within_radius(
        locations["latitude_center"],
        locations["longitude_center"],
        point,
        radius,
    )


def read_run(
    results_dir: pathlib.Path | str = DEFAULT_RESULTS_DIR,
    group: str = "emis",
    species: str = "CH4",
    prior_name: str | None = PRIOR_NAME,
) -> dict[str, Any]:
    """
    Read everything: unknowns, simulations, observations, first guess and prior.

    Returns a dict with

    * ``unknowns`` -- (n_iters, n_rows, n_cols)
    * ``simulations`` -- (n_iters, n_obs)
    * ``first_guess`` -- (n_obs,)
    * ``observed`` / ``uncertainty`` / ``lite_coord`` / ``time`` -- (n_obs,)
    * ``latitude`` / ``longitude`` -- (n_obs,), the observation centres
    * ``prior_ch4_total`` -- (n_times, n_rows, n_cols), with
      ``prior_ch4_total_mean``, ``prior_lat`` and ``prior_lon`` on the grid.
      Pass ``prior_name=None`` to skip the prior file.
    """
    unknowns = read_unknowns(results_dir, group=group, species=species)
    simulations = read_simulations(results_dir)
    observations = read_observations(
        results_dir,
        fields=(
            "value",
            "uncertainty",
            "lite_coord",
            "time",
            "latitude_center",
            "longitude_center",
        ),
    )
    first_guess = read_first_guess(results_dir)

    n_obs = simulations.shape[1]
    for label, array in (
        ("observed.pickle", observations["value"]),
        (FIRST_GUESS_NAME, first_guess),
    ):
        if array.size != n_obs:
            raise ValueError(
                f"{label} has {array.size} observations, " f"but the obs-lite files have {n_obs}"
            )

    run = {
        "unknowns": unknowns,
        "simulations": simulations,
        "first_guess": first_guess,
        "observed": observations["value"],
        "uncertainty": observations["uncertainty"],
        "lite_coord": observations["lite_coord"],
        "time": observations["time"],
        "latitude": observations["latitude_center"],
        "longitude": observations["longitude_center"],
    }

    if prior_name is not None:
        prior = read_prior(results_dir, name=prior_name)
        run.update({f"prior_{name}": array for name, array in prior.items()})

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results_dir",
        nargs="?",
        default=DEFAULT_RESULTS_DIR,
        type=pathlib.Path,
        help=f"fourdvar archive directory (default: {DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument("--group", default="emis", help="netCDF group of the unknowns")
    parser.add_argument("--species", default="CH4", help="species to read")
    parser.add_argument(
        "--point",
        nargs=2,
        type=float,
        metavar=("LAT", "LON"),
        help="report how many observations lie within --radius of this point",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=1.0,
        help="search radius in degrees, used with --point (default: 1)",
    )
    args = parser.parse_args()

    run = read_run(args.results_dir, group=args.group, species=args.species)
    for name, array in run.items():
        print(f"{name}: shape {array.shape} dtype {array.dtype}")

    if args.point is not None:
        point = (args.point[0], args.point[1])
        selected = indices_within_radius(run["latitude"], run["longitude"], point, args.radius)
        print(
            f"{selected.size} observations within {args.radius} degrees of "
            f"{point}, first indices {selected[:5]}"
        )


if __name__ == "__main__":
    main()
