"""Map between boundary-condition offset unknowns and the CMAQ BCON grid.

The 4D-Var boundary unknowns are additive offsets, in ppm, on the lateral
boundary condition CMAQ reads. Each unknown covers one region of the boundary
(a set of perimeter cells and layers) for one control time step. Neither the
regions nor the steps need be the same size.

The map is held in a netCDF file (see `build_bcon_map`), written by
`scripts/cmaq_preprocess/make_bcon_map.py` and copied into the prior:

- `BCON_REGION[LAY, PERIM]`: region index of each BCON cell, -1 for none.
- `STEP_START[STEP]`, `STEP_END[STEP]`: control step boundaries.
- `BCON_UNC[STEP, REGION]`: prior 1-sigma uncertainty of each offset, in ppm.

The functions here have no knowledge of fourdvar, so the expansion E (offsets
to a BCON-shaped field) and its adjoint can be tested directly.

Perimeter layout (I/O API `BNDARY3`, `NTHIK = 1`): South, East, North, West.
South holds columns 1..NCOLS+1 of row 0, East rows 1..NROWS+1 of column
NCOLS+1, North columns 0..NCOLS of row NROWS+1 and West rows 0..NROWS of
column 0 (1-based interior indices), so each side carries one corner and the
four corners are never read by horizontal advection.
"""

import datetime
import itertools
import pathlib
from collections.abc import Sequence

import netCDF4
import numpy as np
import pyproj
import xarray as xr

EDGES = ("S", "E", "N", "W")
REMAINDER_RULES = ("spread", "end")
# matches openmethane.obs_preprocess.model_space and CMAQ/WRF
EARTH_RADIUS = 6370000.0


def split_length(
    total: int, target: int, remainder: str = "spread", min_fraction: float = 0.0
) -> list[int]:
    """Split `total` units into pieces of about `target` units.

    remainder="spread" uses the nearest whole number of pieces (rounding
    half up), sized as equally as possible: 31 by 5 -> 5,5,5,5,5,6.
    remainder="end" uses full-length pieces plus one shorter piece at the
    end: 31 by 5 -> 5,5,5,5,5,5,1. With "end", a leftover shorter than
    `min_fraction * target` is merged into the previous piece instead.
    A target of at least `total` gives a single piece.
    """
    if total < 1:
        raise ValueError(f"cannot split a length of {total}")
    if target < 1:
        raise ValueError(f"target piece length must be at least 1, got {target}")
    if remainder not in REMAINDER_RULES:
        raise ValueError(f"remainder must be one of {REMAINDER_RULES}, got {remainder!r}")
    if target >= total:
        return [total]

    nfull, leftover = divmod(total, target)

    if remainder == "end":
        pieces = [target] * nfull
        if leftover >= max(min_fraction * target, 1):
            pieces.append(leftover)
        else:
            pieces[-1] += leftover
        return pieces

    npiece = nfull + 1 if 2 * leftover >= target else nfull
    base, extra = divmod(total, npiece)
    # longer pieces go last, so the run's final step absorbs the extra days
    return [base] * (npiece - extra) + [base + 1] * extra


def perimeter_size(ncols: int, nrows: int) -> int:
    return 2 * (ncols + nrows) + 4


def perimeter_edges(ncols: int, nrows: int) -> list[np.ndarray]:
    """Perimeter indices of the non-corner cells of each edge (S, E, N, W).

    Each array is ordered by increasing column (S, N) or row (E, W).
    """
    off_s = 0
    off_e = ncols + 1
    off_n = ncols + nrows + 2
    off_w = 2 * ncols + nrows + 3
    return [
        off_s + np.arange(ncols),
        off_e + np.arange(nrows),
        off_n + 1 + np.arange(ncols),
        off_w + 1 + np.arange(nrows),
    ]


def corner_indices(ncols: int, nrows: int) -> np.ndarray:
    off_e = ncols + 1
    off_n = ncols + nrows + 2
    off_w = 2 * ncols + nrows + 3
    return np.array([off_e - 1, off_n - 1, off_n, off_w])


def perimeter_cell_xy(ncols: int, nrows: int) -> tuple[np.ndarray, np.ndarray]:
    """0-based (column, row) of each perimeter cell, -1 or NCOLS/NROWS outside the grid."""
    col = np.concatenate(
        [
            np.arange(ncols + 1),  # S: cols 0..NCOLS (0-based), row -1
            np.full(nrows + 1, ncols),  # E: col NCOLS, rows 0..NROWS
            np.arange(-1, ncols),  # N: cols -1..NCOLS-1, row NROWS
            np.full(nrows + 1, -1),  # W: col -1, rows -1..NROWS-1
        ]
    )
    row = np.concatenate(
        [
            np.full(ncols + 1, -1),
            np.arange(nrows + 1),
            np.full(ncols + 1, nrows),
            np.arange(-1, nrows),
        ]
    )
    return col, row


def equal_mass_bands(vglvls: Sequence[float], nbands: int) -> list[int]:
    """0-based start layer of each of `nbands` bands holding about equal air mass.

    `vglvls` are the NLAYS+1 layer interfaces in CMAQ's sigma-p coordinate, so
    each layer's mass is proportional to its thickness in sigma. Band edges are
    placed at the interfaces nearest to the cumulative-mass quantiles.
    """
    sigma = np.asarray(vglvls, dtype=float)
    thick = sigma[:-1] - sigma[1:]
    nlays = thick.size
    if not 1 <= nbands <= nlays:
        raise ValueError(f"nbands must be between 1 and {nlays}, got {nbands}")
    if (thick <= 0).any():
        raise ValueError("VGLVLS must decrease monotonically")
    cum = np.concatenate([[0.0], np.cumsum(thick)]) / thick.sum()

    starts = [0]
    for i in range(1, nbands):
        # interfaces 1..nlays-1 are the candidate band edges; keep each band at
        # least one layer thick and leave room for the bands still to come
        lo = starts[-1] + 1
        hi = nlays - (nbands - i)
        candidates = np.arange(lo, hi + 1)
        best = candidates[np.argmin(np.abs(cum[candidates] - i / nbands))]
        starts.append(int(best))
    return starts


def band_index(nlays: int, band_starts: Sequence[int]) -> np.ndarray:
    """Band of each layer, from the 0-based start layer of each band."""
    starts = list(band_starts)
    if not starts or starts[0] != 0:
        raise ValueError("the first band must start at layer 0")
    if any(b <= a for a, b in itertools.pairwise(starts)) or starts[-1] >= nlays:
        raise ValueError(f"band starts {starts} must increase and lie within {nlays} layers")
    band = np.zeros(nlays, dtype=int)
    for start in starts[1:]:
        band[start:] += 1
    return band


def _split_cells(cells: np.ndarray, target: int, remainder: str, min_fraction: float):
    lengths = split_length(cells.size, target, remainder, min_fraction)
    return np.split(cells, np.cumsum(lengths)[:-1])


def build_region_map(  # noqa: PLR0913
    ncols: int,
    nrows: int,
    nlays: int,
    segment_cells_x: int,
    segment_cells_y: int,
    band_starts: Sequence[int],
    remainder: str = "spread",
    min_fraction: float = 0.0,
    wrap: bool = False,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Build the `BCON_REGION[LAY, PERIM]` map and a description of each region.

    Segments are cut along each edge separately, so no region crosses a
    corner, unless `wrap` is set, in which case the non-corner perimeter is cut
    as one loop, counter-clockwise from the south-west corner. Regions are
    numbered by edge (S, E, N, W), then segment, then band from the surface up.
    """
    edges = perimeter_edges(ncols, nrows)
    if wrap:
        # counter-clockwise: S west to east, E south to north, N east to west,
        # W north to south
        loop = np.concatenate([edges[0], edges[1], edges[2][::-1], edges[3][::-1]])
        segments = [
            (-1, seg) for seg in _split_cells(loop, segment_cells_x, remainder, min_fraction)
        ]
    else:
        segments = []
        for edge, cells in enumerate(edges):
            target = segment_cells_x if EDGES[edge] in ("S", "N") else segment_cells_y
            segments += [
                (edge, seg) for seg in _split_cells(cells, target, remainder, min_fraction)
            ]

    band = band_index(nlays, band_starts)
    nbands = band.max() + 1
    region_map = np.full((nlays, perimeter_size(ncols, nrows)), -1, dtype=np.int32)

    info: dict[str, list] = {
        "REGION_EDGE": [],
        "REGION_SEGMENT": [],
        "REGION_BAND": [],
        "REGION_NCELLS": [],
        "REGION_LAY_START": [],
        "REGION_LAY_END": [],
        "REGION_PERIM_FIRST": [],
        "REGION_PERIM_LAST": [],
    }
    region = 0
    seg_count: dict[int, int] = {}
    for edge, cells in segments:
        seg_num = seg_count.get(edge, 0)
        seg_count[edge] = seg_num + 1
        for b in range(nbands):
            lays = np.flatnonzero(band == b)
            region_map[np.ix_(lays, cells)] = region
            info["REGION_EDGE"].append(edge)
            info["REGION_SEGMENT"].append(seg_num)
            info["REGION_BAND"].append(b)
            info["REGION_NCELLS"].append(cells.size)
            # 1-based, inclusive, as CMAQ numbers layers
            info["REGION_LAY_START"].append(lays[0] + 1)
            info["REGION_LAY_END"].append(lays[-1] + 1)
            info["REGION_PERIM_FIRST"].append(cells[0])
            info["REGION_PERIM_LAST"].append(cells[-1])
            region += 1
    return region_map, {k: np.array(v, dtype=np.int32) for k, v in info.items()}


def build_steps(
    total_hours: int, step_hours: int, remainder: str = "spread", min_fraction: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Control step boundaries, in seconds from the start of the run."""
    lengths = np.array(split_length(total_hours, step_hours, remainder, min_fraction)) * 3600
    end = np.cumsum(lengths)
    return end - lengths, end


def record_steps(
    record_seconds: np.ndarray | None, step_start: np.ndarray, step_end: np.ndarray
) -> np.ndarray:
    """Control step of each BCON record.

    `record_seconds` is each record's time in seconds from the start of the
    run, or None for a time-independent BCON file, which only works with a
    single control step. A record belongs to the step containing it; records
    before the run go to the first step and records at or after the run end to
    the last, so the 24:00 record of a daily file and the 00:00 record of the
    next day's file can land in different steps, each consistent with its own
    file.
    """
    step_start = np.asarray(step_start)
    step_end = np.asarray(step_end)
    if record_seconds is None:
        if step_start.size != 1:
            raise ValueError(
                "a time-independent BCON file (TSTEP = 0) can only be used with a single "
                f"boundary control step, but the map has {step_start.size}"
            )
        return np.zeros(1, dtype=int)
    steps = np.searchsorted(step_start, np.asarray(record_seconds), side="right") - 1
    return np.clip(steps, 0, step_start.size - 1)


def expand(x: np.ndarray, region_map: np.ndarray, rec_step: np.ndarray) -> np.ndarray:
    """E: offsets x[STEP, REGION] -> field[REC, LAY, PERIM], zero outside every region."""
    # an extra zero column, which region index -1 picks up
    padded = np.concatenate([np.asarray(x, dtype=float), np.zeros((x.shape[0], 1))], axis=1)
    return padded[np.asarray(rec_step)][:, region_map]


def collapse(
    field: np.ndarray, region_map: np.ndarray, rec_step: np.ndarray, nstep: int, nregion: int
) -> np.ndarray:
    """E transpose: field[REC, LAY, PERIM] -> g[STEP, REGION], summing over each region."""
    g = np.zeros((nstep, nregion + 1))
    shape = field.shape
    steps = np.broadcast_to(np.asarray(rec_step)[:, None, None], shape)
    regions = np.broadcast_to(region_map[None, :, :], shape)
    np.add.at(g, (steps, regions), np.asarray(field, dtype=float))
    return g[:, :nregion]


def accumulate_minimum(
    current: np.ndarray, field: np.ndarray, region_map: np.ndarray, rec_step: np.ndarray
) -> None:
    """Fold field[REC, LAY, PERIM] into the running minimum current[STEP, REGION], in place."""
    padded = np.concatenate([current, np.full((current.shape[0], 1), np.inf)], axis=1)
    shape = field.shape
    steps = np.broadcast_to(np.asarray(rec_step)[:, None, None], shape)
    regions = np.broadcast_to(region_map[None, :, :], shape)
    np.minimum.at(padded, (steps, regions), np.asarray(field, dtype=float))
    current[:] = padded[:, :-1]


def validate_map(  # noqa: PLR0913
    region_map: np.ndarray,
    step_start: np.ndarray,
    step_end: np.ndarray,
    unc: np.ndarray,
    run_seconds: int,
    nlays: int,
    ncols: int,
    nrows: int,
) -> None:
    """Raise ValueError unless the map is consistent with itself, the grid and the run."""
    nperim = perimeter_size(ncols, nrows)
    if region_map.shape != (nlays, nperim):
        raise ValueError(
            f"BCON_REGION has shape {region_map.shape}, expected (LAY, PERIM) = ({nlays}, {nperim})"
        )
    if region_map.min() < -1:
        raise ValueError("BCON_REGION values must be -1 or a region index")
    nregion = int(region_map.max()) + 1
    if nregion < 1:
        raise ValueError("BCON_REGION assigns no cell to a region")
    present = np.unique(region_map[region_map >= 0])
    if present.size != nregion:
        missing = sorted(set(range(nregion)) - set(present.tolist()))
        raise ValueError(f"BCON_REGION region indices must be contiguous, missing {missing}")
    interior = np.ones(nperim, dtype=bool)
    interior[corner_indices(ncols, nrows)] = False
    gaps = np.argwhere((region_map < 0) & interior[None, :])
    if gaps.size:
        lay, perim = gaps[0]
        raise ValueError(
            f"{len(gaps)} non-corner boundary cells are in no region, "
            f"the first at layer {lay + 1}, perimeter cell {perim}"
        )

    step_start = np.asarray(step_start)
    step_end = np.asarray(step_end)
    if step_start.ndim != 1 or step_start.shape != step_end.shape or step_start.size < 1:
        raise ValueError("STEP_START and STEP_END must be 1-D and the same length")
    if step_start[0] != 0 or step_end[-1] != run_seconds:
        raise ValueError(
            f"control steps must cover the run: they span {step_start[0]} to {step_end[-1]} "
            f"seconds from the start, but the run is {run_seconds} seconds long"
        )
    if (step_end <= step_start).any() or (step_start[1:] != step_end[:-1]).any():
        raise ValueError("control steps must be contiguous and of positive length")

    if unc.shape != (step_start.size, nregion):
        raise ValueError(
            f"BCON_UNC has shape {unc.shape}, expected (STEP, REGION) = "
            f"({step_start.size}, {nregion})"
        )
    if not (np.isfinite(unc).all() and (unc > 0).all()):
        raise ValueError("BCON_UNC must be finite and positive")


def ioapi_record_seconds(
    sdate: int, stime: int, tstep: int, nrec: int, run_start: datetime.date
) -> np.ndarray | None:
    """Time of each record of an I/O API file, in seconds from `run_start` 00:00.

    Returns None for a time-independent file (TSTEP = 0).
    """
    if tstep == 0:
        return None

    def hms(value):
        return 3600 * (value // 10000) + 60 * ((value // 100) % 100) + value % 100

    first = datetime.datetime.strptime(f"{sdate:07d}", "%Y%j") + datetime.timedelta(
        seconds=hms(stime)
    )
    origin = datetime.datetime.combine(run_start, datetime.time())
    offset = (first - origin).total_seconds()
    return offset + hms(tstep) * np.arange(nrec)


def file_record_seconds(path: str | pathlib.Path, run_start: datetime.date) -> np.ndarray | None:
    """Record times of an I/O API BCON (or ADJ_LGRID_BC) file, see `ioapi_record_seconds`."""
    with netCDF4.Dataset(path) as nc:
        return ioapi_record_seconds(
            int(nc.SDATE), int(nc.STIME), int(nc.TSTEP), len(nc.dimensions["TSTEP"]), run_start
        )


def _region_lonlat(attrs: dict, region_map: np.ndarray, ncols: int, nrows: int, nregion: int):
    """Mean longitude and latitude of each region's perimeter cells."""
    col, row = perimeter_cell_xy(ncols, nrows)
    x = attrs["XORIG"] + (col + 0.5) * attrs["XCELL"]
    y = attrs["YORIG"] + (row + 0.5) * attrs["YCELL"]
    lon = np.full(nregion, np.nan)
    lat = np.full(nregion, np.nan)
    if int(attrs["GDTYP"]) != 2:
        return lon, lat
    proj = pyproj.Proj(
        proj="lcc",
        lat_1=float(attrs["P_ALP"]),
        lat_2=float(attrs["P_BET"]),
        lat_0=float(attrs["YCENT"]),
        lon_0=float(attrs["P_GAM"]),
        a=EARTH_RADIUS,
        b=EARTH_RADIUS,
    )
    for r in range(nregion):
        cells = np.flatnonzero((region_map == r).any(axis=0))
        lon[r], lat[r] = proj(x[cells].mean(), y[cells].mean(), inverse=True)
    return lon, lat


def build_bcon_map(  # noqa: PLR0913
    bcon_file: str | pathlib.Path,
    start_date: datetime.date,
    end_date: datetime.date,
    segment_km: float = 1000.0,
    step_days: float = 5.0,
    nbands: int = 4,
    remainder: str = "spread",
    min_fraction: float = 0.0,
    unc: float = 0.02,
    layer_bands: Sequence[int] | None = None,
    wrap: bool = False,
) -> xr.Dataset:
    """Build a boundary map for the run `start_date` to `end_date` (inclusive).

    `layer_bands` gives explicit 1-based start layers for the vertical bands
    (e.g. [1, 16]) and overrides `nbands`. `unc` is the prior 1-sigma offset in
    ppm, applied to every region and step.
    """
    with netCDF4.Dataset(bcon_file) as nc:
        attrs = {k: nc.getncattr(k) for k in nc.ncattrs()}
    ncols, nrows, nlays = int(attrs["NCOLS"]), int(attrs["NROWS"]), int(attrs["NLAYS"])
    if int(attrs.get("NTHIK", 1)) != 1:
        raise ValueError(f"{bcon_file}: only NTHIK = 1 boundary files are supported")

    if layer_bands is None:
        band_starts = equal_mass_bands(attrs["VGLVLS"], nbands)
    else:
        band_starts = [int(b) - 1 for b in layer_bands]

    def to_cells(cell_size):
        return max(1, round(segment_km * 1000.0 / float(cell_size)))

    region_map, info = build_region_map(
        ncols,
        nrows,
        nlays,
        segment_cells_x=to_cells(attrs["XCELL"]),
        segment_cells_y=to_cells(attrs["YCELL"]),
        band_starts=band_starts,
        remainder=remainder,
        min_fraction=min_fraction,
        wrap=wrap,
    )
    nregion = int(region_map.max()) + 1

    ndays = (end_date - start_date).days + 1
    if ndays < 1:
        raise ValueError("end_date must not be before start_date")
    step_hours = max(1, round(step_days * 24))
    step_start, step_end = build_steps(ndays * 24, step_hours, remainder, min_fraction)
    if int(attrs["TSTEP"]) == 0 and step_start.size > 1:
        raise ValueError(
            f"{bcon_file} is time-independent (TSTEP = 0), so the run can only have one "
            f"boundary control step, but {step_days} days per step gives {step_start.size}"
        )

    lon, lat = _region_lonlat(attrs, region_map, ncols, nrows, nregion)
    return make_map_dataset(
        region_map,
        step_start,
        step_end,
        np.full((step_start.size, nregion), float(unc)),
        start_date,
        info=info,
        lon=lon,
        lat=lat,
        attrs={
            "bcon_file": str(bcon_file),
            "START_DATE": start_date.isoformat(),
            "END_DATE": end_date.isoformat(),
            "NCOLS": ncols,
            "NROWS": nrows,
            "NLAYS": nlays,
            "segment_km": float(segment_km),
            "step_days": float(step_days),
            "band_start_layers": np.array(band_starts, dtype=np.int32) + 1,
            "remainder": remainder,
            "min_fraction": float(min_fraction),
            "wrap": int(wrap),
        },
    )


def make_map_dataset(  # noqa: PLR0913
    region_map: np.ndarray,
    step_start: np.ndarray,
    step_end: np.ndarray,
    unc: np.ndarray,
    start_date: datetime.date,
    info: dict[str, np.ndarray] | None = None,
    lon: np.ndarray | None = None,
    lat: np.ndarray | None = None,
    attrs: dict | None = None,
) -> xr.Dataset:
    origin = np.datetime64(start_date.isoformat(), "ns")
    time_units = f"seconds since {start_date.isoformat()} 00:00:00"
    ds = xr.Dataset(
        {
            "BCON_REGION": (("LAY", "PERIM"), region_map.astype(np.int32)),
            "STEP_START": (
                ("STEP",),
                origin + np.asarray(step_start).astype("timedelta64[s]").astype("timedelta64[ns]"),
            ),
            "STEP_END": (
                ("STEP",),
                origin + np.asarray(step_end).astype("timedelta64[s]").astype("timedelta64[ns]"),
            ),
            "BCON_UNC": (("STEP", "REGION"), np.asarray(unc, dtype=float), {"units": "ppm"}),
        },
        attrs=attrs or {},
    )
    ds["BCON_REGION"].attrs["long_name"] = "region of each boundary cell, -1 for none"
    ds["BCON_UNC"].attrs["long_name"] = "prior 1-sigma uncertainty of the boundary offset"
    for name in ("STEP_START", "STEP_END"):
        ds[name].encoding = {"units": time_units, "dtype": "int64"}
    for name, values in (info or {}).items():
        ds[name] = (("REGION",), values)
    if lon is not None:
        ds["REGION_LON"] = (("REGION",), lon, {"units": "degrees_east"})
        ds["REGION_LAT"] = (("REGION",), lat, {"units": "degrees_north"})
    if "REGION_EDGE" in ds:
        ds["REGION_EDGE"].attrs["long_name"] = "edge: 0=S, 1=E, 2=N, 3=W, -1 if wrapped"
    return ds


def read_bcon_map(
    path: str | pathlib.Path, start_date: datetime.date, end_date: datetime.date
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read a map file as (region_map, step_start, step_end, unc).

    Step boundaries are returned in seconds from `start_date` 00:00.
    """
    with xr.open_dataset(path) as ds:
        origin = np.datetime64(start_date.isoformat(), "s")

        def seconds(name):
            return ((ds[name].values - origin) / np.timedelta64(1, "s")).astype(np.int64)

        region_map = ds["BCON_REGION"].values.astype(np.int32)
        step_start = seconds("STEP_START")
        step_end = seconds("STEP_END")
        unc = ds["BCON_UNC"].values.astype(float)
    run_seconds = ((end_date - start_date).days + 1) * 86400
    if step_start.size and (step_start[0] != 0 or step_end[-1] != run_seconds):
        raise ValueError(
            f"{path} was built for a different period: its steps do not cover "
            f"{start_date} to {end_date}"
        )
    return region_map, step_start, step_end, unc
