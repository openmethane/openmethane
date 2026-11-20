"""Choose how to split a model grid across MPI ranks.

Models that run on a decomposed grid, such as CMAQ and WRF, need a number of
subdomain columns and rows that suits the grid: a grid split too finely gives
subdomains too small to exchange a halo. `solve_decomposition` picks the shape
from the number of ranks available. It reads no configuration, so each model
passes its own halo width and minimum subdomain size.
"""

import logging
import math

import attrs
import attrs.validators

logger = logging.getLogger(__name__)


@attrs.frozen
class Decomposition:
    """A horizontal domain decomposition into columns and rows of subdomains."""

    npcol: int = attrs.field(validator=attrs.validators.gt(0))
    """Number of subdomains across the grid's columns"""
    nprow: int = attrs.field(validator=attrs.validators.gt(0))
    """Number of subdomains across the grid's rows"""

    @property
    def ranks(self) -> int:
        """Total number of MPI ranks the decomposition needs."""
        return self.npcol * self.nprow

    @property
    def is_serial(self) -> bool:
        """Whether this is a single rank, run without mpirun."""
        return self.ranks == 1

    def __str__(self) -> str:
        return f"{self.npcol}x{self.nprow}"


def _rank_cost(
    grid_cols: int, grid_rows: int, decomposition: Decomposition, halo_width: int
) -> int:
    """
    Estimate the work the busiest rank does under a decomposition.

    Counts the cells a rank owns plus the halo cells it has to exchange for
    them, which is what trades off splitting the domain further against the
    communication that splitting adds. Uses the largest subdomain, since every
    rank waits on the slowest.
    """
    width = math.ceil(grid_cols / decomposition.npcol)
    height = math.ceil(grid_rows / decomposition.nprow)

    interior = width * height
    # A halo on each of the four sides, exchanged every step.
    halo = 2 * halo_width * (width + height)

    return interior + halo


def solve_decomposition(
    grid_cols: int,
    grid_rows: int,
    target_ranks: int,
    min_cells_per_rank: int,
    halo_width: int,
) -> Decomposition:
    """
    Find the best decomposition of a grid across at most `target_ranks` ranks.

    Minimises the estimated work of the busiest rank (see `_rank_cost`) while
    keeping every subdomain at least `min_cells_per_rank` cells wide and tall.
    That balances the two competing pressures on its own: more ranks give each
    one fewer cells, but smaller subdomains spend proportionally more of their
    time on halo exchange. In practice it uses all of the ranks whenever they
    divide the domain reasonably squarely, and leaves some idle rather than
    accept a long thin split.

    The result does not have to use all of `target_ranks`, so the caller must
    launch exactly `ranks` of them. Nor does it have to divide the grid evenly:
    the smallest subdomain is the floor of the division, which is what the
    minimum is checked against.

    Parameters
    ----------
    grid_cols
        Number of columns in the grid.
    grid_rows
        Number of rows in the grid.
    target_ranks
        Most ranks to use, normally the cores the job has been given.
    min_cells_per_rank
        Fewest cells a subdomain may span in either direction. Must be at least
        `halo_width`, since a narrower subdomain can't supply a whole halo.
    halo_width
        Width in cells of the halo each subdomain exchanges with its neighbours.

    Returns
    -------
    The chosen decomposition, at worst 1x1.
    """
    if target_ranks < 1:
        raise ValueError(f"target_ranks must be positive, got {target_ranks}")
    if halo_width < 0:
        raise ValueError(f"halo_width must not be negative, got {halo_width}")
    if min_cells_per_rank < halo_width:
        raise ValueError(
            f"min_cells_per_rank must be at least the halo width {halo_width},"
            f" got {min_cells_per_rank}"
        )

    best = None
    best_score = None

    for npcol in range(1, target_ranks + 1):
        # Subdomains only get narrower as npcol grows, so once one direction is
        # too fine no larger value of it can qualify.
        if grid_cols // npcol < min_cells_per_rank:
            break

        for nprow in range(1, target_ranks // npcol + 1):
            if grid_rows // nprow < min_cells_per_rank:
                break

            candidate = Decomposition(npcol, nprow)
            # Two decompositions can cost the same, most obviously a domain's
            # own transpose. Break the tie on the squarest subdomains and then
            # on npcol, so the choice doesn't depend on iteration order.
            skew = abs(math.log((grid_cols / npcol) / (grid_rows / nprow)))
            score = (_rank_cost(grid_cols, grid_rows, candidate, halo_width), skew, npcol)

            if best_score is None or score < best_score:
                best = candidate
                best_score = score

    if best is None:
        # The grid is smaller than the minimum in at least one direction. Serial
        # runs swap no halo, so 1x1 is still valid, just not parallel.
        logger.warning(
            f"{grid_cols}x{grid_rows} grid is too small to split into subdomains of at"
            f" least {min_cells_per_rank} cells, running in serial"
        )
        return Decomposition(1, 1)

    return best
