import datetime
import pathlib

import pytest

from openmethane.wrf.config import WrfConfig, WrfConfigError
from openmethane.wrf.install import WrfInstall

# What the production WRF job sets.
PRODUCTION_ENV = {
    "START_DATE": "2022-12-07",
    "DOMAIN_NAME": "aust10km",
    "DOMAIN_VERSION": "v1",
    "STORE_PATH": "/store",
    "CHK_PATH": "/chk",
    "FORCE_WRF": "false",
    "NCPUS": "32",
}


def test_reads_the_production_job_environment():
    config = WrfConfig.from_env(PRODUCTION_ENV)

    assert config.start_date == datetime.date(2022, 12, 7)
    assert config.end_date == datetime.date(2022, 12, 7)
    assert config.domain_version == "v1"
    assert [domain.name for domain in config.domains] == ["aust10km"]
    assert config.output_path == pathlib.Path("/store/wrf/aust10km")
    assert config.scratch_path == pathlib.Path("/chk/wrf/aust10km")
    assert config.met_em_cache_path == pathlib.Path("/chk/wrf/aust10km/metem")
    assert config.fnl_cache_path == pathlib.Path("/app/data/fnl")
    assert (config.num_hours_spin_up, config.num_hours_per_run) == (12, 24)
    assert config.mpi_ranks == 32
    assert config.force is False
    assert config.install == WrfInstall()


def test_paths_and_options_default_as_run_wrf_did():
    env = {"START_DATE": "2022-12-07", "DOMAIN_NAME": "au-test", "DOMAIN_VERSION": "v1"}

    config = WrfConfig.from_env(env)

    assert config.output_path == pathlib.Path("/app/data/wrf/au-test")
    assert config.scratch_path == pathlib.Path("/mnt/scratch/wrf/au-test")
    assert config.mpi_ranks is None
    assert config.force is False


def test_cache_paths_can_be_overridden():
    env = PRODUCTION_ENV | {"FNL_CACHE_PATH": "/cache/fnl", "MET_EM_CACHE_PATH": "/cache/metem"}

    config = WrfConfig.from_env(env)

    assert config.fnl_cache_path == pathlib.Path("/cache/fnl")
    assert config.met_em_cache_path == pathlib.Path("/cache/metem")


@pytest.mark.parametrize(
    "value, expected", (("true", True), ("TRUE", True), ("false", False), ("", False))
)
def test_force_wrf(value, expected):
    config = WrfConfig.from_env(PRODUCTION_ENV | {"FORCE_WRF": value})

    assert config.force is expected


def test_end_date_is_ignored_and_one_day_is_run():
    config = WrfConfig.from_env(PRODUCTION_ENV | {"END_DATE": "2022-12-31"})

    assert config.end_date == datetime.date(2022, 12, 7)


def test_every_problem_is_reported_at_once():
    env = {
        "START_DATE": "07/12/2022",
        "DOMAIN_NAME": "nowhere",
        "FORCE_WRF": "yes",
        "NCPUS": "lots",
    }

    with pytest.raises(WrfConfigError) as raised:
        WrfConfig.from_env(env)

    problems = raised.value.problems
    assert len(problems) == 5
    assert "START_DATE must be a date as YYYY-MM-DD, got '07/12/2022'" in problems
    assert "DOMAIN_VERSION is required" in problems
    assert any("No WRF geometry for domain 'nowhere'" in problem for problem in problems)
    assert "FORCE_WRF must be true or false, got 'yes'" in problems
    assert "NCPUS must be a positive whole number, got 'lots'" in problems


def test_missing_required_variables_are_named():
    with pytest.raises(WrfConfigError) as raised:
        WrfConfig.from_env({})

    assert raised.value.problems == [
        "START_DATE is required",
        "DOMAIN_NAME is required",
        "DOMAIN_VERSION is required",
    ]


def test_ncpus_must_be_positive():
    with pytest.raises(WrfConfigError, match="NCPUS must be a positive whole number, got '0'"):
        WrfConfig.from_env(PRODUCTION_ENV | {"NCPUS": "0"})
