#
# Copyright 2025 The Superpower Institute
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import pyproj
import xarray as xr


def _crs_from_dataset(ds: xr.Dataset) -> pyproj.CRS:
    """Build the projection from an open domain dataset"""
    # CF gives each data variable a `grid_mapping` attribute naming the variable
    # that carries the projection, so the name is read rather than assumed.
    names = {
        variable.attrs["grid_mapping"]
        for variable in ds.data_vars.values()
        if "grid_mapping" in variable.attrs
    }

    if not names:
        raise ValueError("No variable in the domain declares a `grid_mapping` attribute")
    if len(names) > 1:
        raise ValueError(f"The domain declares more than one grid mapping: {sorted(names)}")

    return pyproj.CRS.from_cf(ds[names.pop()].attrs)


def domain_crs(domain_file) -> pyproj.CRS:
    """
    Read the projection a domain's `x` and `y` coordinates are defined in

    Open Methane domains are on a Lambert conformal conic grid described by a CF
    grid mapping variable, so the projection is built from that rather than being
    reconstructed from the domain's attributes.
    """
    with xr.open_dataset(domain_file) as ds:
        return _crs_from_dataset(ds)


def domain_bounding_box(domain_file, crs: pyproj.CRS) -> list[float]:
    """
    Read a bounding box covering a domain from its definition file

    The box is taken from `x_bounds` and `y_bounds`, which hold the outer edges of
    each cell, so it covers the domain's full extent rather than only its cell
    centres.

    Returns `[left, bottom, right, top]` in `crs`.

    The projected edges of a domain are not straight in a geographic CRS, so the
    conversion samples along them rather than transforming the four corners,
    which would draw the box inside the domain it is meant to contain.
    """
    with xr.open_dataset(domain_file) as ds:
        domain = _crs_from_dataset(ds)
        x_bounds = ds["x_bounds"].to_numpy()
        y_bounds = ds["y_bounds"].to_numpy()

    transformer = pyproj.Transformer.from_crs(domain, crs, always_xy=True)
    left, bottom, right, top = transformer.transform_bounds(
        x_bounds.min(), y_bounds.min(), x_bounds.max(), y_bounds.max()
    )

    return [float(left), float(bottom), float(right), float(top)]
