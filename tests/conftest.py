import os
from importlib import reload
from pathlib import Path

import pytest
import xarray as xr

from fourdvar import env
from fourdvar.params import (
    archive_defn,
    cmaq_config,
    data_access,
    date_defn,
    input_defn,
    root_path_defn,
    template_defn,
)


@pytest.fixture
def root_dir() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(root_dir) -> Path:
    return root_dir / "tests" / "test-data"


def _clean_attrs(
    attrs: dict,
    excluded_fields: tuple[str, ...] = (
        "HISTORY",
        "CDATE",
        "CTIME",
        "WDATE",
        "WTIME",
        "IOAPI_VERSION",  # TODO: Check why this differs on the CI
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
        data_regression.check(content, basename=basename)

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

    def run(target: str, home: str = "{HOME}", clear: bool = True) -> None:
        if clear:
            os.environ.clear()

        monkeypatch.setenv("HOME", home)
        monkeypatch.setenv("TARGET", target)

        _reload_params()

        # Add back the env variables that weren't added during the reload
        missing_keys = set(initial_env.keys()) - set(os.environ.keys())
        for k in missing_keys:
            os.environ[k] = initial_env[k]

    yield run

    # Reset environment to match the initial environment
    os.environ.clear()
    os.environ.update(initial_env)

    _reload_params()
