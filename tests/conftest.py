import os
from importlib import reload
from pathlib import Path

import pytest
import xarray as xr
import yaml

from openmethane.fourdvar import env
from openmethane.fourdvar.params import (
    archive_defn,
    cmaq_config,
    data_access,
    date_defn,
    input_defn,
    root_path_defn,
    template_defn,
)
from openmethane.util.download import DownloadFailed, fetch_archive

TESTS_DIR = Path(__file__).parent
BUNDLES_FILE = TESTS_DIR / "test-data" / "bundles.yaml"

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
        default=TESTS_DIR.parent / "data" / "test-cache",
        help="Folder to unpack test data bundles into, kept between runs. Default: data/test-cache",
    )


@pytest.fixture
def root_dir() -> Path:
    return TESTS_DIR.parent


@pytest.fixture
def test_data_dir(root_dir) -> Path:
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


@pytest.fixture
def metcro3d_file(test_data_dir, tmpdir):
    return str(test_data_dir / "mcip" / "2022-12-07" / "d01" / "METCRO3D_au-test_v1")


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
    reload(env)
    reload(root_path_defn)
    reload(input_defn)
    reload(date_defn)
    reload(archive_defn)
    reload(template_defn)
    reload(data_access)
    reload(cmaq_config)


@pytest.fixture
def target_environment(monkeypatch):
    initial_env = dict(os.environ)

    default_variables = {
        # Docker target requires some additional env variables
        "docker": {
            "STORE_PATH": "/app/data",
            "START_DATE": "2022-12-07",
            "END_DATE": "2022-12-07",
            "DOMAIN_NAME": "au-test",
            "DOMAIN_VERSION": "v1",
        }
    }
    # Variables not to strip out of the current environment
    # This isn't an exhaustive list, just some common ones
    # I'm not certain about the impact on pytest/pycharm
    extra_variables = [
        "PATH",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "LD_LIBRARY_PATH",
    ]

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

        for key in extra_variables:
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
