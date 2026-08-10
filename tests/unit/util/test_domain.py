import numpy as np
import pyproj
import pytest
import xarray as xr

from openmethane.util.domain import domain_bounding_box, domain_crs

# Roughly the projection Open Methane domains use, on a sphere like WRF's
LAMBERT = pyproj.CRS.from_proj4(
    "+proj=lcc +lat_0=-27.64 +lon_0=133.3 +lat_1=-15 +lat_2=-40 +R=6370000 +units=m +no_defs"
)

WGS84 = pyproj.CRS.from_epsg(4326)

# Continental scale, like the aust10km domain. The projected edges of a domain
# this size curve appreciably in a geographic CRS, which the conversion has to
# account for.
CELL = 1_000_000.0
X_CENTRES = np.arange(-2, 3) * CELL
Y_CENTRES = np.arange(-2, 3) * CELL


def bounds_for(centres):
    return np.stack([centres - CELL / 2, centres + CELL / 2], axis=-1)


@pytest.fixture
def domain_file(tmp_path):
    """Write a small domain laid out like the real ones"""
    ds = xr.Dataset(
        data_vars={
            "land_mask": (
                ("y", "x"),
                np.ones((Y_CENTRES.size, X_CENTRES.size)),
                {"grid_mapping": "lambert_conformal"},
            ),
            "lambert_conformal": ((), 0, LAMBERT.to_cf()),
            "x_bounds": (("x", "cell_bounds"), bounds_for(X_CENTRES)),
            "y_bounds": (("y", "cell_bounds"), bounds_for(Y_CENTRES)),
        },
        coords={"x": X_CENTRES, "y": Y_CENTRES},
    )

    path = tmp_path / "domain.test.nc"
    ds.to_netcdf(path)

    return path


def test_domain_crs_reads_the_declared_grid_mapping(domain_file):
    assert domain_crs(domain_file).equals(LAMBERT)


def test_domain_crs_without_a_grid_mapping(tmp_path):
    path = tmp_path / "domain.no-mapping.nc"
    xr.Dataset({"land_mask": (("y", "x"), np.ones((2, 2)))}).to_netcdf(path)

    with pytest.raises(ValueError, match="No variable in the domain declares"):
        domain_crs(path)


def test_domain_crs_with_conflicting_grid_mappings(tmp_path):
    path = tmp_path / "domain.two-mappings.nc"
    xr.Dataset(
        {
            "land_mask": (("y", "x"), np.ones((2, 2)), {"grid_mapping": "lambert_conformal"}),
            "inventory_mask": (("y", "x"), np.ones((2, 2)), {"grid_mapping": "something_else"}),
            "lambert_conformal": ((), 0, LAMBERT.to_cf()),
            "something_else": ((), 0, WGS84.to_cf()),
        }
    ).to_netcdf(path)

    with pytest.raises(ValueError, match="more than one grid mapping"):
        domain_crs(path)


def test_domain_bounding_box_in_the_domain_crs(domain_file):
    """
    Asking for the domain's own CRS returns the cell edges unchanged

    The box comes from x_bounds and y_bounds, so it reaches half a cell beyond
    the outermost centres in each direction.
    """
    assert domain_bounding_box(domain_file, LAMBERT) == [
        X_CENTRES.min() - CELL / 2,
        Y_CENTRES.min() - CELL / 2,
        X_CENTRES.max() + CELL / 2,
        Y_CENTRES.max() + CELL / 2,
    ]


def test_domain_bounding_box_contains_every_cell_edge(domain_file):
    """Converting must not draw the box inside the domain it should contain"""
    left, bottom, right, top = domain_bounding_box(domain_file, WGS84)

    transformer = pyproj.Transformer.from_crs(LAMBERT, WGS84, always_xy=True)
    edges = bounds_for(X_CENTRES).ravel(), bounds_for(Y_CENTRES).ravel()
    mesh_x, mesh_y = np.meshgrid(*edges)
    longitude, latitude = transformer.transform(mesh_x, mesh_y)

    assert left <= longitude.min()
    assert bottom <= latitude.min()
    assert right >= longitude.max()
    assert top >= latitude.max()


def test_domain_bounding_box_is_wider_than_the_transformed_corners(domain_file):
    """
    The projected edges of a domain curve in a geographic CRS

    Transforming only the four corners would understate the box, so the box has to
    contain the corner one and be strictly larger somewhere.
    """
    left, bottom, right, top = domain_bounding_box(domain_file, WGS84)

    transformer = pyproj.Transformer.from_crs(LAMBERT, WGS84, always_xy=True)
    corner_left, corner_bottom = transformer.transform(
        X_CENTRES.min() - CELL / 2, Y_CENTRES.min() - CELL / 2
    )
    corner_right, corner_top = transformer.transform(
        X_CENTRES.max() + CELL / 2, Y_CENTRES.max() + CELL / 2
    )

    corners = (corner_left, corner_bottom, corner_right, corner_top)
    box = (left, bottom, right, top)

    assert left <= corner_left
    assert bottom <= corner_bottom
    assert right >= corner_right
    assert top >= corner_top
    assert box != corners
