import datetime as dt

import pytest
from scripts.obs_preprocess import fetch_tropomi

GRANULE = (
    "OFFL/L2__CH4___/2022/07/01/"
    "S5P_OFFL_L2__CH4____20220701T024730_20220701T042859_24427_02_020301_20220702T182808.nc"
)


def test_granule_period():
    assert fetch_tropomi.granule_period(GRANULE) == (
        dt.datetime(2022, 7, 1, 2, 47, 30),
        dt.datetime(2022, 7, 1, 4, 28, 59),
    )


def test_granule_period_unparseable():
    with pytest.raises(RuntimeError, match="Could not read a sensing period"):
        fetch_tropomi.granule_period("OFFL/L2__CH4___/2022/07/01/not-a-granule.nc")


def test_output_filename():
    assert fetch_tropomi.output_filename(GRANULE) == (
        "S5P_OFFL_L2__CH4____20220701T024730_20220701T042859_24427_02_020301_20220702T182808.nc4"
    )
