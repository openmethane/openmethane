"""Choose how to split the model domain across MPI ranks.

CMAQ is told its decomposition as NPCOL x NPROW, and the two numbers have to
suit the grid: a domain split too finely gives subdomains too small to exchange
a halo. Rather than configure the pair per domain, callers can name the number
of ranks they want to run on and let `resolve_decomposition` pick the shape.

The solver itself is shared with other models in `openmethane.util.decomposition`.
This module supplies CMAQ's settings and grid.
"""

import functools

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
import openmethane.util.decomposition as shared
from openmethane.fourdvar.params import cmaq_config, date_defn
from openmethane.util.decomposition import Decomposition
from openmethane.util.logger import get_logger

logger = get_logger(__name__)

# Width of the halo the advection scheme swaps with its neighbours, in cells:
# SWP in CMAQ-Adjoint's hadv/yamo_cadj_fwd/{xadv,yadv,hppm}.F under -Dparallel.
# A subdomain narrower than this can't supply a whole halo, so it is a hard
# floor on cells per rank in either direction.
HALO_WIDTH = 3


def solve_decomposition(
    grid_cols: int,
    grid_rows: int,
    target_ranks: int,
    min_cells_per_rank: int,
) -> Decomposition:
    """
    Find the best decomposition of a grid for CMAQ, with CMAQ's halo width.

    See `openmethane.util.decomposition.solve_decomposition`. CMAQ launches
    exactly NPCOL x NPROW ranks (HGRD_INIT rejects any other count), and
    SUBHDOMAIN spreads the remaining columns and rows one per subdomain, which
    is what that solver assumes.
    """
    decomposition = shared.solve_decomposition(
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        target_ranks=target_ranks,
        min_cells_per_rank=min_cells_per_rank,
        halo_width=HALO_WIDTH,
    )
    if grid_cols < min_cells_per_rank or grid_rows < min_cells_per_rank:
        logger.warning(
            f"{grid_cols}x{grid_rows} grid is too small to split into subdomains of at"
            f" least {min_cells_per_rank} cells, running CMAQ in serial"
        )
    return decomposition


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
