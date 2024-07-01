from pathlib import Path

import pytest
import xarray as xr


@pytest.fixture
def root_dir() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(root_dir) -> Path:
    return root_dir / "tests" / "test-data"


def _clean_attrs(attrs: dict) -> dict:
    clean = {}
    for key, value in attrs.items():
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

    def compare(ds):
        if not hasattr(ds, "groups"):
            content = _extract_group(ds)
        else:
            content = {
                "groups": {k: _extract_group(ds[k]) for k in ds.groups},
                "attrs": _clean_attrs(ds.attrs),
            }
        data_regression.check(content)

    return compare
