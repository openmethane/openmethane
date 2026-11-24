"""Run the WRF step for a real au-test day and check what it publishes.

Needs the WRF and WPS programs, so it only runs in the openmethane image, and
takes about 5 minutes. It is marked `wrf_integration`, which `make test`
leaves out; run it with `make test-wrf`.

The checks are of the contract in docs/reference/wrf-outputs.md, the layout and
structure MCIP relies on, not of values, so they still hold when the WRF
binaries change.
"""

import datetime
import os
import pathlib

import netCDF4
import pytest

from openmethane.wrf import pipeline
from openmethane.wrf.config import WrfConfig
from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.install import WrfInstall

pytestmark = pytest.mark.wrf_integration

DAY = datetime.date(2022, 12, 7)


@pytest.fixture
def fnl_cache_path(root_dir) -> pathlib.Path:
    """
    Where the test keeps FNL analyses, about 3.4 GB for the day. Kept between
    runs, under data/ by default. WRF_TEST_FNL_CACHE_PATH moves it, as CI does.
    """
    return pathlib.Path(os.environ.get("WRF_TEST_FNL_CACHE_PATH") or root_dir / "data" / "fnl")


@pytest.fixture
def config(tmp_path, fnl_cache_path) -> WrfConfig:
    return WrfConfig(
        start_date=DAY,
        end_date=DAY,
        domains=DomainSet.load([("au-test", "v1")]),
        output_path=tmp_path / "store" / "wrf" / "au-test",
        scratch_path=tmp_path / "chk" / "wrf" / "au-test",
        met_em_cache_path=tmp_path / "chk" / "wrf" / "au-test" / "metem",
        fnl_cache_path=fnl_cache_path,
        install=WrfInstall(
            wrf_dir=pathlib.Path(os.environ["WRF_INSTALL_DIR"]),
            wps_dir=pathlib.Path(os.environ["WPS_INSTALL_DIR"]),
        ),
        mpi_ranks=1,
    )


def test_publishes_a_complete_day_in_the_layout_mcip_reads(config, test_data_dir):
    hours = [datetime.datetime(2022, 12, 7) + datetime.timedelta(hours=h) for h in range(25)]
    expected = [f"WRFOUT_d01_{hour:%Y-%m-%dT%H%M}Z.nc" for hour in hours]
    # The fixture CMAQ preprocessing's tests read, so the variables MCIP is
    # known to work with
    mcip_fixture = test_data_dir / "wrf" / "au-test" / "2022120700"

    ran = pipeline.run(config)

    assert ran
    day = config.output_path / "2022120700"
    assert sorted(path.name for path in day.glob("WRFOUT_*")) == expected
    assert not list(day.glob("wrfout_*"))
    assert (day / "namelist.wps").is_file()
    assert (day / "namelist.input").is_file()
    assert any((day / "logs").iterdir())
    assert (config.output_path / "geo_em.d01.nc").is_file()
    # Every 6 hours from 12Z the day before to 00Z the day after
    assert len(list((config.output_path / "metem").glob("met_em.d01.*.nc"))) == 7
    assert not config.scratch_path.exists()

    for name, hour in zip(expected, hours):
        with (
            netCDF4.Dataset(day / name) as ours,
            netCDF4.Dataset(mcip_fixture / name) as fixture,
        ):
            assert ours.dimensions["Time"].size == 1, name
            assert netCDF4.chartostring(ours["Times"][:])[0] == f"{hour:%Y-%m-%d_%H:%M:%S}", name
            assert {
                variable.name: (variable.dimensions, variable.dtype)
                for variable in ours.variables.values()
            } == {
                variable.name: (variable.dimensions, variable.dtype)
                for variable in fixture.variables.values()
            }, name
