import datetime
import pathlib

import pytest

from openmethane.wrf.config import WrfConfig, WrfConfigError
from openmethane.wrf.install import WrfInstall

# What the production WRF job and the openmethane image set.
PRODUCTION_ENV = {
    "START_DATE": "2022-12-07",
    "DOMAIN_NAME": "aust10km",
    "DOMAIN_VERSION": "v1",
    "STORE_PATH": "/store",
    "CHK_PATH": "/chk",
    "FNL_CACHE_PATH": "/cache/fnl",
    "WRF_INSTALL_DIR": "/install/wrf",
    "WPS_INSTALL_DIR": "/install/wps",
    "FORCE_WRF": "false",
    "NCPUS": "32",
}


def test_reads_the_production_job_environment():
    config = WrfConfig.from_env(PRODUCTION_ENV)

    assert config.start_date == datetime.date(2022, 12, 7)
    assert config.end_date == datetime.date(2022, 12, 7)
    assert [(domain.name, domain.version) for domain in config.domains] == [("aust10km", "v1")]
    assert config.output_path == pathlib.Path("/store/wrf/aust10km")
    assert config.scratch_path == pathlib.Path("/chk/wrf/aust10km")
    assert config.met_em_cache_path == pathlib.Path("/chk/wrf/aust10km/metem")
    assert config.fnl_cache_path == pathlib.Path("/cache/fnl")
    assert (config.num_hours_spin_up, config.num_hours_per_run) == (12, 24)
    assert config.mpi_ranks == 32
    assert config.force is False
    assert config.install == WrfInstall(wrf_dir="/install/wrf", wps_dir="/install/wps")


def test_options_default_as_run_wrf_did():
    env = {
        name: value for name, value in PRODUCTION_ENV.items() if name not in ("FORCE_WRF", "NCPUS")
    }

    config = WrfConfig.from_env(env)

    assert config.mpi_ranks is None
    assert config.force is False


def test_caches_default_to_the_scratch_folder():
    env = {
        name: value
        for name, value in PRODUCTION_ENV.items()
        if name not in ("FNL_CACHE_PATH", "MET_EM_CACHE_PATH")
    }

    config = WrfConfig.from_env(env)

    assert config.fnl_cache_path == pathlib.Path("/chk/wrf/aust10km/fnl")
    assert config.met_em_cache_path == pathlib.Path("/chk/wrf/aust10km/metem")


def test_the_met_em_cache_path_can_be_overridden():
    env = PRODUCTION_ENV | {"MET_EM_CACHE_PATH": "/cache/metem"}

    config = WrfConfig.from_env(env)

    assert config.met_em_cache_path == pathlib.Path("/cache/metem")


@pytest.mark.parametrize(
    "value, expected",
    (
        ("true", True),
        ("TRUE", True),
        ("false", False),
        ("", False),
    ),
)
def test_force_wrf(value, expected):
    config = WrfConfig.from_env(PRODUCTION_ENV | {"FORCE_WRF": value})

    assert config.force is expected


def test_end_date_is_ignored_and_one_day_is_run():
    config = WrfConfig.from_env(PRODUCTION_ENV | {"END_DATE": "2022-12-31"})

    assert config.end_date == datetime.date(2022, 12, 7)


def test_every_problem_is_reported_at_once():
    env = PRODUCTION_ENV | {
        "START_DATE": "07/12/2022",
        "DOMAIN_NAME": "nowhere",
        "FORCE_WRF": "yes",
        "NCPUS": "lots",
    }

    with pytest.raises(WrfConfigError) as raised:
        WrfConfig.from_env(env)

    assert raised.value.problems == [
        "START_DATE must be a date as YYYY-MM-DD, got '07/12/2022'",
        "No WRF geometry for domain 'nowhere' version 'v1'. Known: au-test v1, aust10km v1",
        "FORCE_WRF must be true or false, got 'yes'",
        "NCPUS must be a positive whole number, got 'lots'",
    ]


def test_a_version_with_no_geometry_is_an_error():
    with pytest.raises(WrfConfigError, match="domain 'aust10km' version 'v2'"):
        WrfConfig.from_env(PRODUCTION_ENV | {"DOMAIN_VERSION": "v2"})


def test_missing_required_variables_are_named():
    with pytest.raises(WrfConfigError) as raised:
        WrfConfig.from_env({})

    assert raised.value.problems == [
        "START_DATE is required",
        "DOMAIN_NAME is required",
        "DOMAIN_VERSION is required",
        "STORE_PATH is required",
        "CHK_PATH is required",
        "WRF_INSTALL_DIR is required",
        "WPS_INSTALL_DIR is required",
    ]


def test_relative_paths_are_made_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    env = PRODUCTION_ENV | {"STORE_PATH": "store", "CHK_PATH": "chk", "FNL_CACHE_PATH": "fnl"}

    config = WrfConfig.from_env(env)

    assert config.output_path == tmp_path / "store" / "wrf" / "aust10km"
    assert config.scratch_path == tmp_path / "chk" / "wrf" / "aust10km"
    assert config.met_em_cache_path == tmp_path / "chk" / "wrf" / "aust10km" / "metem"
    assert config.fnl_cache_path == tmp_path / "fnl"


@pytest.mark.parametrize("store, chk", (("/data", "/data"), ("/data", "/data/wrf/aust10km/x")))
def test_scratch_and_output_must_be_separate(store, chk):
    with pytest.raises(WrfConfigError, match="CHK_PATH and STORE_PATH must be separate"):
        WrfConfig.from_env(PRODUCTION_ENV | {"STORE_PATH": store, "CHK_PATH": chk})


def test_ncpus_must_be_positive():
    with pytest.raises(WrfConfigError, match="NCPUS must be a positive whole number, got '0'"):
        WrfConfig.from_env(PRODUCTION_ENV | {"NCPUS": "0"})
