import datetime as dt

import pytest
from scripts.obs_preprocess import fetch_tropomi

OFFL = "S5P_OFFL_L2__CH4____20221207T025418_20221207T043548_26683_03_020400_20221213T140313.nc"
RPRO = "S5P_RPRO_L2__CH4____20220701T024730_20220701T042859_24427_03_020400_20230131T104028.nc"


def test_granule_period():
    assert fetch_tropomi.granule_period(OFFL) == (
        dt.datetime(2022, 12, 7, 2, 54, 18),
        dt.datetime(2022, 12, 7, 4, 35, 48),
    )


def test_granule_period_unparseable():
    with pytest.raises(RuntimeError, match="Could not read a sensing period"):
        fetch_tropomi.granule_period("not-a-granule.nc")


def test_granule_orbit():
    assert fetch_tropomi.granule_orbit(OFFL) == "26683"
    assert fetch_tropomi.granule_orbit(RPRO) == "24427"


def test_object_key_offl():
    assert fetch_tropomi.object_key(OFFL) == f"OFFL/L2__CH4___/2022/12/07/{OFFL}"


def test_object_key_rpro():
    """The timeliness comes from the filename, so RPRO resolves to its own prefix"""
    assert fetch_tropomi.object_key(RPRO) == f"RPRO/L2__CH4___/2022/07/01/{RPRO}"


def test_reject_duplicate_orbits_passes_distinct_orbits():
    assert fetch_tropomi.reject_duplicate_orbits([OFFL, RPRO]) == [OFFL, RPRO]


def test_reject_duplicate_orbits_rejects_two_versions_of_one_orbit():
    """Two products for one orbit would put the same observations in twice"""
    superseded = RPRO.replace("_03_020400_", "_02_020301_")

    with pytest.raises(RuntimeError, match="more than one product per orbit.*orbit 24427"):
        fetch_tropomi.reject_duplicate_orbits([RPRO, superseded])
