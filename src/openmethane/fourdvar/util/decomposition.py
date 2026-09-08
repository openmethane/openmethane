"""Choose how to split the model domain across MPI ranks.

CMAQ is told its decomposition as NPCOL x NPROW, and the two numbers have to
suit the grid: a domain split too finely gives subdomains too small to exchange
a halo. Rather than configure the pair per domain, callers can name the number
of ranks they want to run on and let `resolve_decomposition` pick the shape.
"""

import functools
import math

import attrs
import attrs.validators

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.params import cmaq_config, date_defn
from openmethane.util.logger import get_logger

logger = get_logger(__name__)

# Width of the halo the advection scheme swaps with its neighbours, in cells:
# SWP in CMAQ-Adjoint's hadv/yamo_cadj_fwd/{xadv,yadv,hppm}.F under -Dparallel.
# A subdomain narrower than this can't supply a whole halo, so it is a hard
# floor on cells per rank in either direction.
HALO_WIDTH = 3


@attrs.frozen
class Decomposition:
    """A horizontal domain decomposition, as CMAQ's NPCOL and NPROW."""

    npcol: int = attrs.field(validator=attrs.validators.gt(0))
    nprow: int = attrs.field(validator=attrs.validators.gt(0))

    @property
    def ranks(self) -> int:
        """Total number of MPI ranks the decomposition needs."""
        return self.npcol * self.nprow

    @property
    def is_serial(self) -> bool:
        """Whether this runs CMAQ in serial rather than under mpirun."""
        return self.ranks == 1

    def __str__(self) -> str:
        return f"{self.npcol}x{self.nprow}"


def _rank_cost(grid_cols: int, grid_rows: int, decomposition: Decomposition) -> int:
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
    # A halo on each of the four sides, exchanged every advection step.
    halo = 2 * HALO_WIDTH * (width + height)

    return interior + halo


def solve_decomposition(
    grid_cols: int,
    grid_rows: int,
    target_ranks: int,
    min_cells_per_rank: int,
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

    The result does not have to divide `target_ranks` evenly. CMAQ launches
    exactly NPCOL x NPROW ranks (HGRD_INIT rejects any other count), so a domain
    that can't fill the target simply runs on fewer ranks. Nor does it have to
    divide the grid evenly: SUBHDOMAIN spreads the remaining columns and rows
    one per subdomain, so the smallest subdomain is the floor of the division.

    Parameters
    ----------
    grid_cols
        Number of columns in the grid.
    grid_rows
        Number of rows in the grid.
    target_ranks
        Most ranks to use, normally the cores the job has been given.
    min_cells_per_rank
        Fewest cells a subdomain may span in either direction.

    Returns
    -------
    The chosen decomposition, at worst 1x1.
    """
    if target_ranks < 1:
        raise ValueError(f"target_ranks must be positive, got {target_ranks}")
    if min_cells_per_rank < HALO_WIDTH:
        raise ValueError(
            f"min_cells_per_rank must be at least the halo width {HALO_WIDTH},"
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
            score = (_rank_cost(grid_cols, grid_rows, candidate), skew, npcol)

            if best_score is None or score < best_score:
                best = candidate
                best_score = score

    if best is None:
        # The grid is smaller than the minimum in at least one direction. Serial
        # runs swap no halo, so 1x1 is still valid, just not parallel.
        logger.warning(
            f"{grid_cols}x{grid_rows} grid is too small to split into subdomains of at"
            f" least {min_cells_per_rank} cells, running CMAQ in serial"
        )
        return Decomposition(1, 1)

    return best


def read_grid_size(path: str) -> tuple[int, int]:
    """
    Read the size of the grid an IO/API file is on.

    Parameters
    ----------
    path
        Path of the file, which must carry the IO/API grid attributes.

    Returns
    -------
    The grid's column and row counts.
    """
    return int(ncf.get_attr(path, "NCOLS")), int(ncf.get_attr(path, "NROWS"))


@functools.cache
def resolve_decomposition() -> Decomposition:
    """
    Work out the decomposition to run CMAQ with.

    NUM_PROC_COLS and NUM_PROC_ROWS are used as given if either is set. Failing
    that, NUM_PROC_TOTAL is split across the domain by `solve_decomposition`. If
    neither is configured, CMAQ runs in serial.

    The result is cached, since the grid does not change within a run.

    Returns
    -------
    The decomposition to run every CMAQ invocation with.
    """
    if cmaq_config.npcol or cmaq_config.nprow:
        # A missing half of an explicit pair means one rank in that direction.
        decomposition = Decomposition(cmaq_config.npcol or 1, cmaq_config.nprow or 1)
        logger.info(f"using configured decomposition {decomposition}")
        return decomposition

    if not cmaq_config.num_proc_total:
        logger.info("no decomposition configured, running CMAQ in serial")
        return Decomposition(1, 1)

    # Take the grid from the MCIP output rather than the domain file, since this
    # is the grid CMAQ itself is given. The path carries a date, and every day
    # of a run is on the same grid.
    grid_file = dt.replace_date(cmaq_config.grid_cro_2d, date_defn.start_date)
    grid_cols, grid_rows = read_grid_size(grid_file)

    decomposition = solve_decomposition(
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        target_ranks=cmaq_config.num_proc_total,
        min_cells_per_rank=cmaq_config.min_cells_per_rank,
    )
    logger.info(
        f"decomposed the {grid_cols}x{grid_rows} grid as {decomposition}"
        f" ({decomposition.ranks} of {cmaq_config.num_proc_total} ranks,"
        f" subdomains of {grid_cols // decomposition.npcol}"
        f"x{grid_rows // decomposition.nprow} cells or larger)"
    )
    return decomposition
