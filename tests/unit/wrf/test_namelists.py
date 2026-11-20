import datetime

import f90nml
import pytest

from openmethane.wrf.geometry import DomainGeometry, DomainSet
from openmethane.wrf.namelists import (
    PER_DOMAIN,
    NamelistError,
    build_wps_namelist,
    build_wrf_namelist,
    read_model_config,
)
from openmethane.wrf.windows import RunWindow

# The window keeping 2022-12-07, as in the setup-wrf fixtures.
WINDOW = RunWindow(
    start=datetime.datetime(2022, 12, 6, 12),
    first_kept=datetime.datetime(2022, 12, 7),
    end=datetime.datetime(2022, 12, 8),
)

PROJECTION = {
    "map_proj": "lambert",
    "ref_lat": -33.5,
    "ref_lon": 150.0,
    "truelat1": -15.0,
    "truelat2": -40.0,
    "stand_lon": 133.302,
    "geog_data_res": "usgs_30s+default",
}
# The WRF index test's domains (#296, #325): a 40x40 outer domain at 10 km and
# two sibling 31x31 nests at ratio 3.
INDEX_TEST = [
    DomainGeometry(name="outer", e_we=40, e_sn=40, dx=10000, dy=10000, **PROJECTION),
    DomainGeometry(
        name="target", e_we=31, e_sn=31, dx=10000 / 3, dy=10000 / 3, parent="outer",
        parent_grid_ratio=3, i_parent_start=8, j_parent_start=8, **PROJECTION,
    ),
    DomainGeometry(
        name="dummy", e_we=31, e_sn=31, dx=10000 / 3, dy=10000 / 3, parent="outer",
        parent_grid_ratio=3, i_parent_start=24, j_parent_start=22, **PROJECTION,
    ),
]  # fmt: skip


def as_dict(namelist: f90nml.Namelist) -> dict:
    """A namelist as WRF reads it: written out and parsed back, as plain dicts."""
    return f90nml.reads(str(namelist)).todict()


def differences(ours: dict, theirs: dict, ignore: set[str]) -> list[str]:
    """Each setting that differs between two parsed namelists."""
    found = []
    for group in sorted(set(ours) | set(theirs)):
        mine, other = ours.get(group, {}), theirs.get(group, {})
        for key in sorted(set(mine) | set(other)):
            if key.startswith("_") or key in ignore:
                continue
            if mine.get(key) != other.get(key):
                found.append(f"{group}.{key}: ours {mine.get(key)!r}, setup-wrf {other.get(key)!r}")
    return found


@pytest.mark.parametrize("domain_name", ("au-test", "aust10km"))
def test_namelist_input_matches_setup_wrf(domain_name, test_data_dir):
    fixture = test_data_dir / "wrf-namelists" / "setup-wrf-0.9.2" / domain_name
    domains = DomainSet.load([(domain_name, "v1")])

    namelist = build_wrf_namelist(domains, WINDOW, num_metgrid_levels=34, num_metgrid_soil_levels=4)

    assert (
        differences(as_dict(namelist), f90nml.read(fixture / "namelist.input").todict(), set())
        == []
    )


@pytest.mark.parametrize(
    "domain_name, allowed",
    (
        ("au-test", []),
        # setup-wrf's aust10km template lists four resolutions, left over from a
        # multi-domain template. With one domain WPS reads only the first, and
        # only geogrid reads it at all.
        (
            "aust10km",
            [
                "geogrid.geog_data_res: ours 'usgs_10m+default', setup-wrf"
                " ['usgs_10m+default', 'usgs_30s+default', 'usgs_30s+default', 'usgs_30s+default']"
            ],
        ),
    ),
)
def test_namelist_wps_matches_setup_wrf(domain_name, allowed, test_data_dir):
    fixture = test_data_dir / "wrf-namelists" / "setup-wrf-0.9.2" / domain_name
    domains = DomainSet.load([(domain_name, "v1")])

    namelist = build_wps_namelist(domains, WINDOW)

    found = differences(
        as_dict(namelist), f90nml.read(fixture / "namelist.wps").todict(), {"geog_data_path"}
    )
    assert found == allowed


def test_nests_get_their_own_geometry_and_boundaries():
    domains = DomainSet.from_geometries(INDEX_TEST)

    namelist = build_wrf_namelist(domains, WINDOW, num_metgrid_levels=34, num_metgrid_soil_levels=4)

    settings = as_dict(namelist)
    assert settings["domains"]["max_dom"] == 3
    assert settings["domains"]["grid_id"] == [1, 2, 3]
    assert settings["domains"]["parent_id"] == [1, 1, 1]
    assert settings["domains"]["e_we"] == [40, 31, 31]
    assert settings["domains"]["i_parent_start"] == [1, 8, 24]
    assert settings["domains"]["j_parent_start"] == [1, 8, 22]
    assert settings["domains"]["parent_grid_ratio"] == [1, 3, 3]
    assert settings["domains"]["parent_time_step_ratio"] == [1, 3, 3]
    assert settings["domains"]["dx"] == pytest.approx([10000, 10000 / 3, 10000 / 3])
    assert settings["bdy_control"]["specified"] == [True, False, False]
    assert settings["bdy_control"]["nested"] == [False, True, True]


def test_every_per_domain_setting_has_a_value_for_each_domain():
    domains = DomainSet.from_geometries(INDEX_TEST)

    namelist = build_wrf_namelist(domains, WINDOW, num_metgrid_levels=34, num_metgrid_soil_levels=4)

    settings = as_dict(namelist)
    short = {
        f"{group}.{key}": value
        for group, keys in PER_DOMAIN.items()
        for key, value in settings.get(group, {}).items()
        if key in keys and not (isinstance(value, list) and len(value) == 3)
    }
    assert short == {}
    assert settings["time_control"]["iofields_filename"] == ["add_remove_var.txt"] * 3
    assert settings["time_control"]["history_begin_h"] == [12] * 3
    assert settings["physics"]["cu_physics"] == [5] * 3


def test_wps_lists_each_domain_and_takes_spacing_from_the_outer_one():
    domains = DomainSet.from_geometries(INDEX_TEST)

    namelist = build_wps_namelist(domains, WINDOW, geog_data_path="/geog/WPS_GEOG")

    settings = as_dict(namelist)
    assert settings["share"]["max_dom"] == 3
    assert settings["share"]["start_date"] == ["2022-12-06_12:00:00"] * 3
    assert settings["geogrid"]["parent_id"] == [1, 1, 1]
    assert settings["geogrid"]["i_parent_start"] == [1, 8, 24]
    assert settings["geogrid"]["geog_data_res"] == ["usgs_30s+default"] * 3
    assert (settings["geogrid"]["dx"], settings["geogrid"]["dy"]) == (10000, 10000)
    assert settings["geogrid"]["geog_data_path"] == "/geog/WPS_GEOG"
    # The index test's outer domain is centred on its reference point.
    assert "ref_x" not in settings["geogrid"]


def test_wps_and_wrf_namelists_agree_on_the_geometry():
    # setup-wrf checked this at run time; building both from one domain set
    # makes it true by construction.
    domains = DomainSet.from_geometries(INDEX_TEST)

    wps = as_dict(build_wps_namelist(domains, WINDOW))
    wrf = as_dict(
        build_wrf_namelist(domains, WINDOW, num_metgrid_levels=34, num_metgrid_soil_levels=4)
    )

    assert wps["share"]["max_dom"] == wrf["domains"]["max_dom"]
    assert wps["share"]["interval_seconds"] == wrf["time_control"]["interval_seconds"]
    for key in (
        "parent_id",
        "parent_grid_ratio",
        "i_parent_start",
        "j_parent_start",
        "e_we",
        "e_sn",
    ):
        assert wps["geogrid"][key] == wrf["domains"][key], key
    assert wps["geogrid"]["dx"] == wrf["domains"]["dx"][0]


def test_an_unclassified_setting_in_the_model_configuration_is_an_error():
    model_config = read_model_config()
    model_config["physics"]["shcu_physics"] = 0

    with pytest.raises(NamelistError, match="physics.shcu_physics"):
        build_wrf_namelist(
            DomainSet.from_geometries(INDEX_TEST),
            WINDOW,
            num_metgrid_levels=34,
            num_metgrid_soil_levels=4,
            model_config=model_config,
        )


def test_a_per_domain_list_must_match_the_domains():
    model_config = read_model_config()
    model_config["physics"]["cu_physics"] = [5, 0]

    with pytest.raises(NamelistError, match="physics.cu_physics has 2 values for 3 domains"):
        build_wrf_namelist(
            DomainSet.from_geometries(INDEX_TEST),
            WINDOW,
            num_metgrid_levels=34,
            num_metgrid_soil_levels=4,
            model_config=model_config,
        )


def test_the_model_configuration_passed_in_is_left_unchanged():
    model_config = read_model_config()
    before = model_config.todict()

    build_wrf_namelist(
        DomainSet.from_geometries(INDEX_TEST),
        WINDOW,
        num_metgrid_levels=34,
        num_metgrid_soil_levels=4,
        model_config=model_config,
    )

    assert model_config.todict() == before


def test_a_per_domain_list_of_the_right_length_is_kept():
    model_config = read_model_config()
    model_config["physics"]["cu_physics"] = [5, 0, 0]

    namelist = build_wrf_namelist(
        DomainSet.from_geometries(INDEX_TEST),
        WINDOW,
        num_metgrid_levels=34,
        num_metgrid_soil_levels=4,
        model_config=model_config,
    )

    assert as_dict(namelist)["physics"]["cu_physics"] == [5, 0, 0]
