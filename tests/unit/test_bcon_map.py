import datetime

import netCDF4
import numpy as np
import pytest

from openmethane import bcon_map

NCOLS, NROWS, NLAYS = 10, 7, 6
NPERIM = bcon_map.perimeter_size(NCOLS, NROWS)


@pytest.fixture
def bcon_file(test_data_dir):
    return test_data_dir / "cmaq" / "template_bcon_profile_CH4only_d01.nc"


@pytest.mark.parametrize(
    "total, target, remainder, min_fraction, expected",
    (
        (31, 5, "spread", 0.0, [5, 5, 5, 5, 5, 6]),
        (31, 5, "end", 0.0, [5, 5, 5, 5, 5, 5, 1]),
        (32, 5, "end", 0.5, [5, 5, 5, 5, 5, 7]),
        (33, 5, "end", 0.5, [5, 5, 5, 5, 5, 5, 3]),
        (33, 5, "spread", 0.0, [4, 4, 5, 5, 5, 5, 5]),
        (351, 100, "end", 0.0, [100, 100, 100, 51]),
        (351, 100, "spread", 0.0, [87, 88, 88, 88]),
        (30, 5, "spread", 0.0, [5] * 6),
        (30, 5, "end", 0.0, [5] * 6),
        (1, 5, "spread", 0.0, [1]),
        (5, 5, "end", 0.0, [5]),
        (7, 5, "spread", 0.0, [7]),
    ),
)
def test_split_length(total, target, remainder, min_fraction, expected):
    pieces = bcon_map.split_length(total, target, remainder, min_fraction)
    assert pieces == expected
    assert sum(pieces) == total


def test_split_length_rejects_bad_input():
    with pytest.raises(ValueError):
        bcon_map.split_length(10, 0)
    with pytest.raises(ValueError):
        bcon_map.split_length(10, 3, "middle")


def test_equal_mass_bands_uniform_layers():
    assert bcon_map.equal_mass_bands(np.linspace(1, 0, 9), 4) == [0, 2, 4, 6]


def test_equal_mass_bands_test_domain(bcon_file):
    with netCDF4.Dataset(bcon_file) as nc:
        vglvls = np.array(nc.VGLVLS, dtype=float)
    starts = bcon_map.equal_mass_bands(vglvls, 4)
    thick = vglvls[:-1] - vglvls[1:]
    mass = np.add.reduceat(thick, starts) / thick.sum()
    # each band is within one layer's mass of a quarter of the column
    assert np.all(np.abs(mass - 0.25) <= thick.max() / thick.sum())


def test_perimeter_edges_cover_all_but_corners():
    edges = bcon_map.perimeter_edges(NCOLS, NROWS)
    corners = bcon_map.corner_indices(NCOLS, NROWS)
    cells = np.concatenate([*edges, corners])
    assert sorted(cells.tolist()) == list(range(NPERIM))
    assert [e.size for e in edges] == [NCOLS, NROWS, NCOLS, NROWS]
    # S and E carry their corner at the end, N and W at the start
    assert corners.tolist() == [NCOLS, NCOLS + NROWS + 1, NCOLS + NROWS + 2, 2 * NCOLS + NROWS + 3]


def test_perimeter_cell_xy_matches_ioapi_order():
    col, row = bcon_map.perimeter_cell_xy(NCOLS, NROWS)
    corners = bcon_map.corner_indices(NCOLS, NROWS)
    assert list(zip(col[corners], row[corners])) == [
        (NCOLS, -1),
        (NCOLS, NROWS),
        (-1, NROWS),
        (-1, -1),
    ]
    edges = bcon_map.perimeter_edges(NCOLS, NROWS)
    assert (row[edges[0]] == -1).all() and (col[edges[0]] == np.arange(NCOLS)).all()
    assert (col[edges[1]] == NCOLS).all() and (row[edges[1]] == np.arange(NROWS)).all()
    assert (row[edges[2]] == NROWS).all() and (col[edges[2]] == np.arange(NCOLS)).all()
    assert (col[edges[3]] == -1).all() and (row[edges[3]] == np.arange(NROWS)).all()


def test_region_map_eight_regions():
    """A segment longer than any edge and two bands give the old 8-region layout."""
    region_map, info = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0, 3])
    edges = bcon_map.perimeter_edges(NCOLS, NROWS)
    assert region_map.max() == 7
    # numbered SL, SH, EL, EH, NL, NH, WL, WH as before
    for edge, cells in enumerate(edges):
        assert (region_map[:3][:, cells] == 2 * edge).all()
        assert (region_map[3:][:, cells] == 2 * edge + 1).all()
    assert (region_map[:, bcon_map.corner_indices(NCOLS, NROWS)] == -1).all()
    assert info["REGION_LAY_START"].tolist() == [1, 4] * 4
    assert info["REGION_LAY_END"].tolist() == [3, 6] * 4


@pytest.mark.parametrize("remainder", bcon_map.REMAINDER_RULES)
def test_region_map_segments(remainder):
    region_map, info = bcon_map.build_region_map(
        NCOLS, NROWS, NLAYS, 4, 3, [0, 2, 4], remainder=remainder
    )
    nregion = region_map.max() + 1
    assert sorted(np.unique(region_map[region_map >= 0])) == list(range(nregion))
    bcon_map.validate_map(
        region_map, [0], [86400], np.ones((1, nregion)), 86400, NLAYS, NCOLS, NROWS
    )
    # no region crosses a corner
    edge_of_cell = np.full(NPERIM, -1)
    for edge, cells in enumerate(bcon_map.perimeter_edges(NCOLS, NROWS)):
        edge_of_cell[cells] = edge
    for r in range(nregion):
        assert np.unique(edge_of_cell[(region_map == r).any(axis=0)]).size == 1
    s_lengths = info["REGION_NCELLS"][(info["REGION_EDGE"] == 0) & (info["REGION_BAND"] == 0)]
    assert s_lengths.tolist() == bcon_map.split_length(NCOLS, 4, remainder)


def test_region_map_wrap_crosses_corners():
    region_map, info = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 6, 6, [0], wrap=True)
    nregion = region_map.max() + 1
    assert info["REGION_NCELLS"].sum() == 2 * (NCOLS + NROWS)
    assert (info["REGION_EDGE"] == -1).all()
    bcon_map.validate_map(
        region_map, [0], [86400], np.ones((1, nregion)), 86400, NLAYS, NCOLS, NROWS
    )


@pytest.mark.parametrize(
    "change, message",
    (
        (lambda m: m.__setitem__((0, 0), -1), "in no region"),
        (lambda m: m.__setitem__(m == 1, 2), "contiguous"),
        (lambda m: m.__setitem__((0, 0), -5), "-1 or a region"),
    ),
)
def test_validate_map_rejects_bad_regions(change, message):
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0, 3])
    change(region_map)
    nregion = region_map.max() + 1
    with pytest.raises(ValueError, match=message):
        bcon_map.validate_map(
            region_map, [0], [86400], np.ones((1, nregion)), 86400, NLAYS, NCOLS, NROWS
        )


@pytest.mark.parametrize(
    "start, end, unc_shape, message",
    (
        ([0, 86400], [86400, 2 * 86400], (2, 8), "cover the run"),
        ([0, 40000], [50000, 86400], (2, 8), "contiguous"),
        ([0], [86400], (1, 7), "BCON_UNC has shape"),
    ),
)
def test_validate_map_rejects_bad_steps(start, end, unc_shape, message):
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0, 3])
    with pytest.raises(ValueError, match=message):
        bcon_map.validate_map(
            region_map, start, end, np.ones(unc_shape), 86400, NLAYS, NCOLS, NROWS
        )


def test_validate_map_rejects_wrong_grid():
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0, 3])
    with pytest.raises(ValueError, match="shape"):
        bcon_map.validate_map(
            region_map, [0], [86400], np.ones((1, 8)), 86400, NLAYS, NCOLS + 1, NROWS
        )


def test_record_steps_uneven():
    # 6 days: steps of 5 days and 1 day
    start, end = bcon_map.build_steps(6 * 24, 5 * 24, "end")
    assert (start / 86400).tolist() == [0, 5]
    assert (end / 86400).tolist() == [5, 6]
    records = np.array([-3600, 0, 4.5 * 86400, 5 * 86400, 6 * 86400, 6 * 86400 + 3600])
    assert bcon_map.record_steps(records, start, end).tolist() == [0, 0, 0, 1, 1, 1]


def test_record_steps_daily_files():
    """The 24:00 record of one day and 00:00 of the next fall either side of a step edge."""
    start, end = np.array([0, 86400]), np.array([86400, 2 * 86400])
    day1 = np.arange(0, 86401, 3 * 3600)
    day2 = day1 + 86400
    assert bcon_map.record_steps(day1, start, end).tolist() == [0] * 8 + [1]
    assert bcon_map.record_steps(day2, start, end).tolist() == [1] * 9


def test_record_steps_time_independent():
    assert bcon_map.record_steps(None, [0], [86400]).tolist() == [0]
    with pytest.raises(ValueError, match="time-independent"):
        bcon_map.record_steps(None, [0, 86400], [86400, 2 * 86400])


def test_ioapi_record_seconds():
    run_start = datetime.date(2022, 12, 7)
    seconds = bcon_map.ioapi_record_seconds(2022341, 0, 30000, 9, run_start)
    assert seconds.tolist() == [3 * 3600 * i for i in range(9)]
    seconds = bcon_map.ioapi_record_seconds(2022342, 10000, 10000, 2, run_start)
    assert seconds.tolist() == [86400 + 3600, 86400 + 7200]
    assert bcon_map.ioapi_record_seconds(-635, 0, 0, 1, run_start) is None


@pytest.mark.parametrize(
    "seg, bands, wrap, rec_step, nstep",
    (
        (100, [0], False, [0], 1),
        (100, [0, 3], False, [0, 0, 0], 1),
        (3, [0, 2, 4], False, [0, 0, 1, 1, 2], 3),
        (4, [0, 1], True, [0, 1, 1, 1], 2),
    ),
)
def test_expand_collapse_are_adjoint(seg, bands, wrap, rec_step, nstep):
    rng = np.random.default_rng(0)
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, seg, seg, bands, wrap=wrap)
    nregion = region_map.max() + 1
    rec_step = np.array(rec_step)
    x = rng.normal(size=(nstep, nregion))
    y = rng.normal(size=(rec_step.size, NLAYS, NPERIM))

    ex = bcon_map.expand(x, region_map, rec_step)
    assert ex.shape == y.shape
    eTy = bcon_map.collapse(y, region_map, rec_step, nstep, nregion)
    np.testing.assert_allclose((ex * y).sum(), (x * eTy).sum())


def test_expand_hand_made_map():
    region_map = np.full((NLAYS, NPERIM), -1)
    region_map[:, :5] = 0
    region_map[:2, 5:] = 1
    region_map[2:, 5:] = 2
    x = np.array([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]])
    field = bcon_map.expand(x, region_map, np.array([0, 1]))
    assert (field[0, :, :5] == 1).all() and (field[1, 1, 5:] == 20).all()
    assert (field[1, 4, 5:] == 30).all()


def test_expand_leaves_unmapped_cells_alone():
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0])
    field = bcon_map.expand(np.ones((1, 4)), region_map, np.array([0]))
    assert (field[:, :, bcon_map.corner_indices(NCOLS, NROWS)] == 0).all()
    assert field.sum() == NLAYS * 2 * (NCOLS + NROWS)


def test_accumulate_minimum():
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 100, 100, [0, 3])
    rec_step = np.array([0, 0, 1])
    field = np.full((3, NLAYS, NPERIM), 2.0)
    s_cell = bcon_map.perimeter_edges(NCOLS, NROWS)[0][2]
    field[1, 4, s_cell] = 0.5  # S, upper band, step 0
    field[2, 0, :] = 1.0  # every lower band, step 1
    corner = bcon_map.corner_indices(NCOLS, NROWS)[0]
    field[:, :, corner] = -9.0  # corners are in no region, so never count

    minimum = np.full((2, 8), np.inf)
    bcon_map.accumulate_minimum(minimum, field, region_map, rec_step)
    expected = np.full((2, 8), 2.0)
    expected[0, 1] = 0.5
    expected[1, ::2] = 1.0
    np.testing.assert_array_equal(minimum, expected)

    # a second day folds into the same running minimum
    bcon_map.accumulate_minimum(minimum, np.full((1, NLAYS, NPERIM), 0.1), region_map, [1])
    assert (minimum[1] == 0.1).all() and (minimum[0] == expected[0]).all()


def test_build_and_read_bcon_map(bcon_file, tmp_path):
    day = datetime.date(2022, 12, 7)
    ds = bcon_map.build_bcon_map(bcon_file, day, day, segment_km=40, unc=0.02)
    path = tmp_path / "bcon_map.nc"
    ds.to_netcdf(path)

    region_map, start, end, unc = bcon_map.read_bcon_map(path, day, day)
    assert region_map.shape == (32, 44)
    assert start.tolist() == [0] and end.tolist() == [86400]
    assert unc.shape == (1, region_map.max() + 1)
    assert (unc == 0.02).all()
    # 10 cells per edge at 10 km, cut into 40 km segments, by 4 bands
    assert region_map.max() + 1 == 4 * 3 * 4
    assert np.isfinite(ds["REGION_LON"]).all() and np.isfinite(ds["REGION_LAT"]).all()

    with pytest.raises(ValueError, match="different period"):
        bcon_map.read_bcon_map(path, day, datetime.date(2022, 12, 8))


def test_build_bcon_map_time_independent_needs_one_step(bcon_file):
    """The test BCON has TSTEP = 0, so a run longer than a step cannot use it."""
    with pytest.raises(ValueError, match="time-independent"):
        bcon_map.build_bcon_map(
            bcon_file, datetime.date(2022, 12, 1), datetime.date(2022, 12, 10), step_days=5
        )
