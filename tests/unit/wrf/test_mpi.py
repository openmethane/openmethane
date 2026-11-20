import os

import pytest

from openmethane.wrf.mpi import find_largest_factors, physical_cpu_count, safe_mpi_ranks

# Grid sizes in cells, (south_north, west_east), from each domain's geo_em.
AU_TEST = (14, 14)
AUST10KM = (442, 466)


@pytest.mark.parametrize(
    "grid, cpu_count, expected",
    (
        # Each expected count is what setup-wrf 0.9.2's safe_mpi_tasks gives.
        *((AU_TEST, cpus, 1) for cpus in (1, 2, 8, 12, 16, 24, 31, 32, 48, 64, 96, 128, 192)),
        (AUST10KM, 1, 1),
        (AUST10KM, 2, 2),
        (AUST10KM, 8, 8),
        (AUST10KM, 12, 12),
        (AUST10KM, 16, 16),
        (AUST10KM, 24, 24),
        (AUST10KM, 31, 30),
        (AUST10KM, 32, 32),
        (AUST10KM, 48, 48),
        (AUST10KM, 64, 64),
        (AUST10KM, 96, 96),
        (AUST10KM, 128, 128),
        (AUST10KM, 192, 192),
    ),
)
def test_gives_setup_wrfs_rank_count_for_the_domains_we_run(grid, cpu_count, expected):
    assert safe_mpi_ranks([grid], cpu_count) == expected


@pytest.mark.parametrize(
    "grid, cpu_count, expected",
    (
        # setup-wrf's own cases
        ((1, 1), 32, 1),
        ((19, 19), 32, 1),
        ((20, 20), 4, 4),
        ((20, 20), 8, 4),
        ((20, 20), 1024, 4),
        ((64, 64), 1024, 36),
        ((2000, 2000), 64, 64),
        ((2000, 2000), 63, 63),
        ((2000, 2000), 60, 60),
        ((2000, 2000), 62, 60),
        ((2000, 2000), 61, 60),
    ),
)
def test_gives_setup_wrfs_rank_count_for_its_test_grids(grid, cpu_count, expected):
    assert safe_mpi_ranks([grid], cpu_count) == expected


def test_the_smallest_domain_decides_the_count():
    # 64 ranks suit aust10km alone, but a 30x30 nest can take only 9: 3x3
    # patches of 10 cells.
    assert safe_mpi_ranks([AUST10KM, (30, 30)], 64) == 9
    assert safe_mpi_ranks([(30, 30), AUST10KM], 64) == 9


def test_rejects_no_cores_or_no_grids():
    with pytest.raises(ValueError, match="cpu_count must be positive"):
        safe_mpi_ranks([AUST10KM], 0)
    with pytest.raises(ValueError, match="At least one grid"):
        safe_mpi_ranks([], 32)


@pytest.mark.parametrize(
    "number, expected",
    (
        (1, (1, 1)),
        (3, (1, 3)),
        (4, (2, 2)),
        (6, (2, 3)),
        (17, (1, 17)),
        (18, (3, 6)),
        (62, (2, 31)),
        (63, (7, 9)),
        (128, (8, 16)),
    ),
)
def test_find_largest_factors(number, expected):
    assert find_largest_factors(number) == expected


def test_physical_cpu_count_ignores_hyperthreads(tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    # 2 sockets of 4 cores, each core listed twice. Core ids repeat per socket.
    cpuinfo.write_text(
        "".join(
            f"processor\t: {n}\nphysical id\t: {socket}\ncore id\t\t: {core}\n\n"
            for n, (socket, core) in enumerate(
                [(socket, core) for socket in range(2) for core in range(4)] * 2
            )
        )
    )

    assert physical_cpu_count(str(cpuinfo)) == 8


def test_physical_cpu_count_falls_back_to_cpu_count(tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nBogoMIPS\t: 50.00\n\n")

    assert physical_cpu_count(str(cpuinfo)) == os.cpu_count()
    assert physical_cpu_count(str(tmp_path / "missing")) == os.cpu_count()
