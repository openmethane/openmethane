"""How many MPI ranks to run wrf.exe on.

WRF splits the grid itself, into the most nearly square pair of factors of the
rank count, so only the count is chosen here. Ported from setup-wrf's
`safe_mpi_tasks`, but checked against every domain rather than only the
innermost. #325 replaces this with the shared decomposition solver.
"""

import math
import os

WRF_MIN_PATCH_SIZE = 10
"""Fewest cells WRF guidance allows a patch in either direction"""


def physical_cpu_count(cpuinfo: str = "/proc/cpuinfo") -> int:
    """
    Number of physical cores, which is half the CPUs os.cpu_count() reports on
    a host with hyperthreading. WRF runs faster with one rank per physical core
    than with one per hardware thread.

    Falls back to os.cpu_count() where /proc/cpuinfo doesn't say which core
    each CPU belongs to. Neither respects a container's CPU limit, so set the
    rank count explicitly when running in one.
    """
    cores = set()
    try:
        with open(cpuinfo) as file:
            socket = None
            for line in file:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "physical id":
                    socket = value.strip()
                elif key == "core id":
                    cores.add((socket, value.strip()))
    except OSError:
        pass

    return len(cores) or os.cpu_count() or 1


def find_largest_factors(number: int) -> tuple[int, int]:
    """The pair of factors of `number` closest to its square root, smaller first."""
    factor = math.isqrt(number)
    while number % factor:
        factor -= 1
    return factor, number // factor


def safe_mpi_ranks(grids: list[tuple[int, int]], cpu_count: int) -> int:
    """
    The most ranks, up to `cpu_count`, that give WRF usable patches on every grid.

    A count qualifies when its most nearly square factors are within a factor
    of two of each other, and every grid's patches are at least
    `WRF_MIN_PATCH_SIZE` cells in each direction. Small grids end up on one
    rank.

    WRF uses one layout for every domain, so the smallest grid decides. For one
    grid this is setup-wrf's `safe_mpi_tasks`.

    Parameters
    ----------
    grids
        Each domain's size in cells as (rows, columns), south-north by
        west-east, as in its geo_em file. `DomainSet.grid_cells` gives them;
        the namelist's `e_sn` and `e_we` are one larger.
    cpu_count
        Most ranks to use.
    """
    if cpu_count < 1:
        raise ValueError(f"cpu_count must be positive, got {cpu_count}")
    if not grids:
        raise ValueError("At least one grid is needed")

    ranks = cpu_count
    while ranks > 1:
        # As in setup-wrf, the larger factor is assumed to split the rows
        across, down = find_largest_factors(ranks)
        if down <= across * 2 and all(
            rows / down >= WRF_MIN_PATCH_SIZE and columns / across >= WRF_MIN_PATCH_SIZE
            for rows, columns in grids
        ):
            return ranks
        ranks -= 1
    return 1
