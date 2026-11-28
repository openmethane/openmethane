import importlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest
import xarray as xr
import yaml

from openmethane.util.download import DownloadFailed, fetch_archive

TESTS_DIR = Path(__file__).parent
ROOT_DIR = TESTS_DIR.parent
BUNDLES_FILE = TESTS_DIR / "test-data" / "bundles.yaml"

# Everything from here to `_start_unconfigured()`, plus `_reload_params` and
# `target_environment`, works around `fourdvar.params` and `util.logger`
# reading the environment when imported. Delete it once nothing does (#352).
NO_ENV_FILE_TARGET = "pytest"
"""
A `TARGET` with no `.env.${TARGET}` file, so no file fills in configuration a
test didn't set.
"""

CONFIG_VARIABLES = (
    "ADJOINT_BWD",
    "ADJOINT_FWD",
    "BCON_FILE",
    "BOUNDARY_TRIM",
    "CAMS_FILE",
    "CAMS_INVERSION_VERSION",
    "CAMS_PRODUCT",
    "CAMS_TO_CMAQ_BIAS",
    "CHK_PATH",
    "CMAQ_BIN",
    "CMAQ_KZMIN",
    "CTM_DIR",
    "DOMAIN_FILE",
    "DOMAIN_INDEX",
    "DOMAIN_MAP_PROJECTION",
    "DOMAIN_MCIP_SUFFIX",
    "DOMAIN_NAME",
    "DOMAIN_VERSION",
    "EMIS_FILE",
    "END_DATE",
    "EXECUTION_ID",
    "EXPERIMENT",
    "FORCE_FILE",
    "FORCE_UPDATE",
    "GEO_DIR",
    "ICON_FILE",
    "LOG_FILE",
    "LOG_LEVEL",
    "MET_DIR",
    "MIN_CELLS_PER_RANK",
    "MPI_EXTRA_ARGS",
    "NUM_PROC_COLS",
    "NUM_PROC_ROWS",
    "NUM_PROC_TOTAL",
    "OBS_FILE_GLOB",
    "OM_LOGGING_FILE",
    "PBS_JOBFS",
    "PRIOR_FILE",
    "ROOT_DIR",
    "START_DATE",
    "STORE_PATH",
    "TARGET",
    "TEMPLATE_DIR",
    "TEST_DATA_DIR",
    "USE_JOBFS",
    "WRF_DIR",
)
"""
Variables the `.env` files set, and those `fourdvar.params`, the CMAQ
preprocessing configuration and the logger read when imported or loaded,
removed from the environment tests start with.
"""

PROCESS_VARIABLES = ("PATH", "PYTHONPATH", "VIRTUAL_ENV", "LD_LIBRARY_PATH")
"""
Variables configuration fixtures keep when they clear the environment, which
programs need to start. Not an exhaustive list.
"""

UNCONFIGURED = "/nonexistent-test-configuration"
"""
Where the variables that `fourdvar.params` can't import without point, until
a configuration fixture sets them.
"""

PARAMS_MODULES = (
    "openmethane.fourdvar.env",
    "openmethane.fourdvar.params.root_path_defn",
    "openmethane.fourdvar.params.input_defn",
    "openmethane.fourdvar.params.date_defn",
    "openmethane.fourdvar.params.archive_defn",
    "openmethane.fourdvar.params.template_defn",
    "openmethane.fourdvar.params.data_access",
    "openmethane.fourdvar.params.cmaq_config",
)
"""Modules that read their configuration when imported, in dependency order."""


def _start_unconfigured() -> None:
    """
    Remove configuration from the environment the tests start with.

    Test modules import code that imports `fourdvar.params`, which reads
    `STORE_PATH` and other variables on import, so this runs when this file is
    loaded, before any test module is. A test that needs configuration uses a
    fixture such as `au_test_config`. One that forgets gets paths under
    `UNCONFIGURED` for the variables params can't import without, which fail
    when read, and the code's defaults for the rest (dates in July 2022, for
    example), never a value from a `.env` file or the developer's shell.
    """
    for key in CONFIG_VARIABLES:
        os.environ.pop(key, None)
    os.environ["TARGET"] = NO_ENV_FILE_TARGET
    for key in (
        "STORE_PATH",
        "MET_DIR",
        "PRIOR_FILE",
        "ICON_FILE",
        "BCON_FILE",
        "ADJOINT_FWD",
        "ADJOINT_BWD",
    ):
        os.environ[key] = f"{UNCONFIGURED}/{key}"


assert not (ROOT_DIR / f".env.{NO_ENV_FILE_TARGET}").exists()
_start_unconfigured()

FIXTURE_MARKERS = {
    "fnl_cache_path": ("network",),
}
"""
Markers a test gets for using a fixture, directly or through another fixture.
Pytest can't mark fixtures, so a test using an expensive fixture would
otherwise have to repeat its markers.
"""


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    # tryfirst, so the markers are in place before `-m` deselects
    for item in items:
        for fixture in getattr(item, "fixturenames", ()):
            for marker in FIXTURE_MARKERS.get(fixture, ()):
                item.add_marker(marker)


def pytest_addoption(parser):
    parser.addoption(
        "--test-cache",
        type=Path,
        default=ROOT_DIR / "data" / "test-cache",
        help="Folder to unpack test data bundles into, kept between runs. Default: data/test-cache",
    )


@pytest.fixture
def root_dir() -> Path:
    return ROOT_DIR


@pytest.fixture
def test_data_dir(root_dir) -> Path:
    """Test data tracked in git: the WRF output MCIP reads, until #337."""
    return root_dir / "tests" / "test-data"


def _fetch_bundle(name: str, cache: Path) -> Path:
    bundle = yaml.safe_load(BUNDLES_FILE.read_text())[name]
    try:
        return fetch_archive(bundle["url"], bundle["sha256"], cache / name)
    except DownloadFailed as error:
        pytest.fail(f"Couldn't fetch the {name} test data in {BUNDLES_FILE}: {error}")


@pytest.fixture(scope="session")
def wrf_data(pytestconfig) -> Path:
    """
    The reference output of the WRF step for au-test on 2022-12-07, downloaded
    on first use. Holds `au-test/`, laid out as `${STORE_PATH}/wrf/au-test`.
    """
    return _fetch_bundle("wrf", pytestconfig.getoption("test_cache"))


@pytest.fixture(scope="session")
def daily_run_data(pytestconfig) -> Path:
    """
    Inputs and outputs of each step of the daily and monthly workflows for
    au-test on 2022-12-07, downloaded on first use. Holds a folder per kind of
    data (`mcip/`, `obs/`, `templates/` and so on) and the domain files in
    `domains/au-test/v1/`.
    """
    return _fetch_bundle("daily_run", pytestconfig.getoption("test_cache"))


@pytest.fixture
def metcro3d_file(daily_run_data):
    return str(daily_run_data / "mcip" / "2022-12-07" / "d01" / "METCRO3D_au-test_v1")


def _clean_attrs(
    attrs: dict,
    excluded_fields: tuple[str, ...] = (
        "HISTORY",
        "CDATE",
        "CTIME",
        "WDATE",
        "WTIME",
        # IOAPI 3.1 truncates this to the length of a stale buffer
        # (crtfil3.F), so its value depends on what the binary wrote before
        "IOAPI_VERSION",
    ),
) -> dict:
    clean = {}
    for key, value in attrs.items():
        if key in excluded_fields:
            continue
        if hasattr(value, "item"):
            try:
                clean[key] = value.item()
            except ValueError:
                clean[key] = value.tolist()
        else:
            clean[key] = value

    return clean


def _extract_group(ds: xr.Dataset):
    return {
        "attrs": _clean_attrs(ds.attrs),
        "coords": dict(ds.coords),
        "dims": dict(ds.sizes),
        "variables": {k: {"attrs": dict(v.attrs), "dims": v.dims} for k, v in ds.variables.items()},
    }


@pytest.fixture
def compare_dataset(data_regression):
    """
    Check if the structure of xarray dataset/datatree instance has changed
    """

    def compare(ds: xr.Dataset | str, basename: str | None = None):
        if isinstance(ds, Path | str):
            ds = xr.load_dataset(ds)

        if not hasattr(ds, "groups"):
            content = _extract_group(ds)
        else:
            content = {
                "groups": {k: _extract_group(ds[k]) for k in ds.groups},
                "attrs": _clean_attrs(ds.attrs),
            }
        try:
            data_regression.check(content, basename=basename)
        except AssertionError as exc:
            # pytest-regressions puts the bare string "FILES DIFFER" on the first
            # line and only names its temporary copies of the fixture. Since a
            # single test may compare several datasets, name the failing fixture
            # (and its tracked location) up front so the summary line is useful.
            expected = data_regression.original_datadir / f"{basename}.yml"
            raise AssertionError(f"{basename} differs from {expected}\n{exc}") from None

    return compare


def _reload_params():
    for name in PARAMS_MODULES:
        importlib.reload(importlib.import_module(name))


@pytest.fixture
def au_test_config(monkeypatch, tmp_path, test_data_dir, daily_run_data) -> Callable[..., None]:
    """
    Configuration for au-test v1 on 2022-12-07, reading inputs from the
    `daily_run` bundle and WRF output from `tests/test-data`, with
    `STORE_PATH` in the test's temporary folder.

    Clears the rest of the environment, except what processes need to start,
    and reloads `fourdvar.params`. Returns a function that sets more variables
    and reloads again, for example `au_test_config(END_DATE="2022-12-08")`;
    `None` unsets a variable.
    """
    domain_dir = daily_run_data / "domains" / "au-test" / "v1"
    variables = {
        "TARGET": NO_ENV_FILE_TARGET,
        "START_DATE": "2022-12-07",
        "END_DATE": "2022-12-07",
        "DOMAIN_NAME": "au-test",
        "DOMAIN_VERSION": "v1",
        "DOMAIN_MCIP_SUFFIX": "au-test_v1",
        "BOUNDARY_TRIM": "1",
        "STORE_PATH": tmp_path / "store",
        "TEMPLATE_DIR": daily_run_data / "templates",
        "MET_DIR": daily_run_data / "mcip",
        "CTM_DIR": daily_run_data / "cmaq",
        "WRF_DIR": test_data_dir / "wrf" / "au-test",
        "GEO_DIR": domain_dir,
        "DOMAIN_FILE": domain_dir / "domain.au-test.nc",
        "CAMS_PRODUCT": "inversion",
        "CAMS_INVERSION_VERSION": "v25r1",
        "CAMS_FILE": daily_run_data / "cams" / "cams_inversion_v25r1_2022-12-07.nc",
        "PRIOR_FILE": daily_run_data / "prior" / "prior-emissions.nc",
        "ICON_FILE": daily_run_data / "cmaq" / "template_icon_profile_CH4only_d01.nc",
        "BCON_FILE": daily_run_data / "cmaq" / "template_bcon_profile_CH4only_d01.nc",
        "CMAQ_BIN": "/opt/cmaq/bin",
        "ADJOINT_FWD": "/opt/cmaq/bin/ADJOINT_FWD",
        "ADJOINT_BWD": "/opt/cmaq/bin/ADJOINT_BWD",
    }

    def configure(**overrides: str | Path | None) -> None:
        for key, value in overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, str(value))
        _reload_params()

    for key in list(os.environ):
        if key not in (*PROCESS_VARIABLES, "HOME"):
            monkeypatch.delenv(key)
    configure(**variables)

    yield configure

    # Restore the environment before reloading, so later tests see the
    # unconfigured params rather than this test's
    monkeypatch.undo()
    _reload_params()


@pytest.fixture
def target_environment(monkeypatch):
    """
    Load the `.env.${TARGET}` file for a target. Only for tests of `.env`
    loading itself; other tests use a configuration fixture such as
    `au_test_config`.
    """
    initial_env = dict(os.environ)

    # The Docker targets need variables a run supplies, not the .env file
    run_variables = {
        "STORE_PATH": "/app/data",
        "START_DATE": "2022-12-07",
        "END_DATE": "2022-12-07",
        "DOMAIN_NAME": "au-test",
        "DOMAIN_VERSION": "v1",
    }
    default_variables = {"docker": run_variables, "docker-monthly": run_variables}

    def run(
        target: str,
        *,
        home: str = "{HOME}",
        clear: bool = True,
        overrides: dict[str, str] | None = None,
    ) -> None:
        if clear:
            os.environ.clear()

        monkeypatch.setenv("HOME", home)
        monkeypatch.setenv("TARGET", target)

        for key in PROCESS_VARIABLES:
            if key in initial_env:
                os.environ[key] = initial_env[key]

        # Use some common params to ensure the tests run as expected
        defaults = default_variables.get(target, {})
        os.environ.update(defaults)
        os.environ.update(overrides or {})

        _reload_params()

    yield run

    # Reset environment to match the initial environment
    os.environ.clear()
    os.environ.update(initial_env)

    _reload_params()
