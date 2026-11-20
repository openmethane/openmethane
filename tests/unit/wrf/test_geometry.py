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
OUTER = DomainGeometry(name="outer", e_we=40, e_sn=40, dx=10000, dy=10000, **INDEX_TEST_PROJECTION)
TARGET = DomainGeometry(
    name="target",
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


def nest_of(parent: str, name: str) -> DomainGeometry:
    """A small nest at ratio 3 in the named parent."""
    return DomainGeometry(
        name=name,
        e_we=31,
        e_sn=31,
        dx=1000,
        dy=1000,
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
    geometry = load_geometry(name)

    assert geometry.name == name
    assert (geometry.e_we, geometry.e_sn, geometry.dx, geometry.dy) == (e_we, e_sn, 10000, 10000)
    assert geometry.ref_x == ref_x
    assert geometry.geog_data_res == geog_data_res
    assert geometry.map_proj == "lambert"
    assert not geometry.is_nest


def test_an_unknown_domain_names_the_known_ones():
    with pytest.raises(GeometryError, match="No WRF geometry for domain 'nowhere'.*aust10km"):
        load_geometry("nowhere")


def test_unknown_attributes_are_rejected_rather_than_ignored():
    attributes = {f"wrf_{key}": value for key, value in INDEX_TEST_PROJECTION.items()}
    attributes |= {"wrf_e_we": 40, "wrf_e_sn": 40, "wrf_dx": 10000, "wrf_dy": 10000}
    attributes["wrf_e_ew"] = 40

    with pytest.raises(GeometryError, match="Unknown attributes for domain outer: wrf_e_ew"):
        DomainGeometry.from_attributes("outer", attributes)


def test_missing_attributes_are_reported():
    with pytest.raises(GeometryError, match="Incomplete geometry for domain outer"):
        DomainGeometry.from_attributes("outer", {"wrf_map_proj": "lambert"})


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
        [OUTER, TARGET, nest_of("target", "inner"), DUMMY, nest_of("dummy", "inner2")]
    )

    assert domains.per_domain("name") == ["outer", "target", "dummy", "inner", "inner2"]
    assert domains.per_domain("parent_index") == [1, 1, 1, 2, 3]
    # Each nest's spacing is its parent's over the ratio, whatever it was given.
    assert domains.per_domain("dx") == pytest.approx(
        [10000, 10000 / 3, 10000 / 3, 10000 / 9, 10000 / 9]
    )


def test_a_set_needs_exactly_one_outer_domain():
    with pytest.raises(GeometryError, match="exactly one outer domain, got 0"):
        DomainSet.from_geometries([TARGET])
    with pytest.raises(GeometryError, match="exactly one outer domain, got 2"):
        DomainSet.from_geometries([OUTER, load_geometry("au-test")])


def test_a_nest_needs_its_parent_in_the_set():
    with pytest.raises(GeometryError, match="target is nested in outer, which isn't in the run"):
        DomainSet.from_geometries([load_geometry("au-test"), TARGET])


def test_domain_names_must_be_unique():
    with pytest.raises(GeometryError, match="Domain names repeat"):
        DomainSet.from_geometries([OUTER, TARGET, TARGET])


def test_nesting_in_a_loop_is_rejected():
    with pytest.raises(GeometryError, match="nested in a loop"):
        DomainSet.from_geometries([OUTER, nest_of("b", "a"), nest_of("a", "b")])
