import pytest

from openmethane.wrf.geometry import DomainGeometry, DomainSet, GeometryError, load_geometry

# The three domains of the WRF index test (#296, #325): a 40x40 outer domain at
# 10 km and two sibling 31x31 nests at ratio 3.
INDEX_TEST_PROJECTION = {
    "map_proj": "lambert",
    "ref_lat": -33.5,
    "ref_lon": 150.0,
    "truelat1": -15.0,
    "truelat2": -40.0,
    "stand_lon": 133.302,
    "geog_data_res": "usgs_30s+default",
}
OUTER = DomainGeometry(
    name="outer", version="v1", e_we=40, e_sn=40, dx=10000, dy=10000, **INDEX_TEST_PROJECTION
)
TARGET = DomainGeometry(
    name="target",
    version="v1",
    e_we=31,
    e_sn=31,
    dx=10000 / 3,
    dy=10000 / 3,
    parent="outer",
    parent_grid_ratio=3,
    i_parent_start=8,
    j_parent_start=8,
    **INDEX_TEST_PROJECTION,
)
DUMMY = DomainGeometry(
    name="dummy",
    version="v1",
    e_we=31,
    e_sn=31,
    dx=10000 / 3,
    dy=10000 / 3,
    parent="outer",
    parent_grid_ratio=3,
    i_parent_start=24,
    j_parent_start=22,
    **INDEX_TEST_PROJECTION,
)


def nest_of(parent: str, name: str, dx: float) -> DomainGeometry:
    """A small nest at ratio 3 in the named parent, whose spacing is 3 times dx."""
    return DomainGeometry(
        name=name,
        version="v1",
        e_we=31,
        e_sn=31,
        dx=dx,
        dy=dx,
        parent=parent,
        parent_grid_ratio=3,
        i_parent_start=2,
        j_parent_start=2,
        **INDEX_TEST_PROJECTION,
    )


@pytest.mark.parametrize(
    "name, e_we, e_sn, ref_x, geog_data_res",
    (
        ("aust10km", 467, 443, 233.5, "usgs_10m+default"),
        ("au-test", 15, 15, -145.5, "usgs_30s+default"),
    ),
)
def test_loads_the_geometry_of_the_domains_we_run(name, e_we, e_sn, ref_x, geog_data_res):
    geometry = load_geometry(name, "v1")

    assert (geometry.name, geometry.version) == (name, "v1")
    assert (geometry.e_we, geometry.e_sn, geometry.dx, geometry.dy) == (e_we, e_sn, 10000, 10000)
    assert geometry.ref_x == ref_x
    assert geometry.geog_data_res == geog_data_res
    assert geometry.map_proj == "lambert"
    assert not geometry.is_nest


def test_an_unknown_domain_names_the_known_ones():
    with pytest.raises(GeometryError, match="No WRF geometry for domain 'nowhere'.*aust10km v1"):
        load_geometry("nowhere", "v1")


def test_an_unknown_version_of_a_known_domain_is_an_error():
    with pytest.raises(GeometryError, match="domain 'aust10km' version 'v2'"):
        load_geometry("aust10km", "v2")


def test_attributes_for_other_programs_are_ignored():
    attributes = {f"wrf_{key}": value for key, value in INDEX_TEST_PROJECTION.items()}
    attributes |= {"wrf_e_we": 31, "wrf_e_sn": 31, "wrf_dx": 10000 / 3, "wrf_dy": 10000 / 3}
    attributes |= {
        "parent_domain_name": "outer",
        "parent_domain_version": "v1",
        "parent_cmaq_col_offset": 7,
        "domain_format_version": 1,
        "wrf_parent_grid_ratio": 3,
    }

    geometry = DomainGeometry.from_attributes("target", "v2", attributes)

    assert geometry.version == "v2"
    assert geometry.parent == "outer"
    assert geometry.parent_grid_ratio == 3


def test_unknown_attributes_are_rejected_rather_than_ignored():
    attributes = {f"wrf_{key}": value for key, value in INDEX_TEST_PROJECTION.items()}
    attributes |= {"wrf_e_we": 40, "wrf_e_sn": 40, "wrf_dx": 10000, "wrf_dy": 10000}
    attributes["wrf_e_ew"] = 40

    with pytest.raises(GeometryError, match="Unknown attributes for domain outer: wrf_e_ew"):
        DomainGeometry.from_attributes("outer", "v1", attributes)


def test_missing_attributes_are_reported():
    with pytest.raises(GeometryError, match="Incomplete geometry for domain outer"):
        DomainGeometry.from_attributes("outer", "v1", {"wrf_map_proj": "lambert"})


def test_one_domain_is_d01():
    domains = DomainSet.from_geometries([OUTER])

    assert [domain.id for domain in domains] == ["d01"]
    assert domains.outer.parent_index == 1
    assert (domains.outer.dx, domains.outer.dy) == (10000, 10000)


def test_numbers_the_index_test_domains_parent_first_and_siblings_in_order():
    # The parent is listed between its nests; only the siblings' order matters.
    domains = DomainSet.from_geometries([TARGET, OUTER, DUMMY])

    assert domains.per_domain("name") == ["outer", "target", "dummy"]
    assert domains.per_domain("id") == ["d01", "d02", "d03"]
    assert domains.per_domain("index") == [1, 2, 3]
    assert domains.per_domain("parent_index") == [1, 1, 1]
    assert domains.per_domain("dx") == pytest.approx([10000, 10000 / 3, 10000 / 3])
    assert domains.per_domain("i_parent_start") == [1, 8, 24]


def test_swapping_siblings_swaps_their_numbers():
    domains = DomainSet.from_geometries([OUTER, DUMMY, TARGET])

    assert domains.per_domain("name") == ["outer", "dummy", "target"]


def test_a_nest_of_a_nest_follows_every_domain_nearer_the_outer_one():
    domains = DomainSet.from_geometries(
        [
            OUTER,
            TARGET,
            nest_of("target", "inner", 10000 / 9),
            DUMMY,
            nest_of("dummy", "inner2", 10000 / 9),
        ]
    )

    assert domains.per_domain("name") == ["outer", "target", "dummy", "inner", "inner2"]
    assert domains.per_domain("parent_index") == [1, 1, 1, 2, 3]
    assert domains.per_domain("dx") == pytest.approx(
        [10000, 10000 / 3, 10000 / 3, 10000 / 9, 10000 / 9]
    )


def test_a_set_needs_exactly_one_outer_domain():
    with pytest.raises(GeometryError, match="exactly one outer domain, got 0"):
        DomainSet.from_geometries([TARGET])
    with pytest.raises(GeometryError, match="exactly one outer domain, got 2"):
        DomainSet.from_geometries([OUTER, load_geometry("au-test", "v1")])


def test_a_nest_needs_its_parent_in_the_set():
    with pytest.raises(GeometryError, match="target is nested in outer, which isn't in the run"):
        DomainSet.from_geometries([load_geometry("au-test", "v1"), TARGET])


def test_domain_names_must_be_unique():
    with pytest.raises(GeometryError, match="Domain names repeat"):
        DomainSet.from_geometries([OUTER, TARGET, TARGET])


def test_nesting_in_a_loop_is_rejected():
    with pytest.raises(GeometryError, match="nested in a loop"):
        DomainSet.from_geometries([OUTER, nest_of("b", "a", 1000), nest_of("a", "b", 1000)])


def test_a_nest_spacing_that_disagrees_with_its_parent_is_an_error():
    with pytest.raises(GeometryError, match="inner has spacing 1000 x 1000, but its parent's"):
        DomainSet.from_geometries([OUTER, TARGET, nest_of("target", "inner", 1000)])


def test_grid_cells_are_one_less_than_the_staggered_size():
    domains = DomainSet.from_geometries([OUTER, TARGET])

    assert domains.grid_cells() == [(39, 39), (30, 30)]


def test_au_test_grid_cells_match_its_geo_em():
    # geo_em.d01.nc for au-test v1 is 14 x 14 cells
    domains = DomainSet.load([("au-test", "v1")])

    assert domains.grid_cells() == [(14, 14)]
