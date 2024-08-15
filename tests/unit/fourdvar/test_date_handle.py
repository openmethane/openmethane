import datetime

import pytest

from fourdvar.util import date_handle


def test_get_datelist(target_environment):
    target_environment("docker")
    res = date_handle.get_datelist()
    assert res == [datetime.date(2022, 7, 22)]

    # Check that the modified config from target_environment fixture is flowing through as expected
    target_environment("docker", overrides={"START_DATE": "2022-07-01", "END_DATE": "2022-07-02"})
    res = date_handle.get_datelist()
    assert res == [datetime.date(2022, 7, 1), datetime.date(2022, 7, 2)]


@pytest.mark.parametrize(
    "date,inp,exp",
    [
        (datetime.date(2022, 7, 22), "<YYYYMMDD>", "20220722"),
        (datetime.date(2022, 7, 1), "<YYYYMMDD>", "20220701"),
        (datetime.date(2022, 7, 22), "<YYYY-MM-DD>", "2022-07-22"),
        (datetime.date(2022, 7, 22), "<YYYYDDD>", "2022203"),
        (datetime.date(2022, 7, 22), "test/<YYYYMMDD>/other", "test/20220722/other"),
        (datetime.date(2022, 7, 22), "test/<YYYYMMDD>/<YYYYMMDD>", "test/20220722/20220722"),
        (datetime.date(2022, 7, 22), "<YYYYMMDD>/<YYYY-MM-DD>", "20220722/2022-07-22"),
    ],
)
def test_replace_date(target_environment, date, inp, exp):
    target_environment("docker")

    res = date_handle.replace_date(inp, date)

    assert res == exp
