import pytest

from openmethane.fourdvar.util.decomposition import (
    HALO_WIDTH,
    Decomposition,
    read_grid_size,
    resolve_decomposition,
    solve_decomposition,
)

# The domains we run, as (columns, rows).
AUST10KM = (454, 430)
AU_TEST = (10, 10)


@pytest.fixture
def uncached_decomposition():
    """Resolve the decomposition afresh, ignoring any earlier call's result."""
    resolve_decomposition.cache_clear()
    yield resolve_decomposition
    resolve_decomposition.cache_clear()


@pytest.mark.parametrize(
    "grid, target_ranks, expected",
    (
        # The decompositions chosen by hand for the domains we run: 6x4 for a
        # 48 vCPU (24 physical core) job, 8x6 for the 48 ranks used before that.
        (AUST10KM, 24, (6, 4)),
        (AUST10KM, 48, (8, 6)),
        # au-test is too small to gain from being split at all.
        (AU_TEST, 24, (1, 1)),
        # A single rank has nothing to decide.
        (AUST10KM, 1, (1, 1)),
        # A prime target can't be filled squarely, so a rank goes unused rather
        # than accepting the 23x1 split that would use them all.
        (AUST10KM, 23, (11, 2)),
        # A wide domain is split along its long side.
        ((400, 100), 8, (4, 2)),
    ),
)
def test_solves_the_decompositions_we_run(grid, target_ranks, expected):
    grid_cols, grid_rows = grid

    decomposition = solve_decomposition(
        grid_cols=grid_cols, grid_rows=grid_rows, target_ranks=target_ranks, min_cells_per_rank=10
    )

    assert decomposition == Decomposition(*expected)


@pytest.mark.parametrize("target_ranks", range(1, 65))
def test_every_subdomain_is_at_least_the_minimum(target_ranks):
    grid_cols, grid_rows = AUST10KM
    min_cells = 10

    decomposition = solve_decomposition(
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        target_ranks=target_ranks,
        min_cells_per_rank=min_cells,
    )

    # SUBHDOMAIN gives the leftovers of an uneven split to the leading
    # subdomains, so the floor of the division is the smallest subdomain.
    assert grid_cols // decomposition.npcol >= min_cells
    assert grid_rows // decomposition.nprow >= min_cells
    assert decomposition.ranks <= target_ranks


def test_uses_as_many_of_the_ranks_as_the_domain_allows():
    grid_cols, grid_rows = AUST10KM

    # 45x43 subdomains: any finer split in either direction drops below 40 cells.
    decomposition = solve_decomposition(
        grid_cols=grid_cols, grid_rows=grid_rows, target_ranks=1000, min_cells_per_rank=40
    )

    assert decomposition == Decomposition(11, 10)


def test_falls_back_to_serial_for_a_domain_below_the_minimum(caplog):
    decomposition = solve_decomposition(
        grid_cols=5, grid_rows=5, target_ranks=24, min_cells_per_rank=10
    )

    assert decomposition == Decomposition(1, 1)
    assert decomposition.is_serial
    assert "too small to split" in caplog.text


def test_rejects_a_minimum_below_the_halo_width():
    with pytest.raises(ValueError, match=f"at least the halo width {HALO_WIDTH}"):
        solve_decomposition(
            grid_cols=454, grid_rows=430, target_ranks=24, min_cells_per_rank=HALO_WIDTH - 1
        )


def test_rejects_a_target_of_no_ranks():
    with pytest.raises(ValueError, match="target_ranks must be positive"):
        solve_decomposition(grid_cols=454, grid_rows=430, target_ranks=0, min_cells_per_rank=10)


@pytest.mark.parametrize("npcol, nprow", ((0, 4), (4, 0), (-1, 4)))
def test_a_decomposition_needs_a_rank_in_each_direction(npcol, nprow):
    with pytest.raises(ValueError, match="must be > 0"):
        Decomposition(npcol, nprow)


def test_ranks_is_the_product_of_the_decomposition():
    assert Decomposition(6, 4).ranks == 24
    assert not Decomposition(6, 4).is_serial
    assert Decomposition(1, 1).is_serial
    assert str(Decomposition(6, 4)) == "6x4"


def test_reads_the_grid_size_from_the_mcip_output(test_data_dir):
    grid_cro_2d = test_data_dir / "mcip" / "2022-12-07" / "d01" / "GRIDCRO2D_au-test_v1"

    assert read_grid_size(str(grid_cro_2d)) == AU_TEST


def test_configured_decomposition_is_used_as_given(uncached_decomposition, monkeypatch):
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 8)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.nprow", 6)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.num_proc_total", 24)

    # An explicit pair wins over a rank target, even one it disagrees with.
    assert uncached_decomposition() == Decomposition(8, 6)


def test_half_a_configured_decomposition_means_one_rank_across(uncached_decomposition, monkeypatch):
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 4)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.nprow", 0)

    assert uncached_decomposition() == Decomposition(4, 1)


def test_rank_target_is_split_across_the_grid_cmaq_is_given(
    uncached_decomposition, monkeypatch, test_data_dir
):
    grid_cro_2d = test_data_dir / "mcip" / "<YYYY-MM-DD>" / "d01" / "GRIDCRO2D_au-test_v1"
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 0)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.nprow", 0)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.num_proc_total", 24)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.grid_cro_2d", str(grid_cro_2d))

    # The MCIP output is on the 10x10 au-test grid, which is too small to gain
    # from being split at all.
    assert uncached_decomposition() == Decomposition(1, 1)


def test_no_configuration_at_all_runs_in_serial(uncached_decomposition, monkeypatch):
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 0)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.nprow", 0)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.num_proc_total", 0)

    assert uncached_decomposition() == Decomposition(1, 1)


def test_the_resolved_decomposition_is_cached(uncached_decomposition, monkeypatch):
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 8)
    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.nprow", 6)

    assert uncached_decomposition() == Decomposition(8, 6)

    monkeypatch.setattr("openmethane.fourdvar.params.cmaq_config.npcol", 2)

    assert uncached_decomposition() == Decomposition(8, 6)
