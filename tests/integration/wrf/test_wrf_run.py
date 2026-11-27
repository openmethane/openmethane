"""Run the WRF step for a real au-test day and check what it publishes.

Needs the WRF and WPS programs, so it only runs in the openmethane image, and
takes about 5 minutes. The first run downloads 3.4 GB of FNL analyses, so it
is also `network` (added in tests/conftest.py for `fnl_cache_path`).

The test runs `wrf run` as production does, configured from the environment,
then checks the output twice: its layout and structure against the contract in
docs/reference/wrf-outputs.md, which say why MCIP would break, and its values
against the reference output in the `wrf` bundle (`wrf_data`), which say that
anything changed. A change meant to change WRF's output needs a new bundle;
see "WRF test data" in docs/guides/testing.md.
"""

import datetime
import os
import pathlib
import subprocess
import sys

import netCDF4
import pytest

from openmethane.wrf.compare import compare_runs

# Marks every test in this module, since each runs WRF
pytestmark = [pytest.mark.wrf, pytest.mark.slow]

DAY = datetime.date(2022, 12, 7)

WRF_COMMAND = pathlib.Path(sys.executable).parent / "wrf"
"""The `wrf` console script installed beside this Python"""


@pytest.fixture
def fnl_cache_path(root_dir) -> pathlib.Path:
    """
    Where the test keeps FNL analyses, about 3.4 GB for the day. Kept between
    runs, under data/ by default. WRF_TEST_FNL_CACHE_PATH moves it, as CI does.
    """
    return pathlib.Path(os.environ.get("WRF_TEST_FNL_CACHE_PATH") or root_dir / "data" / "fnl")


@pytest.fixture
def wrf_environment(monkeypatch, tmp_path, fnl_cache_path):
    """
    Set every variable `WrfConfig.from_env` reads, for the settings the `wrf`
    bundle was made with. `WRF_INSTALL_DIR` and `WPS_INSTALL_DIR` keep the
    image's values. One rank, because the rank count changes WRF's output at
    rounding level.
    """
    monkeypatch.setenv("START_DATE", DAY.isoformat())
    monkeypatch.setenv("DOMAIN_NAME", "au-test")
    monkeypatch.setenv("DOMAIN_VERSION", "v1")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store"))
    monkeypatch.setenv("CHK_PATH", str(tmp_path / "chk"))
    monkeypatch.setenv("FNL_CACHE_PATH", str(fnl_cache_path))
    monkeypatch.setenv("NCPUS", "1")
    for name in ("FORCE_WRF", "MET_EM_CACHE_PATH", "FNL_DATASET_ROOT"):
        monkeypatch.delenv(name, raising=False)


def test_publishes_the_reference_day_in_the_layout_mcip_reads(
    wrf_environment, wrf_data, tmp_path, test_data_dir
):
    hours = [datetime.datetime(2022, 12, 7) + datetime.timedelta(hours=h) for h in range(25)]
    expected = [f"WRFOUT_d01_{hour:%Y-%m-%dT%H%M}Z.nc" for hour in hours]
    output_path = tmp_path / "store" / "wrf" / "au-test"
    # The fixture CMAQ preprocessing's tests read, so the variables MCIP is
    # known to work with
    mcip_fixture = test_data_dir / "wrf" / "au-test" / "2022120700"

    completed = subprocess.run([WRF_COMMAND, "run"], check=False)  # noqa: S603

    assert completed.returncode == 0
    day = output_path / "2022120700"
    assert sorted(path.name for path in day.glob("WRFOUT_*")) == expected
    assert not list(day.glob("wrfout_*"))
    assert (day / "namelist.wps").is_file()
    assert (day / "namelist.input").is_file()
    assert any((day / "logs").iterdir())
    assert (output_path / "geo_em.d01.nc").is_file()
    # Every 6 hours from 12Z the day before to 00Z the day after
    assert len(list((output_path / "metem").glob("met_em.d01.*.nc"))) == 7
    assert not (tmp_path / "chk" / "wrf" / "au-test").exists()

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

    differences = compare_runs(output_path, wrf_data / "au-test")
    assert not differences, "differs from the wrf bundle:\n" + "\n".join(
        f"{path}: {difference}" for path, found in differences.items() for difference in found
    )
