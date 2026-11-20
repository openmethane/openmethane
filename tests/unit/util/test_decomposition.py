import pytest

from openmethane.util.decomposition import Decomposition, solve_decomposition

# The aust10km grid, as (columns, rows).
AUST10KM = (454, 430)


@pytest.mark.parametrize(
    "halo_width, expected",
    (
        # With no halo to exchange, every rank is worth using, however thin
        # its subdomain.
        (0, (23, 1)),
        # A wider halo makes long edges costly, so the solver gives up ranks
        # for squarer subdomains.
        (3, (11, 2)),
        (10, (7, 3)),
    ),
)
def test_a_wider_halo_favours_squarer_subdomains(halo_width, expected):
    grid_cols, grid_rows = AUST10KM

    decomposition = solve_decomposition(
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        target_ranks=23,
        min_cells_per_rank=10,
        halo_width=halo_width,
    )

    assert decomposition == Decomposition(*expected)


def test_every_subdomain_is_at_least_the_minimum():
    grid_cols, grid_rows = AUST10KM

    decomposition = solve_decomposition(
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        target_ranks=1000,
        min_cells_per_rank=40,
        halo_width=5,
    )

    assert grid_cols // decomposition.npcol >= 40
    assert grid_rows // decomposition.nprow >= 40
    assert decomposition.ranks <= 1000


def test_falls_back_to_serial_for_a_grid_below_the_minimum(caplog):
    decomposition = solve_decomposition(
        grid_cols=5, grid_rows=5, target_ranks=24, min_cells_per_rank=10, halo_width=3
    )

    assert decomposition == Decomposition(1, 1)
    assert "too small to split" in caplog.text


def test_rejects_a_minimum_below_the_halo_width():
    with pytest.raises(ValueError, match="at least the halo width 5, got 4"):
        solve_decomposition(
            grid_cols=454, grid_rows=430, target_ranks=24, min_cells_per_rank=4, halo_width=5
        )


def test_rejects_a_negative_halo_width():
    with pytest.raises(ValueError, match="halo_width must not be negative"):
        solve_decomposition(
            grid_cols=454, grid_rows=430, target_ranks=24, min_cells_per_rank=10, halo_width=-1
        )


def test_rejects_a_target_of_no_ranks():
    with pytest.raises(ValueError, match="target_ranks must be positive"):
        solve_decomposition(
            grid_cols=454, grid_rows=430, target_ranks=0, min_cells_per_rank=10, halo_width=3
        )


@pytest.mark.parametrize("npcol, nprow", ((0, 4), (4, 0), (-1, 4)))
def test_a_decomposition_needs_a_subdomain_in_each_direction(npcol, nprow):
    with pytest.raises(ValueError, match="must be > 0"):
        Decomposition(npcol, nprow)
